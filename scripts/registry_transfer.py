"""Lossless portable experiment registry export/restore (no source data)."""
import argparse
import json
from pathlib import Path
import sqlite3
from research.portfolio import ROOT
from research.registry import Registry


def export_registry(folder):
    target=folder/'trials.jsonl'
    with sqlite3.connect(f'file:{folder / "registry.sqlite3"}?mode=ro',uri=True) as db:
        rows=db.execute('SELECT context,candidate,stage,spec,result,created FROM trials ORDER BY context,candidate,stage')
        with target.open('w') as out:
            for context,candidate,stage,spec,result,created in rows:
                out.write(json.dumps(dict(context=context,candidate=candidate,stage=stage,spec=json.loads(spec),result=json.loads(result),created=created),sort_keys=True,allow_nan=False)+'\n')
    return target


def restore_registry(folder):
    registry=Registry(folder); count=0
    for line in (folder/'trials.jsonl').read_text().splitlines():
        r=json.loads(line);old=registry.get(r['context'],r['candidate'],r['stage'])
        if old is not None:
            row=registry.db.execute('SELECT spec FROM trials WHERE context=? AND candidate=? AND stage=?',(r['context'],r['candidate'],r['stage'])).fetchone()
            if old!=r['result'] or json.loads(row[0])!=r['spec']: raise ValueError('Conflicting historical trial; refusing to overwrite')
            continue
        registry.db.execute('INSERT INTO trials VALUES (?,?,?,?,?,?)',(r['context'],r['candidate'],r['stage'],json.dumps(r['spec'],sort_keys=True),json.dumps(r['result'],sort_keys=True),r['created']));count+=1
    registry.db.commit();registry.db.close();return count


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['export','restore'])
    a=p.parse_args();folder=ROOT/'research/experiments'
    print(export_registry(folder) if a.command=='export' else f'Restored {restore_registry(folder)} missing trials')
