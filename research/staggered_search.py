"""Final, adaptive 36-variant rebalance diversification experiment."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib,json
import numpy as np
import pandas as pd
from research.portfolio import ROOT,Panel,FeeSchedule,simulate,benchmark
from research.refinements import Refinement
from research.staggered import StaggeredFactory,grid
from research.refine_search import PERIODS,INCUMBENT
from research.registry import Registry

FOLDER=ROOT/'reports/momentum_staggered_20260929'


def main():
    FOLDER.mkdir(exist_ok=True);p=Panel.load();reg=Registry(ROOT/'research/experiments')
    config=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    fees={k:FeeSchedule(**config[k]) for k in ['base','stress']}
    files=['research/portfolio.py','research/candidates.py','research/refinements.py',
        'research/staggered.py','research/staggered_search.py','research/refine_search.py',
        'configs/thai_trading_costs.json','configs/data_exclusions.json']
    source={'prices':p.source_hashes,'code':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    context='stagger_'+hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()[:16]
    plan={'context':context,'created_at':datetime.now(timezone.utc).isoformat(),'source':source,
        'candidates':[asdict(s) for s in grid()],'costs':config,'periods':PERIODS,
        'reason':'Adaptive third and final batch after two prior batches exposed rebalance-date sensitivity. Test multiple scheduled baskets, netted into one fully costed portfolio. No future holdout claims.',
        'screen':'Higher development CAGR, smaller development drawdown, discovery and validation CAGR at most 2 percentage points below incumbent. Lock top12 by sum of development CAGR gain and drawdown improvement.',
        'confirm':'Higher full CAGR and smaller full drawdown than incumbent at base AND stress fees; recent drawdown no worse and recent CAGR at most 2 percentage points lower at both costs, and above buy-hold.',
        'audit':'All locked variants: full/recent with +1 execution session, DELTA excluded, THAI excluded, phase shifted by10. Compare equally perturbed incumbent. Require higher full CAGR and smaller full drawdown in each scenario; report recent comparisons. Select qualified variant with highest frozen development score.',
        'holdout':'No untouched period remains in available prices. Fixed current SET100 snapshot, 2017-2026. Future data after September28 reserved.'}
    path=FOLDER/'search_plan.json'
    if path.exists():
        if json.loads(path.read_text())['context']!=context:raise RuntimeError('Frozen context changed')
    else:path.write_text(json.dumps(plan,indent=2))
    factory=StaggeredFactory(p)
    def run(s,period,profile='base',scenario='normal',panel=p,f=factory):
        cid=INCUMBENT if isinstance(s,Refinement) else s.identity
        stage=f'{scenario}_{period}_{profile}'
        old=reg.get(context,cid,stage)
        if old is not None:return old
        t=f.targets(s,phase=10 if scenario=='phase10' else 0)
        if scenario=='delay':t=np.vstack([np.full((1,t.shape[1]),np.nan),t[:-1]])
        r,e,fills=simulate(panel,t,*PERIODS[period],fees[profile],config['initial_capital_thb'],details=scenario=='normal')
        reg.put(context,cid,stage,asdict(s),r)
        if scenario=='normal':
            folder=FOLDER/cid;folder.mkdir(exist_ok=True)
            e.rename('equity').rename_axis('date').to_csv(folder/f'{period}_{profile}_equity.csv')
            fills.to_csv(folder/f'{period}_{profile}_fills.csv',index=False)
        return r
    baseline={f'{period}_{profile}':run(Refinement(),period,profile) for period in PERIODS for profile in fees}
    (FOLDER/'incumbent.json').write_text(json.dumps(baseline,indent=2))
    buyhold={}
    for period in ['full','recent']:
        for profile in fees:
            r,e=benchmark(p,*PERIODS[period],fees[profile],config['initial_capital_thb']);buyhold[period+'_'+profile]=r
            if reg.get(context,'benchmark',period+'_'+profile) is None:reg.put(context,'benchmark',period+'_'+profile,{'family':'buy_hold'},r)
            e.rename('equity').rename_axis('date').to_csv(FOLDER/f'benchmark_{period}_{profile}.csv')
    rows=[]
    for s in grid():
        row={'candidate':s.identity,'parameters':json.dumps(asdict(s),sort_keys=True)}
        for period in ['discovery','validation','development']:
            row.update({period+'_base_'+k:v for k,v in run(s,period).items()})
        gain=row['development_base_cagr']-baseline['development_base']['cagr']
        dd=row['development_base_max_drawdown']-baseline['development_base']['max_drawdown']
        row.update(screen_pass=bool(gain>0 and dd>0 and all(row[v+'_base_cagr']>=baseline[v+'_base']['cagr']-.02 for v in ['discovery','validation'])),selection_score=gain+dd)
        rows.append(row)
    screen=pd.DataFrame(rows).sort_values('selection_score',ascending=False)
    screen.to_csv(FOLDER/'screen_results.csv',index=False)
    locked=screen[screen.screen_pass].head(12).candidate.tolist()
    lockpath=FOLDER/'locked_shortlist.json'
    if not lockpath.exists():lockpath.write_text(json.dumps({'locked_at':datetime.now(timezone.utc).isoformat(),'candidate_ids':locked},indent=2))
    elif json.loads(lockpath.read_text())['candidate_ids']!=locked:raise RuntimeError('Shortlist changed')
    print('Staggered screen passed',int(screen.screen_pass.sum()),'locked',len(locked),flush=True)
    for s,row in zip(grid(),rows):
        row['confirmed']=False
        if s.identity not in locked:continue
        ok=True
        for period in ['full','recent']:
            for profile in fees:
                stage=period+'_'+profile;r=run(s,period,profile);b=baseline[stage]
                row.update({stage+'_'+k:v for k,v in r.items()})
                ok &= r['cagr']>b['cagr']-(.02 if period=='recent' else 0) and r['max_drawdown']>b['max_drawdown']
                if period=='recent':ok &= r['cagr']>buyhold[stage]['cagr']
        row['confirmed']=bool(ok)
        print(s.identity,'confirmed',ok,f'return {row["full_base_total_return"]:.2%}, DD {row["full_base_max_drawdown"]:.2%}',flush=True)
    audit=[]
    for scenario in ['delay','exclude_DELTA','exclude_THAI','phase10']:
        panel=Panel(p.frames,p.exclusions|{scenario.removeprefix('exclude_')}) if scenario.startswith('exclude_') else p
        f=StaggeredFactory(panel)
        for period in ['full','recent']:
            b=run(Refinement(),period,scenario=scenario,panel=panel,f=f)
            for s in grid():
                if s.identity not in locked:continue
                r=run(s,period,scenario=scenario,panel=panel,f=f)
                audit.append({'candidate':s.identity,'scenario':scenario,'period':period,**r,
                    'incumbent_cagr':b['cagr'],'incumbent_total_return':b['total_return'],'incumbent_max_drawdown':b['max_drawdown'],
                    'cagr_gain':r['cagr']-b['cagr'],'drawdown_gain':r['max_drawdown']-b['max_drawdown']})
        print('Audited',scenario,flush=True)
    ad=pd.DataFrame(audit);ad.to_csv(FOLDER/'sensitivity_results.csv',index=False)
    for row in rows:
        a=ad[(ad.candidate.eq(row['candidate']))&ad.period.eq('full')] if len(ad) else ad
        row['audit_pass']=bool(len(a)==4 and (a.cagr_gain>0).all() and (a.drawdown_gain>0).all())
        row['status']=('qualified' if row['confirmed'] and row['audit_pass'] else 'rejected_screen' if not row['screen_pass'] else
            'not_shortlisted' if row['candidate'] not in locked else 'rejected_confirmation' if not row['confirmed'] else 'rejected_sensitivity')
    result=pd.DataFrame(rows).sort_values('selection_score',ascending=False)
    qualified=result[result.status.eq('qualified')]
    if len(qualified):result.loc[result.candidate.eq(qualified.iloc[0].candidate),'status']='selected'
    result.to_csv(FOLDER/'all_candidates.csv',index=False)
    result[result.status.eq('selected')].to_csv(FOLDER/'selected.csv',index=False)
    reg.export();print(result[['candidate','screen_pass','confirmed','audit_pass','status']].to_string(index=False),flush=True)


if __name__=='__main__':main()
