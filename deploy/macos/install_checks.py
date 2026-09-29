"""Render launchd plists for research checks. Does not load or start an agent."""
from pathlib import Path
import plistlib
from trading.settings import ROOT


def main():
    output=ROOT/'.local/launchd';output.mkdir(parents=True,exist_ok=True)
    logs=ROOT/'.local/logs';logs.mkdir(parents=True,exist_ok=True)
    for window,hour,minute in [('morning',9,45),('afternoon',13,45),('close',16,30)]:
        label=f'local.stock-trading.{window}'
        config={'Label':label,'ProgramArguments':[str(ROOT/'.venv/bin/python'),'-m','trading.cli','check','--window',window],
                'WorkingDirectory':str(ROOT),'StartCalendarInterval':{'Hour':hour,'Minute':minute},
                'StandardOutPath':str(logs/f'{window}.log'),'StandardErrorPath':str(logs/f'{window}.error.log'),
                'EnvironmentVariables':{'PYTHONUNBUFFERED':'1'},'ProcessType':'Background'}
        path=output/f'{label}.plist'
        with path.open('wb') as f: plistlib.dump(config,f)
        print(path)
    print('Rendered only. launchd uses the Mac system timezone: set Asia/Bangkok before loading.')


if __name__=='__main__': main()
