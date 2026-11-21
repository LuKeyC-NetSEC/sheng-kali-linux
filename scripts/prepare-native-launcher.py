#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply the pinned native input-policy migration to an existing OSK source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
LOCAL = PROJECT / 'device/input-method'


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Source from prepare-osk-ui.py; preserves existing FUTO UI')
    args = parser.parse_args()
    source = args.source.resolve()
    pin = json.loads((LOCAL / 'provenance.json').read_text(encoding='utf-8'))
    patch = LOCAL / 'native-launcher.patch'
    if digest(patch) != pin['native_launcher_patch_sha256']:
        raise SystemExit('Native launcher patch changed; review provenance')
    for name, expected in pin['native_launcher_files'].items():
        if digest(LOCAL / name) != expected:
            raise SystemExit('Native launcher source changed: ' + name)
    launcher = source / 'fcitx5-osk-kwin-launcher/src'
    for name, expected in pin['native_launcher_base_files'].items():
        if digest(launcher / name) != expected:
            raise SystemExit('Unexpected launcher base; select a fresh source tree: ' + name)
    data = patch.read_bytes().replace(b'\r\n', b'\n')
    subprocess.run(['git', 'apply', '--check', '-'], input=data, cwd=source, check=True)
    subprocess.run(['git', 'apply', '-'], input=data, cwd=source, check=True)
    shutil.copyfile(LOCAL / 'native-policy.rs', launcher / 'native_policy.rs')
    print(json.dumps({'source': str(source), 'nativePolicy': True, 'requiredKwinApi': 1, 'requiredInputContextApi': 2}))


if __name__ == '__main__':
    main()
