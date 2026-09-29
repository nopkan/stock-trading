from datetime import datetime
from decimal import Decimal
import json
import pytest
from trading.audit import redact, canonical
from trading.settings import Settings
from trading.brokers.innovestx import InnovestXBroker
from scripts.bundle_research import create_bundle, restore_bundle
from scripts.registry_transfer import export_registry, restore_registry
from research.registry import Registry


def test_redaction_preserves_financial_values_and_removes_nested_credentials():
    result=redact({'apiKey':'do-not-log','details':[{'Authorization':'Bearer private','price':Decimal('12.25')}],
                   'STOCK_DATABASE_URL':'private','symbol':'PTT'})
    assert result=={'apiKey':'[REDACTED]','details':[{'Authorization':'[REDACTED]','price':'12.25'}],
                    'STOCK_DATABASE_URL':'[REDACTED]','symbol':'PTT'}
    with pytest.raises(ValueError): canonical({'price':float('nan')})
    with pytest.raises(ValueError): redact({'time':datetime(2026,1,1)})


def test_live_env_and_broker_submission_fail_closed(monkeypatch):
    monkeypatch.setattr('trading.settings.load_env',lambda:None)
    monkeypatch.setenv('STOCK_DATABASE_URL','postgresql://local@127.0.0.1/test')
    monkeypatch.setenv('STOCK_LIVE_ENABLED','true')
    with pytest.raises(ValueError): Settings.from_env()
    with pytest.raises(RuntimeError): InnovestXBroker().submit_order(symbol='PTT',shares=100)
    with pytest.raises(RuntimeError): InnovestXBroker().cancel_order('123')


def test_bundle_restore_hashes_and_preserves_conflicting_files(tmp_path):
    source=tmp_path/'source';(source/'data/prices').mkdir(parents=True)
    (source/'data/prices/A.csv').write_text('real-source-bytes')
    bundle=tmp_path/'bundle.tar.gz';create_bundle(bundle,source)
    dest=tmp_path/'dest';dest.mkdir()
    assert restore_bundle(bundle,dest)['verified_files']==1
    assert (dest/'data/prices/A.csv').read_text()=='real-source-bytes'
    assert restore_bundle(bundle,dest)['verified_files']==1
    (dest/'data/prices/A.csv').write_text('preserve-me')
    with pytest.raises(ValueError): restore_bundle(bundle,dest)
    assert (dest/'data/prices/A.csv').read_text()=='preserve-me'


def test_lossless_registry_round_trip_and_conflict_rejection(tmp_path):
    folder=tmp_path/'source';registry=Registry(folder)
    registry.put('context','candidate','stage',{'x':1},{'return':.123,'bool':False,'names':['A']});registry.db.close()
    exported=export_registry(folder);dest=tmp_path/'dest';dest.mkdir()
    (dest/'trials.jsonl').write_bytes(exported.read_bytes())
    assert restore_registry(dest)==1
    assert restore_registry(dest)==0
    r=json.loads((dest/'trials.jsonl').read_text());r['result']['return']=.5
    (dest/'trials.jsonl').write_text(json.dumps(r)+'\n')
    with pytest.raises(ValueError): restore_registry(dest)
