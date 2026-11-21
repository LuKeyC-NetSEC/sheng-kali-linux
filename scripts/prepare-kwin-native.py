#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare the matching KWin source with native input/gesture changes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[1]
LOCAL=PROJECT/'device/kwin-integration'


def patch_data(name):
    data=(LOCAL/name).read_bytes().replace(b'\r\n',b'\n')
    if name=='tabbox-gestures.patch':
        destination='src/tabbox/tabboxgesture.h'
        lines=(LOCAL/'tabboxgesture.h').read_text(encoding='utf-8').splitlines(True)
        data+=('diff --git a/'+destination+' b/'+destination+'\nnew file mode 100644\n--- /dev/null\n+++ b/'+destination+
               '\n@@ -0,0 +1,'+str(len(lines))+' @@\n'+''.join('+'+line for line in lines)).encode()
    return data


def apply(source):
    names=('input-method-reload.patch','tabbox-gestures.patch','input-method-tests.patch')
    series=source/'debian/patches/series'
    entries=series.read_text().splitlines()
    for name in names:
        filename='sheng-'+name.removesuffix('.patch')+'.diff'
        (series.parent/filename).write_bytes(patch_data(name))
        if filename not in entries:entries.append(filename)
    series.write_text('\n'.join(entries)+'\n')
    subprocess.run(['dpkg-source','--before-build',str(source)],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=PROJECT/'out/kwin-native-source')
    parser.add_argument('--cache-dir',type=Path,default=PROJECT/'out/native-source-downloads/kwin')
    args=parser.parse_args()
    pin=json.loads((LOCAL/'provenance.json').read_text(encoding='utf-8'))
    for name,expected in pin['local_files'].items():
        if hashlib.sha256((LOCAL/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise SystemExit('Review the native KWin source hash: '+name)
    subprocess.run([sys.executable,str(PROJECT/'scripts/prepare-native-source.py'),'kwin','--output-dir',str(args.output_dir),
                    '--cache-dir',str(args.cache_dir)],check=True)
    apply(args.output_dir)
    print(json.dumps({'source':str(args.output_dir),'nativeApiVersion':1}))


if __name__=='__main__':main()
