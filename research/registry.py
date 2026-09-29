"""Persistent, deduplicated experiment records. Rejections are never erased."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd


class Registry:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True,exist_ok=True)
        self.db = sqlite3.connect(self.folder/'registry.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS trials (context TEXT, candidate TEXT, stage TEXT, spec TEXT, result TEXT, created TEXT, PRIMARY KEY(context,candidate,stage))')
        self.db.commit()

    def get(self,context,candidate,stage):
        row = self.db.execute('SELECT result FROM trials WHERE context=? AND candidate=? AND stage=?',(context,candidate,stage)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self,context,candidate,stage,spec,result):
        self.db.execute('INSERT INTO trials VALUES (?,?,?,?,?,?)',(context,candidate,stage,
            json.dumps(spec,sort_keys=True),json.dumps(result,sort_keys=True,allow_nan=False),datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def export(self):
        rows = []
        for context,candidate,stage,spec,result,created in self.db.execute('SELECT * FROM trials ORDER BY created,candidate,stage'):
            rows.append({'context':context,'candidate':candidate,'stage':stage,'created':created,
                         'specification':spec,**json.loads(result)})
        pd.DataFrame(rows).to_csv(self.folder/'all_trials.csv',index=False)
        return rows
