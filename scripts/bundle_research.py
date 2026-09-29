"""Private, checksummed data transfer. Never upload the bundle to the public repo."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from research.portfolio import ROOT
from trading.ingest import snapshot_files


def create_bundle(output, root=ROOT):
    output=Path(output).resolve()
    if output.exists(): raise ValueError('Bundle already exists; choose a new filename')
    paths=snapshot_files(root,['data','reports','outputs','research/experiments'])
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest=[]
    with tempfile.TemporaryDirectory() as temporary:
        database=root/'research/experiments/registry.sqlite3';extra=[]
        if database.exists():
            copied=Path(temporary)/'registry.sqlite3'
            with sqlite3.connect(f'file:{database}?mode=ro',uri=True) as source,sqlite3.connect(copied) as target: source.backup(target)
            extra=[(copied,'research/experiments/registry.sqlite3')]
        with tarfile.open(output,'x:gz') as archive:
            for path,name in [(p,str(p.relative_to(root))) for p in paths]+extra:
                content=path.read_bytes();info=tarfile.TarInfo(name);info.size=len(content);info.mode=0o600
                archive.addfile(info,io.BytesIO(content))
                manifest.append({'path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
            content=json.dumps({'format':1,'files':manifest},indent=2).encode()
            info=tarfile.TarInfo('TRANSFER_MANIFEST.json');info.size=len(content);info.mode=0o600
            archive.addfile(info,io.BytesIO(content))
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(f'{digest}  {output.name}\n')
    return {'bundle':str(output),'files':len(manifest),'bytes':output.stat().st_size,'sha256':digest}


def restore_bundle(bundle, root=ROOT):
    root=Path(root).resolve();entries=[]
    with tarfile.open(bundle,'r:gz') as archive:
        members=archive.getmembers()
        if len({m.name for m in members})!=len(members): raise ValueError('Duplicate archive path')
        for member in members:
            path=(root/member.name).resolve()
            if not member.isfile() or not path.is_relative_to(root): raise ValueError('Unsafe archive member')
            if member.name!='TRANSFER_MANIFEST.json' and Path(member.name).parts[0] not in {'data','reports','outputs','research'}:
                raise ValueError('Unexpected archive directory')
        manifest=json.load(archive.extractfile('TRANSFER_MANIFEST.json'))
        expected={r['path']:r for r in manifest['files']}
        if len(expected)!=len(manifest['files']) or set(expected)!={m.name for m in members if m.name!='TRANSFER_MANIFEST.json'}:
            raise ValueError('Manifest and archive differ')
        for name,entry in expected.items():
            content=archive.extractfile(name).read()
            if len(content)!=entry['bytes'] or hashlib.sha256(content).hexdigest()!=entry['sha256']: raise ValueError('Archive checksum mismatch')
            path=root/name
            if path.exists() and (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']):
                raise ValueError('Existing file differs: restore into a staging directory and reconcile explicitly')
            entries.append((name,path))
        for name,path in entries:
            if path.exists(): continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as out: out.write(archive.extractfile(name).read())
    return {'verified_files':len(entries),'destination':str(root)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['create','restore']);p.add_argument('path',type=Path)
    p.add_argument('--destination',type=Path,default=ROOT);a=p.parse_args()
    print(json.dumps(create_bundle(a.path) if a.command=='create' else restore_bundle(a.path,a.destination),indent=2))
