"""Create a private PostgreSQL data-only audit backup using pg_dump 17+."""
from datetime import datetime, timezone
import hashlib
import os
import shutil
import subprocess
from psycopg.conninfo import conninfo_to_dict
from trading.settings import ROOT, load_env


def main():
    load_env();binary=shutil.which('pg_dump')
    if not binary: raise SystemExit('Install PostgreSQL client tools and put pg_dump on PATH')
    info=conninfo_to_dict(os.environ['STOCK_ADMIN_DATABASE_URL']);env=os.environ.copy()
    for key,target in {'host':'PGHOST','port':'PGPORT','user':'PGUSER','password':'PGPASSWORD','dbname':'PGDATABASE','sslmode':'PGSSLMODE'}.items():
        if key in info: env[target]=info[key]
    directory=ROOT/'.local/backups';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(datetime.now(timezone.utc).strftime('audit-%Y%m%dT%H%M%S%fZ')+'.dump');partial=path.with_suffix('.partial')
    fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    subprocess.run([binary,'--format=custom','--data-only','--schema=trading','--file',str(partial)],env=env,check=True)
    partial.rename(path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix('.sha256').write_text(f'{digest}  {path.name}\n');print(path)


if __name__=='__main__': main()
