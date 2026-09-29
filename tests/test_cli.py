import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_custom_parameters_benchmark_and_quarantined_cash(tmp_path):
    dates = pd.bdate_range('2020-01-01', periods=300)
    price = np.linspace(100, 180, len(dates))
    data = pd.DataFrame({'date': dates, 'close': price, 'adj_open': price, 'adj_high': price,
                         'adj_low': price, 'adj_close': price, 'volume': 1000})
    data.to_csv(tmp_path / 'PTT.csv', index=False)
    data.to_csv(tmp_path / 'BANPU.csv', index=False)
    output = tmp_path / 'report'
    subprocess.run([sys.executable, '-m', 'backtest.run', '--strategy', 'rank_multi_horizon',
        '--params', '{"min_turnover_thb": 0}', '--symbols', 'PTT', 'BANPU',
        '--data-dir', str(tmp_path), '--start', '2020-02-01', '--end', '2020-12-31',
        '--output', str(output), '--accept-snapshot-bias'], cwd=ROOT, check=True, capture_output=True)
    report = pd.read_csv(output / 'comparison.csv')
    assert set(report.strategy) == {'rank_multi_horizon', 'buy_hold'}
    targets = pd.read_csv(output / 'rank_multi_horizon_targets.csv')
    assert targets.BANPU.eq(0).all()
    metadata = json.loads((output / 'run.json').read_text())
    assert metadata['parameters']['rank_multi_horizon']['min_turnover_thb'] == 0
    assert metadata['exclusions'] == ['BANPU']


def test_snapshot_flag_required():
    result = subprocess.run([sys.executable, '-m', 'backtest.run'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert '--accept-snapshot-bias' in result.stderr
