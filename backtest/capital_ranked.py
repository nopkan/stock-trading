"""Replay the frozen THB100,000 research candidate. No broker integration."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule
from research.small_capital import LotData, simulate_lots, price_only_basket
from research.capital_search import CapitalRecipe, rank_features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'configs/set100_100000_strategy.json')
    parser.add_argument('--capital', type=float, default=100000.)
    parser.add_argument('--start', default='2017-01-04')
    parser.add_argument('--end', default='2026-09-28')
    parser.add_argument('--cost-profile', choices=['base','minimum_fee','stress'], default='base')
    parser.add_argument('--accept-snapshot-bias', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    if not a.accept_snapshot_bias: parser.error('--accept-snapshot-bias is required for this research dataset')
    if a.output.exists() and any(a.output.iterdir()): parser.error('Use a new output folder')
    if pd.Timestamp(a.start) >= pd.Timestamp(a.end): parser.error('start must precede end')
    config = json.loads(a.config.read_text())
    recipe = CapitalRecipe.from_parameters(config['parameters'])
    if recipe.identity != config['candidate']: parser.error('Candidate identity mismatch')
    p = Panel.load()
    index = pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv', index_col='date', parse_dates=True).close
    if pd.Timestamp(a.end) > index.index[-1]: parser.error('Requested end exceeds saved history')
    dates = index.loc[p.dates[0]:p.dates[-1]].index
    p = Panel({s:f.reindex(dates) for s,f in p.frames.items()},p.exclusions|{'THAI'},p.source_hashes)
    data = LotData(p); features = rank_features(p)[recipe.ranking]
    cfg = json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    fee = FeeSchedule(**cfg['stress' if a.cost_profile == 'stress' else 'base'])
    if a.cost_profile == 'minimum_fee': fee = replace(fee, minimum_daily_commission_thb=50)
    result, curve, fills, daily = simulate_lots(data,features,recipe.sizing,a.start,a.end,fee,a.capital,details=True)
    benchmark, bc = price_only_basket(data,a.start,a.end,fee,a.capital)
    a.output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame({'strategy':curve,'fractional_price_basket':bc}).to_csv(a.output/'equity.csv',index_label='date')
    fills.to_csv(a.output/'fills.csv',index=False); daily.to_csv(a.output/'daily.csv')
    files = ['research/capital_search.py','research/small_capital.py','research/portfolio.py','research/candidates.py','backtest/capital_ranked.py']
    record = {'candidate':recipe.identity,'parameters':recipe.parameters,'capital_thb':a.capital,
              'start':a.start,'end':a.end,'costs':asdict(fee),'strategy':result,'benchmark':benchmark,
              'price_hashes':p.source_hashes,'config_hash':hashlib.sha256(a.config.read_bytes()).hexdigest(),
              'code_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
              'live_ready':False,'limitations':'Fixed current universe; action-derived prices and unverified 100-share lots; dividends excluded; daily proxies, no afternoon auction data.'}
    (a.output/'run.json').write_text(json.dumps(record,indent=2))
    print(json.dumps({'strategy':result,'benchmark':benchmark},indent=2))


if __name__ == '__main__': main()
