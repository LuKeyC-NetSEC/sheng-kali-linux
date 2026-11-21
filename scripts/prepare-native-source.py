#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch and verify a pinned native component source; never build or install it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

PROJECT=Path(__file__).resolve().parents[1]


def main():
    recipes=json.loads((PROJECT/'configs/native-source-pins.json').read_text(encoding='utf-8'))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component',choices=sorted(recipes))
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--cache-dir',type=Path)
    args=parser.parse_args()
    if not shutil.which('dpkg-source') or not shutil.which('gpgv'):
        raise SystemExit('Use Linux with dpkg-dev, gpgv and debian-keyring')
    pin=recipes[args.component]
    output=args.output_dir or PROJECT/'out/native-sources'/args.component
    cache=args.cache_dir or PROJECT/'out/native-source-downloads'/args.component
    if output.exists():raise SystemExit('Choose a fresh output directory')
    cache.mkdir(parents=True,exist_ok=True)
    dsc=None
    for name,expected in pin['archives'].items():
        if Path(name).name!=name:raise SystemExit('Invalid pinned archive name')
        target=cache/name
        if not target.exists():
            with urllib.request.urlopen(pin['baseUrl']+name,timeout=120) as source,target.open('wb') as destination:
                shutil.copyfileobj(source,destination)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
            raise SystemExit('Archive hash mismatch: '+name)
        if name.endswith('.dsc'):dsc=target
    if dsc is None:raise SystemExit('Missing pinned dsc')
    subprocess.run(['gpgv','--keyring','/usr/share/keyrings/debian-keyring.pgp',str(dsc)],check=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['dpkg-source','-x',str(dsc),str(output)],check=True)
    print(json.dumps({'component':args.component,'version':pin['version'],'source':str(output)}))


if __name__=='__main__':main()
