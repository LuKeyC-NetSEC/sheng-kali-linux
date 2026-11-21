#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install a locally built PIN package; optional reload preserves the battery provider."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time


def run(args):
    return subprocess.check_output(args, text=True).strip()


def battery_instance():
    return tuple(Path(p).stat().st_ino for p in ('/sys/module/qcom_battmgr', '/sys/class/power_supply/qcom-battmgr-bat'))


def capacity():
    try:
        return int(Path('/sys/class/power_supply/qcom-battmgr-bat/capacity').read_text())
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--reload', action='store_true', help='Reload only the PIN module in the current session')
    args = parser.parse_args()
    abi = '7.3.4-sm8550-00104-g87ac0f2347eb'
    if platform.system() != 'Linux' or os.geteuid() != 0 or platform.machine() != 'aarch64' or platform.release() != abi:
        raise SystemExit('Run with sudo on the matching ARM64 tablet kernel')
    package = args.package.resolve()
    if run(['dpkg-deb','-f',str(package),'Package']) != 'sheng-dock-fix':
        raise SystemExit('Expected a sheng-dock-fix package')
    relative = Path('lib/modules')/abi/'kernel/drivers/hid/hid-nanosic-wn8030.ko.zst'
    with tempfile.TemporaryDirectory(prefix='sheng-pin-verify-') as temporary:
        subprocess.run(['dpkg-deb','-x',str(package),temporary],check=True)
        candidate = Path(temporary)/relative
        if (run(['modinfo','-F','vermagic',str(candidate)]).split()[0] != abi
                or run(['modinfo','-F','version',str(candidate)]) != '1.3.1-shengfix'):
            raise SystemExit('Package module ABI/version mismatch')
    before = battery_instance() if args.reload else None
    before_percent = capacity()
    state = Path('/var/lib/sheng-pin-installer')
    state.mkdir(mode=0o700,exist_ok=True); state.chmod(0o700)
    backup = state/('backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700)
    targets = [Path('/')/relative, Path('/etc/systemd/system/sheng-devauth.service'),
               Path('/etc/udev/rules.d/80-sheng-devauth.rules')]
    for path in targets:
        if path.is_file(): shutil.copy2(path,backup/path.name)
    previous = subprocess.run(['dpkg-query','-W','-f=${Version}','sheng-dock-fix'],text=True,capture_output=True)
    (backup/'previous.json').write_text(json.dumps({'packageVersion':previous.stdout.strip(),
        'moduleVersion':Path('/sys/module/hid_nanosic_wn8030/version').read_text().strip()
            if Path('/sys/module/hid_nanosic_wn8030/version').exists() else None},indent=2)+'\n')
    (state/'last-backup').write_text(str(backup)+'\n')
    removed = False
    try:
        subprocess.run(['dpkg','--force-confnew','--install',str(package)],check=True)
        if args.reload:
            subprocess.run(['systemctl','stop','sheng-devauth.service'],check=True)
            # modprobe -r also removes unused dependencies, including qcom_battmgr.
            # rmmod removes exactly one module: the battery device must survive.
            subprocess.run(['rmmod','hid_nanosic_wn8030'],check=True)
            removed = True
            if battery_instance() != before: raise RuntimeError('Battery provider changed during PIN removal')
            subprocess.run(['modprobe','hid_nanosic_wn8030'],check=True)
            deadline = time.monotonic()+15
            while subprocess.run(['systemctl','is-active','--quiet','sheng-devauth.service']).returncode:
                if time.monotonic() >= deadline: raise RuntimeError('Automatic authentication startup timed out')
                time.sleep(0.1)
            if battery_instance() != before: raise RuntimeError('Battery provider changed during PIN load')
    except Exception:
        subprocess.run(['systemctl','stop','sheng-devauth.service'],check=False)
        if removed and Path('/sys/module/hid_nanosic_wn8030').exists():
            subprocess.run(['rmmod','hid_nanosic_wn8030'],check=False)
        for path in targets:
            saved=backup/path.name
            if saved.is_file(): shutil.copy2(saved,path)
        subprocess.run(['depmod',abi],check=False)
        subprocess.run(['systemctl','daemon-reload'],check=False)
        subprocess.run(['modprobe','hid_nanosic_wn8030'],check=False)
        subprocess.run(['systemctl','start','sheng-devauth.service'],check=False)
        raise
    result={'kernel':abi,'packageVersion':run(['dpkg-query','-W','-f=${Version}','sheng-dock-fix']),
            'moduleVersion':Path('/sys/module/hid_nanosic_wn8030/version').read_text().strip()
                if Path('/sys/module/hid_nanosic_wn8030/version').exists() else None,
            'reloaded':args.reload,'batteryProviderRetained':battery_instance()==before if args.reload else None,
            'batteryPercentBefore':before_percent,'batteryPercentAfter':capacity(),
            'packageSha256':hashlib.sha256(package.read_bytes()).hexdigest()}
    (state/'installed.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
