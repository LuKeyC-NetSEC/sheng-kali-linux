#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Back up and install a complete, pinned sheng Mesa runtime package set."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parents[1]


def query(*command):
    return subprocess.check_output(command, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package_dir', type=Path)
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0 or query('dpkg', '--print-architecture') != 'arm64':
        raise SystemExit('Run as root on the ARM64 target')
    model = Path('/sys/firmware/devicetree/base/model').read_text().rstrip('\0')
    if 'Xiaomi Pad 6S Pro' not in model:
        raise SystemExit('This installer is limited to Xiaomi Pad 6S Pro')
    pin = json.loads((PROJECT / 'device/gpu-driver/provenance.json').read_text())
    packages = {}
    for path in args.package_dir.resolve().glob('*.deb'):
        name = query('dpkg-deb', '-f', str(path), 'Package')
        if name not in pin['packages']:
            continue
        if name in packages:
            raise SystemExit('Duplicate package: ' + name)
        if query('dpkg-deb', '-f', str(path), 'Version') != pin['packageVersion']:
            raise SystemExit('Package version mismatch: ' + name)
        if query('dpkg-deb', '-f', str(path), 'Architecture') != 'arm64':
            raise SystemExit('Package architecture mismatch: ' + name)
        packages[name] = path
    if set(packages) != set(pin['packages']):
        raise SystemExit('Incomplete package set')
    # Require an actual successful staged rendering test with this exact package set.
    report_path = args.package_dir.resolve() / 'smoke-stage/validation.json'
    report = json.loads(report_path.read_text())
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in packages.items()}
    if (report.get('version') != pin['version'] or not report.get('identicalReadback')
            or not report.get('stage') or report.get('packageHashes') != hashes):
        raise SystemExit('Missing successful staged validation bound to these package hashes')
    if ('FD740' not in report['runs']['freedreno']['renderer']
            or 'Turnip' not in report['runs']['turnip']['renderer']
            or 'zink' not in report['runs']['zink']['renderer'].lower()):
        raise SystemExit('Staged validation did not use the requested hardware paths')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = args.backup_dir or Path('/var/lib/sheng-mesa-backup') / stamp
    backup.mkdir(parents=True, exist_ok=False)
    installed = {}
    selected = []
    for name, package in packages.items():
        result = subprocess.run(['dpkg-query', '-W', '-f=${db:Status-Abbrev} ${Version}', name],
                                capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.startswith('ii '):
            installed[name] = result.stdout.split(maxsplit=1)[1].strip()
            subprocess.run(['dpkg-repack', name], cwd=backup, check=True)
        elif name in ('mesa-common-dev', 'libgbm-dev'):
            continue
        selected.append(str(package))
    manifest = {'model': model, 'kernel': query('uname', '-r'), 'before': installed,
                'after': pin['packageVersion'], 'packageHashes': hashes}
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    env = dict(os.environ, LC_ALL='C', DEBIAN_FRONTEND='noninteractive')
    subprocess.run(['apt-get', '-s', '--no-remove', 'install', *selected], env=env, check=True)
    subprocess.run(['apt-get', '-y', '--no-install-recommends', '--no-remove', 'install', *selected],
                   env=env, check=True)
    print(json.dumps({'installed': pin['packageVersion'], 'backup': str(backup),
                      'sessionRestarted': False}))


if __name__ == '__main__':
    main()
