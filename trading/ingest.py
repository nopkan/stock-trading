"""Import real saved source bytes plus queryable bars/trials in one transaction."""
import csv
from datetime import date
from decimal import Decimal
import hashlib
import json
import mimetypes
from pathlib import Path
import sqlite3
from psycopg.types.json import Jsonb
from trading.audit import canonical

ALLOWED_ROOTS={'data','reports','research','outputs','configs'}


def snapshot_files(root, directories):
    paths=[]
    for directory in directories:
        base=(root/directory).resolve()
        if not base.is_relative_to(root.resolve()) or Path(directory).parts[0] not in ALLOWED_ROOTS:
            raise ValueError('Snapshot directory must be a project data/report/config directory')
        for p in sorted(base.rglob('*')):
            if not p.is_file() or p.is_symlink(): continue
            rel=p.relative_to(root)
            if any(part.startswith('.') or part=='__pycache__' for part in rel.parts): continue
            if p.suffix in ('.pyc','.pem','.key','.p12') or p.name.endswith(('-wal','-shm')): continue
            # SQLite needs the backup API for an atomic snapshot; JSONL is the portable export.
            if p.suffix=='.sqlite3': continue
            paths.append(p)
    return sorted(set(paths))


def import_snapshot(store, root, directories, label):
    root=Path(root).resolve(); paths=snapshot_files(root,directories)
    if not paths: raise ValueError('No snapshot files found')
    entries=[]
    for path in paths:
        content=path.read_bytes()
        digest=store.artifact(content,mimetypes.guess_type(path)[0] or 'application/octet-stream')
        entries.append({'path':str(path.relative_to(root)),'sha256':digest,'bytes':len(content)})
    manifest={'format':1,'files':entries}
    digest=store.artifact(canonical(manifest).encode(),'application/json')
    store.connection.execute('INSERT INTO trading.snapshots(manifest_hash,label,metadata) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                             (digest,label,Jsonb({'format':1,'files':len(entries),'universe':'fixed_current_snapshot','cash_dividends_in_recent_results':False})))
    sid=store.connection.execute('SELECT id FROM trading.snapshots WHERE manifest_hash=%s',(digest,)).fetchone()[0]
    bar_count=0; trial_count=0
    for entry in entries:
        store.connection.execute('INSERT INTO trading.snapshot_files VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(sid,entry['path'],entry['sha256']))
        if entry['path'].startswith('data/prices/') and entry['path'].endswith('.csv'):
            # Parse exactly the stored bytes, never reread a changing source file.
            content=store.connection.execute('SELECT content FROM trading.artifacts WHERE sha256=%s',(entry['sha256'],)).fetchone()[0]
            rows=[]
            for r in csv.DictReader(bytes(content).decode().splitlines()):
                symbol=Path(entry['path']).stem
                numbers=[Decimal(r[k]) for k in ('open','high','low','close','adj_close','volume','dividends','stock_splits')]
                if not all(n.is_finite() for n in numbers): raise ValueError('Non-finite source bar')
                rows.append((sid,symbol,date.fromisoformat(r['date'][:10]),entry['sha256'],
                    *numbers,Jsonb(r)))
            with store.connection.cursor() as cursor:
                cursor.executemany('INSERT INTO trading.market_bars VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',rows)
            bar_count+=len(rows)
        if entry['path']=='research/experiments/trials.jsonl':
            content=store.connection.execute('SELECT content FROM trading.artifacts WHERE sha256=%s',(entry['sha256'],)).fetchone()[0]
            rows=[]
            for line in bytes(content).decode().splitlines():
                r=json.loads(line)
                rows.append((sid,r['context'],r['candidate'],r['stage'],Jsonb(r['spec']),Jsonb(r['result']),r['created']))
            with store.connection.cursor() as cursor:
                cursor.executemany('INSERT INTO trading.research_trials VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',rows)
            trial_count+=len(rows)
    store.event('snapshot:'+digest,'snapshot.imported',{'snapshot_id':str(sid),'manifest_sha256':digest,
                'file_count':len(entries),'price_rows':bar_count,'trial_rows':trial_count})
    return {'snapshot_id':str(sid),'files':len(entries),'price_rows':bar_count,'trial_rows':trial_count}
