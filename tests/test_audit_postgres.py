"""Runs against disposable PostgreSQL in CI; never uses the user's real DB."""
import os
from pathlib import Path
import uuid
import psycopg
import pytest
from trading.audit import AuditStore
from trading.ingest import import_snapshot

URL=os.getenv('STOCK_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Disposable PostgreSQL URL not set')


@pytest.fixture(scope='module')
def db():
    root=Path(__file__).resolve().parents[1]
    with psycopg.connect(URL,autocommit=True) as conn:
        exists=conn.execute("SELECT to_regnamespace('trading')").fetchone()[0]
        if exists: raise RuntimeError('Integration test requires a fresh disposable database')
        for migration in sorted((root/'supabase/migrations').glob('*.sql')): conn.execute(migration.read_text())
    yield


def test_append_idempotence_conflicts_and_chain(db):
    with psycopg.connect(URL) as conn:
        conn.execute('SET ROLE stock_app');store=AuditStore(conn)
        key=str(uuid.uuid4());first=store.event(key,'test',{'secret':'private','price':'12.50'})
        assert first==store.event(key,'test',{'secret':'private','price':'12.50'})
        with pytest.raises(psycopg.Error),conn.transaction(): store.event(key,'test',{'price':'99'})
        assert conn.execute('SELECT payload FROM trading.audit_events WHERE id=%s',(first,)).fetchone()[0]['secret']=='[REDACTED]'
        store.event(str(uuid.uuid4()),'second',{})
        assert conn.execute('SELECT bool_and(linked AND valid_hash) FROM trading.audit_chain_health').fetchone()[0]
        for query in ['UPDATE trading.audit_events SET kind=kind','DELETE FROM trading.audit_events','TRUNCATE trading.audit_events']:
            with pytest.raises(psycopg.Error),conn.transaction(): conn.execute(query)


def test_source_import_is_atomic_queryable_and_idempotent(db,tmp_path):
    p=tmp_path/'data/prices';p.mkdir(parents=True)
    (p/'A.csv').write_text('date,open,high,low,close,adj_close,volume,dividends,stock_splits\n2026-01-05,10,11,9,10,10,100,0,0\n')
    with psycopg.connect(URL) as conn:
        conn.execute('SET ROLE stock_app');store=AuditStore(conn)
        a=import_snapshot(store,tmp_path,['data'],'test');b=import_snapshot(store,tmp_path,['data'],'retry')
        assert a['snapshot_id']==b['snapshot_id']
        assert conn.execute('SELECT count(*) FROM trading.market_bars WHERE snapshot_id=%s',(a['snapshot_id'],)).fetchone()[0]==1
        assert conn.execute('SELECT close FROM trading.market_bars WHERE snapshot_id=%s',(a['snapshot_id'],)).fetchone()[0]==10
        with pytest.raises(psycopg.Error),conn.transaction():
            conn.execute('INSERT INTO trading.artifacts VALUES (%s,%s,%s,now())',('0'*64,'text/plain',b'bad-hash'))


def test_owner_cannot_accidentally_mutate_history(db):
    with psycopg.connect(URL) as conn:
        AuditStore(conn).event(str(uuid.uuid4()),'owner-check',{})
        with pytest.raises(psycopg.Error),conn.transaction(): conn.execute('UPDATE trading.audit_events SET kind=kind')
