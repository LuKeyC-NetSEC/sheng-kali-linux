#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Apply native shell ownership and touch-cancel fixes to pinned Plasma source."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[1]
LOCAL=PROJECT/'device/plasma-integration'


def patch_data():
    data=(LOCAL/'workspace.patch').read_bytes().replace(b'\r\n',b'\n')
    for name in ('shengdesktoppolicy.cpp','shengdesktoppolicy.h'):
        destination='shell/'+name
        lines=(LOCAL/name).read_text(encoding='utf-8').splitlines(True)
        data+=('diff --git a/'+destination+' b/'+destination+'\nnew file mode 100644\n--- /dev/null\n+++ b/'+destination+
               '\n@@ -0,0 +1,'+str(len(lines))+' @@\n'+''.join('+'+line for line in lines)).encode()
    return data


def apply(source):
    series=source/'debian/patches/series'
    series.parent.mkdir(parents=True,exist_ok=True)
    entries=series.read_text().splitlines() if series.exists() else []
    name='sheng-native-shell.diff'
    (series.parent/name).write_bytes(patch_data())
    if name not in entries:entries.append(name)
    series.write_text('\n'.join(entries)+'\n')
    subprocess.run(['dpkg-source','--before-build',str(source)],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=PROJECT/'out/plasma-native-source')
    parser.add_argument('--cache-dir',type=Path,default=PROJECT/'out/native-source-downloads/plasma-workspace')
    parser.add_argument('--existing-source',type=Path,help='Already verified, unmodified source from prepare-native-source.py')
    args=parser.parse_args()
    pin=json.loads((LOCAL/'provenance.json').read_text(encoding='utf-8'))
    for name,expected in pin['local_files'].items():
        if hashlib.sha256((LOCAL/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise SystemExit('Review native Plasma source hash: '+name)
    if args.existing_source:
        source=args.existing_source.resolve()
        version=subprocess.check_output(['dpkg-parsechangelog','-S','Version'],cwd=source,text=True).strip()
        if version!='4:6.7.4-2':raise SystemExit('Unexpected Plasma source version')
    else:
        source=args.output_dir.resolve()
        subprocess.run([sys.executable,str(PROJECT/'scripts/prepare-native-source.py'),'plasma-workspace',
                        '--output-dir',str(source),'--cache-dir',str(args.cache_dir)],check=True)
    apply(source)
    print(json.dumps({'source':str(source),'nativeShellApi':1}))


if __name__=='__main__':main()
