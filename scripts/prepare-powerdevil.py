#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare the pinned Debian PowerDevil source and its native sheng patch."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

PROJECT=Path(__file__).resolve().parents[1]
LOCAL=PROJECT/'device/power-management'


def sha(data):return hashlib.sha256(data).hexdigest()


def combined_patch():
    patch=(LOCAL/'powerdevil.patch').read_bytes().replace(b'\r\n',b'\n')
    for name,destination in [('shengpolicy.cpp','daemon/shengpolicy.cpp'),('shengpolicy.h','daemon/shengpolicy.h'),
                              ('shengpolicytest.cpp','autotests/shengpolicytest.cpp')]:
        lines=(LOCAL/name).read_text(encoding='utf-8').splitlines(True)
        patch+=('diff --git a/'+destination+' b/'+destination+'\nnew file mode 100644\n--- /dev/null\n+++ b/'+destination+
                '\n@@ -0,0 +1,'+str(len(lines))+' @@\n'+''.join('+'+line for line in lines)).encode()
    return patch


def add_native_patch(source):
    patch=source/'debian/patches/sheng-native-power.diff'
    patch.write_bytes(combined_patch())
    series=source/'debian/patches/series'
    entries=series.read_text().splitlines()
    if patch.name not in entries:
        series.write_text('\n'.join(entries+[patch.name])+'\n')
    subprocess.run(['dpkg-source','--before-build',str(source)],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=PROJECT/'out/powerdevil-source')
    parser.add_argument('--cache-dir',type=Path,default=PROJECT/'out/powerdevil-downloads')
    args=parser.parse_args()
    if not shutil.which('dpkg-source') or not shutil.which('gpgv'):
        raise SystemExit('Use a Linux build environment with dpkg-dev, gpgv and debian-keyring')
    pin=json.loads((LOCAL/'provenance.json').read_text(encoding='utf-8'))
    for name,expected in pin['local_files'].items():
        if sha((LOCAL/name).read_bytes().replace(b'\r\n',b'\n'))!=expected:
            raise SystemExit('Native source changed; review provenance: '+name)
    if args.output_dir.exists():
        raise SystemExit('Select a fresh source directory')
    args.cache_dir.mkdir(parents=True,exist_ok=True)
    for name,expected in pin['archives'].items():
        target=args.cache_dir/name
        if not target.exists():
            with urllib.request.urlopen(pin['archive_base']+name,timeout=60) as response,target.open('wb') as output:
                shutil.copyfileobj(response,output)
        if sha(target.read_bytes())!=expected:
            raise SystemExit('Archive hash mismatch: '+name)
    dsc=args.cache_dir/pin['dsc_name']
    subprocess.run(['gpgv','--keyring',pin['debian_keyring'],str(dsc)],check=True)
    args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['dpkg-source','-x',str(dsc),str(args.output_dir)],check=True)
    add_native_patch(args.output_dir)
    print(json.dumps({'source':str(args.output_dir),'upstream':pin['upstream_version'],
                      'debian':pin['debian_version'],'nativePolicy':pin['policy_version']}))


if __name__=='__main__':main()
