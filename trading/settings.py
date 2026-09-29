"""Small explicit config surface; live mode cannot be enabled by an env typo."""
from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def load_env(path=ROOT/'.env'):
    """Read simple KEY=value pairs without shell evaluation or overriding exports."""
    if not path.exists(): return
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        if '=' not in line: raise ValueError('Invalid environment file entry')
        key,value=line.split('=',1)
        if not key.isidentifier(): raise ValueError('Invalid environment variable name')
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"): value=value[1:-1]
        os.environ.setdefault(key,value)


@dataclass(frozen=True)
class Settings:
    database_url: str
    broker: str = 'innovestx'
    mode: str = 'research'
    timezone: str = 'Asia/Bangkok'

    @classmethod
    def from_env(cls):
        load_env()
        if os.getenv('STOCK_LIVE_ENABLED','false').lower() != 'false':
            raise ValueError('Live trading is not implemented or approved')
        mode=os.getenv('STOCK_MODE','research')
        if mode != 'research': raise ValueError('Only research mode is supported')
        broker=os.getenv('STOCK_BROKER','innovestx')
        if broker != 'innovestx': raise ValueError('Configured broker must be innovestx')
        tz=os.getenv('STOCK_TIMEZONE','Asia/Bangkok')
        if tz != 'Asia/Bangkok': raise ValueError('Use Asia/Bangkok scheduling')
        url=os.getenv('STOCK_DATABASE_URL','')
        parsed=urlparse(url)
        if parsed.scheme not in ('postgres','postgresql') or not parsed.hostname:
            raise ValueError('Set STOCK_DATABASE_URL for the local audit database')
        return cls(url,broker,mode,tz)
