"""Local audit operations; no command in this CLI can send a broker order."""
import argparse
from datetime import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from zoneinfo import ZoneInfo
import psycopg
from psycopg import sql
from trading.audit import AuditStore
from trading.ingest import import_snapshot
from trading.settings import ROOT, Settings, load_env


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');sub.add_parser('provision-user');sub.add_parser('verify-audit')
    imp=sub.add_parser('import');imp.add_argument('--directories',nargs='+',default=['data','reports','research/experiments','configs'])
    imp.add_argument('--label',default='local-research')
    check=sub.add_parser('check');check.add_argument('--window',choices=['morning','afternoon','close'],required=True)
    bt=sub.add_parser('backtest');bt.add_argument('--output',required=True,type=Path)
    bt.add_argument('--cost-profile',choices=['base','minimum_fee','stress'],default='base')
    a=p.parse_args();load_env()
    if a.command=='provision-user':
        password=getpass.getpass('New stock_runtime database password: ')
        if len(password)<16: raise ValueError('Use a database password with at least 16 characters')
        if password!=getpass.getpass('Repeat password: '): raise ValueError('Passwords did not match')
        with psycopg.connect(os.environ['STOCK_ADMIN_DATABASE_URL'],connect_timeout=10) as conn:
            exists=conn.execute("SELECT 1 FROM pg_roles WHERE rolname='stock_runtime'").fetchone()
            if exists: raise ValueError('stock_runtime already exists; refusing to change existing credentials')
            conn.execute(sql.SQL('CREATE ROLE stock_runtime LOGIN PASSWORD {}').format(sql.Literal(password)))
            conn.execute('GRANT stock_app TO stock_runtime')
        print('Created stock_runtime; set STOCK_DATABASE_URL in the ignored .env file (URL-encode password).');return
    settings=Settings.from_env()
    if a.command=='backtest':
        output=a.output.resolve()
        if not output.is_relative_to(ROOT/'reports'): raise ValueError('Output must be inside reports/')
        if output.exists() and any(output.iterdir()): raise ValueError('Choose a new output directory')
        run_id=str(uuid.uuid4());config=ROOT/'configs/set100_100000_strategy.json'
        with AuditStore.connect(settings.database_url) as store:
            inputs=import_snapshot(store,ROOT,['data','configs'],f'inputs:{run_id}')
            store.event(run_id+':requested','backtest.requested',{'run_id':run_id,'output':str(output.relative_to(ROOT)),
                        'input_snapshot_id':inputs['snapshot_id'],
                        'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),'cost_profile':a.cost_profile})
        result=subprocess.run([sys.executable,'-m','backtest.capital_ranked','--accept-snapshot-bias',
            '--cost-profile',a.cost_profile,'--output',str(output)],cwd=ROOT)
        with AuditStore.connect(settings.database_url) as store:
            if result.returncode==0:
                imported=import_snapshot(store,ROOT,[str(output.relative_to(ROOT))],f'backtest:{run_id}')
                record=json.loads((output/'run.json').read_text())
                captured=dict(store.connection.execute('SELECT path,artifact_hash FROM trading.snapshot_files WHERE snapshot_id=%s',(inputs['snapshot_id'],)).fetchall())
                matched=all(captured.get(f'data/prices/{symbol}.csv')==digest for symbol,digest in record['price_hashes'].items())
                matched=matched and captured.get('configs/set100_100000_strategy.json')==record['config_hash']
                store.event(run_id+':finished','backtest.finished' if matched else 'backtest.input_changed',
                            {'run_id':run_id,'input_snapshot_id':inputs['snapshot_id'],'input_hashes_match':matched,**imported})
            else: store.event(run_id+':failed','backtest.failed',{'run_id':run_id,'exit_code':result.returncode})
        if result.returncode: raise SystemExit(result.returncode)
        if not matched: raise ValueError('Inputs changed during execution; audit marked unverified')
        return
    with AuditStore.connect(settings.database_url) as store:
        if a.command=='doctor':
            version=store.connection.execute('SHOW server_version').fetchone()[0]
            count=store.connection.execute('SELECT count(*) FROM trading.audit_events').fetchone()[0]
            print(json.dumps({'database':'reachable','postgres_version':version,'events':count,'broker':settings.broker,'mode':settings.mode,'live_enabled':False}))
        elif a.command=='verify-audit':
            total,broken=store.connection.execute('SELECT count(*),count(*) FILTER (WHERE NOT linked OR NOT valid_hash) FROM trading.audit_chain_health').fetchone()
            print(json.dumps({'events':total,'broken_events':broken}))
            if broken: raise ValueError('Audit chain verification failed')
        elif a.command=='import':
            print(json.dumps(import_snapshot(store,ROOT,a.directories,a.label)))
        elif a.command=='check':
            now=datetime.now(ZoneInfo(settings.timezone))
            # Research health check only: no market-data freshness/calendar claim,
            # no signals or orders. Repeated launchd runs on the same date dedupe.
            store.event(f'check:{now.date()}:{a.window}','window.checked',{'date':str(now.date()),'window':a.window,
                'broker':settings.broker,'mode':settings.mode,'orders_sent':0,'status':'blocked_for_live',
                'reason':'Strategy failed extended robustness; broker integration and live calendar/feed not configured'})
            print(json.dumps({'window':a.window,'orders_sent':0,'status':'research_check_recorded'}))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        # Database exceptions can contain a DSN or payload. Keep console logs clean.
        print(f'Operation failed ({type(exc).__name__}); verify configuration and database health.',file=sys.stderr)
        raise SystemExit(1)
