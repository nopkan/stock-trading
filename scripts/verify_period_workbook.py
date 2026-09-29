"""Check exported Excel formula caches against the independently computed CSVs."""
from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from scripts.analyze_buffered_momentum import OUT, ROOT


def main():
    workbook=ROOT/'outputs/01a0ebd9-e77d-7571-805b-78cea90f47e8/SET100_strategy_annual_monthly_analysis.xlsx'
    ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    checked=0
    with zipfile.ZipFile(workbook) as z:
        sheets=[ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml')) for i in [1,2,3]]
        assert all(not s.findall('.//x:c[@t="e"]',ns) for s in sheets),'Excel formula error'
        for tree,file in zip(sheets,['annual_comparison.csv','monthly_comparison.csv']):
            cells={c.attrib['r']:c for c in tree.findall('.//x:c',ns)}
            table=pd.read_csv(OUT/file)
            for i,row in table.iterrows():
                for col,name in [('B','Strategy_return'),('C','Buy_hold_return'),('D','SET100_price_return')]:
                    cell=cells[f'{col}{i+8}']
                    assert cell.find('x:f',ns) is not None
                    np.testing.assert_allclose(float(cell.find('x:v',ns).text),row[name],atol=1e-12)
                    checked+=1
        annual={c.attrib['r']:c for c in sheets[0].findall('.//x:c',ns)}
        a=pd.read_csv(OUT/'annual_comparison.csv')
        for i,row in a.iterrows():
            for ref,name in [(f'H{i+8}','mean_exposure'),(f'B{i+24}','fees_thb'),(f'C{i+24}','slippage_thb'),(f'I{i+24}','max_stock_weight')]:
                np.testing.assert_allclose(float(annual[ref].find('x:v',ns).text),row[name],rtol=1e-10)
                checked+=1
    provenance=json.loads((OUT/'provenance.json').read_text())
    for file,digest in provenance['sha256'].items():
        assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==digest,file
    result={'exported_formula_values_checked':checked,'excel_formula_errors':0,'source_hashes_verified':len(provenance['sha256']),
            'workbook_sha256':hashlib.sha256(workbook.read_bytes()).hexdigest(),
            'annual_rows':10,'monthly_rows':117,'note':'Period compounding and fill/P&L reconciliation also asserted in analysis script.'}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
