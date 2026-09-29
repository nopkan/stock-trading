"""Replay the locked THB30k candidate using lot constraints, not fractional orders."""
from pathlib import Path
import argparse
from dataclasses import asdict, replace
import hashlib
import json
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule
from research.small_capital import LotData, Features, price_only_basket
from strategy.set100_small_capital import SPEC, CANDIDATE_ID, run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capital',type=float,default=30000)
    p.add_argument('--start',default='2017-01-04');p.add_argument('--end',default='2026-09-28')
    p.add_argument('--cost-profile',choices=['base','minimum_fee','stress'],default='base')
    p.add_argument('--accept-snapshot-bias',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.accept_snapshot_bias:p.error('Research uses current membership: --accept-snapshot-bias required')
    if a.output.exists() and any(a.output.iterdir()):p.error('Choose a new output directory; existing results are preserved')
    if pd.Timestamp(a.start)>=pd.Timestamp(a.end):p.error('start must precede end')
    original=Panel.load();index=pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv',index_col='date',parse_dates=True).close
    if pd.Timestamp(a.end)>index.index[-1]:p.error('No verified index calendar beyond saved data')
    calendar=index.loc[original.dates[0]:original.dates[-1]].index
    panel=Panel({s:f.reindex(calendar) for s,f in original.frames.items()},original.exclusions|{'THAI'},original.source_hashes)
    cfg=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    cost=FeeSchedule(**cfg['stress' if a.cost_profile=='stress' else 'base'])
    if a.cost_profile=='minimum_fee':cost=replace(cost,minimum_daily_commission_thb=50)
    data=LotData(panel);features=Features(panel)
    result,curve,fills,daily=run(data,features,a.start,a.end,cost,a.capital)
    b,bc=price_only_basket(data,a.start,a.end,cost,a.capital)
    a.output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame({'strategy':curve,'fractional_price_basket':bc}).to_csv(a.output/'equity.csv',index_label='date')
    fills.to_csv(a.output/'fills.csv',index=False);daily.to_csv(a.output/'daily.csv')
    code={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['strategy/set100_small_capital.py','research/small_capital.py','research/candidates.py','research/portfolio.py','backtest/small_capital.py']}
    record={'candidate':CANDIDATE_ID,'parameters':asdict(SPEC),'capital_thb':a.capital,'costs':asdict(cost),'start':a.start,'end':a.end,
        'strategy':result,'benchmark':b,'code_hashes':code,'price_hashes':original.source_hashes,'live_ready':False,
        'limitations':'Current universe; split-reconstructed prices and assumed 100-share lots; cash dividends excluded; daily open/close proxies; afternoon auction untested.'}
    (a.output/'run.json').write_text(json.dumps(record,indent=2))
    print(json.dumps({'strategy':result,'benchmark':b,'live_ready':False},indent=2))


if __name__=='__main__':main()
