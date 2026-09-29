"""Transactional, idempotent append-only audit writes. No broker calls."""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import psycopg
from psycopg.types.json import Jsonb


def redact(value):
    secret_keys={'password','passwd','secret','apisecret','apikey','token','accesstoken',
                 'refreshtoken','authorization','cookie','setcookie','privatekey','pin',
                 'databaseurl','stockdatabaseurl','stockadmindatabaseurl','dsn'}
    if isinstance(value,dict):
        return {str(k): '[REDACTED]' if re.sub('[^a-z0-9]','',str(k).lower()) in secret_keys
                else redact(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [redact(v) for v in value]
    if isinstance(value,Decimal): return str(value)
    if isinstance(value,datetime):
        if value.tzinfo is None: raise ValueError('Audit datetimes require a timezone')
        return value.astimezone(timezone.utc).isoformat()
    return value


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


class AuditStore:
    def __init__(self, connection): self.connection=connection

    @classmethod
    @contextmanager
    def connect(cls, url):
        # An error must abort all related writes, never silently fall back to files.
        with psycopg.connect(url,connect_timeout=10) as connection:
            yield cls(connection)

    def event(self, key, kind, payload, *, occurred_at=None, actor='stock-trading'):
        if not key or not kind: raise ValueError('Event key and kind are required')
        occurred_at=occurred_at or datetime.now(timezone.utc)
        if occurred_at.tzinfo is None: raise ValueError('Event time must include timezone')
        clean=redact(payload); canonical(clean)
        return self.connection.execute(
            'SELECT trading.append_event(%s,%s,%s,%s,%s)',
            (key,kind,Jsonb(clean),occurred_at,actor)).fetchone()[0]

    def artifact(self, content, media_type='application/octet-stream'):
        digest=hashlib.sha256(content).hexdigest()
        self.connection.execute('INSERT INTO trading.artifacts(sha256,media_type,content) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                                (digest,media_type,content))
        return digest
