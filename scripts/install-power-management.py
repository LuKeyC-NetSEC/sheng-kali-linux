#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deploy native PowerDevil packages with backups; no runtime policy daemon."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import subprocess
import time

PROJECT=Path(__file__).resolve().parents[1]
LOCAL=PROJECT/'device/power-management'
STATE=Path('/var/lib/sheng-power-management')
NAMES=('libpowerdevilcore2','powerdevil-data','powerdevil')
VERSION='4:6.7.4-2+sheng4'
POLICY_VERSION=2
DISPLAY_OFF_POLICY_VERSION=2
BASE_VERSION='4:6.7.4-2'


def run(args,**kwargs):
    return subprocess.check_output(args,text=True,**kwargs).strip()


def user(owner,*arguments):
    return ['runuser','-u',owner.pw_name,'--','env',f'XDG_RUNTIME_DIR=/run/user/{owner.pw_uid}',
            f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{owner.pw_uid}/bus',*arguments]


def files(owner):
    return [Path(owner.pw_dir)/'.config'/name for name in ('powerdevilrc','kscreenlockerrc','kwinrc')]+[
        Path('/etc/systemd/sleep.conf.d/50-sheng.conf'),Path('/usr/lib/systemd/system-sleep/60-sheng-desktop'),
        Path('/usr/share/sheng-power-management/native-policy.json'),Path('/usr/bin/sheng-power-status'),
        Path('/usr/libexec/sheng-configure-power-buttons')]


def restore(backup,owner):
    if not backup.resolve().is_relative_to(STATE.resolve()):
        raise RuntimeError('Unexpected backup path')
    subprocess.run(user(owner,'systemctl','--user','stop','plasma-powerdevil.service'),check=True)
    packages=sorted((backup/'packages').glob('*.deb'))
    subprocess.run(['dpkg','--force-confold','--install',*[str(p) for p in packages]],check=True)
    subprocess.run(user(owner,'systemctl','--user','daemon-reload'),check=True)
    manifest=json.loads((backup/'manifest.json').read_text())
    allowed=set(files(owner))
    if any(Path(item['target']) not in allowed for item in manifest):
        raise RuntimeError('Unexpected restore target')
    for index,item in enumerate(manifest):
        target=Path(item['target'])
        if item['exists']:
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(backup/str(index),target);os.chown(target,item['uid'],item['gid'])
        else:
            target.unlink(missing_ok=True)
    previous_install=backup/'previous-install.json'
    if previous_install.exists():
        shutil.copy2(previous_install,STATE/'installed.json')
    else:
        (STATE/'installed.json').unlink(missing_ok=True)
    subprocess.run(user(owner,'systemctl','--user','start','plasma-powerdevil.service'),check=True)
    # Restore the DPMS effect configuration in the existing compositor too.
    # With no running KWin it will instead be read at the next normal login.
    subprocess.run(user(owner,'qdbus6','org.kde.KWin','/KWin','org.kde.KWin.reconfigure'),check=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages',type=Path,help='Directory with the three matched local Debian packages')
    parser.add_argument('--user',default=os.environ.get('SUDO_USER','kali'))
    parser.add_argument('--sleep-mode',choices=('s2idle','deep'),default='s2idle')
    parser.add_argument('--restore',action='store_true')
    args=parser.parse_args()
    if platform.system()!='Linux' or os.geteuid()!=0 or platform.machine()!='aarch64':
        raise SystemExit('Run with sudo on the ARM64 tablet')
    if Path('/sys/firmware/devicetree/base/model').read_bytes().rstrip(b'\0').decode()!='Xiaomi Pad 6S Pro 12.4':
        raise SystemExit('This installer is scoped to sheng')
    if run(['dpkg-query','-W','-f=${Version}','libqt6core6t64:arm64'])!='6.11.2+dfsg-5':
        raise SystemExit('Rebuild native PowerDevil for this Qt ABI first')
    owner=pwd.getpwnam(args.user)
    if owner.pw_uid==0 or not Path(f'/run/user/{owner.pw_uid}/bus').exists():
        raise SystemExit('An existing desktop user session is required')
    if args.restore:
        restore(Path((STATE/'last-backup').read_text().strip()),owner);return
    if not args.packages:parser.error('--packages is required')
    dev_status=subprocess.run(['dpkg-query','-W','-f=${db:Status-Status}','powerdevil-dev'],text=True,capture_output=True)
    names=NAMES+(('powerdevil-dev',) if dev_status.stdout.strip()=='installed' else ())
    modes=Path('/sys/power/mem_sleep').read_text().replace('[','').replace(']','').split()
    if args.sleep_mode not in modes:raise SystemExit('Sleep mode is not exposed by this kernel')
    candidates={}
    for candidate in args.packages.resolve().glob('*.deb'):
        name=run(['dpkg-deb','-f',str(candidate),'Package'])
        if name in names and run(['dpkg-deb','-f',str(candidate),'Version'])==VERSION:
            if name in candidates:raise SystemExit('Duplicate package: '+name)
            architecture=run(['dpkg-deb','-f',str(candidate),'Architecture'])
            if architecture!=('all' if name=='powerdevil-data' else 'arm64'):
                raise SystemExit('Package architecture mismatch: '+name)
            candidates[name]=candidate
    if set(candidates)!=set(names):raise SystemExit('Expected matched native PowerDevil packages, including dev if installed')
    hook=Path('/usr/lib/systemd/system-sleep/60-sheng-desktop')
    if hook.exists() and hashlib.sha256(hook.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=json.loads((LOCAL/'provenance.json').read_text())['legacy_sleep_hook_sha256']:
        raise SystemExit('Desktop sleep hook has local changes; review before replacing it')
    STATE.mkdir(mode=0o700,exist_ok=True);STATE.chmod(0o700)
    backup=STATE/('backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir(mode=0o700)
    if (STATE/'installed.json').is_file():
        shutil.copy2(STATE/'installed.json',backup/'previous-install.json')
    packages=backup/'packages';packages.mkdir()
    previous={name:run(['dpkg-query','-W','-f=${Version}',name]) for name in names}
    for name,version in previous.items():
        if version==BASE_VERSION:
            subprocess.run(['apt-get','download',name+'='+version],cwd=packages,check=True)
        elif version in ('4:6.7.4-2+sheng1','4:6.7.4-2+sheng2','4:6.7.4-2+sheng3',VERSION):
            cached=[path for path in (STATE/'installed-packages').glob('*.deb')
                    if run(['dpkg-deb','-f',str(path),'Package'])==name
                    and run(['dpkg-deb','-f',str(path),'Version'])==version]
            if len(cached)!=1:raise SystemExit('Missing or ambiguous cached rollback package: '+name)
            saved=json.loads((STATE/'installed.json').read_text())
            if hashlib.sha256(cached[0].read_bytes()).hexdigest()!=saved['packages'][name]:
                raise SystemExit('Cached rollback package hash mismatch: '+name)
            shutil.copy2(cached[0],packages/cached[0].name)
        else:raise SystemExit('Installed package version is outside the reviewed ABI: '+name)
    manifest=[]
    for index,target in enumerate(files(owner)):
        item={'target':str(target),'exists':target.is_file()}
        if item['exists']:
            metadata=target.stat();item.update(uid=metadata.st_uid,gid=metadata.st_gid)
            shutil.copy2(target,backup/str(index))
        manifest.append(item)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (backup/'versions.json').write_text(json.dumps(previous,indent=2)+'\n')
    (STATE/'last-backup').write_text(str(backup)+'\n')
    battery_inode=Path('/sys/class/power_supply/qcom-battmgr-bat').stat().st_ino
    try:
        subprocess.run(user(owner,'systemctl','--user','stop','plasma-powerdevil.service'),check=True)
        subprocess.run(['dpkg','--force-confold','--install',*[str(candidates[name]) for name in names]],check=True)
        subprocess.run(user(owner,'systemctl','--user','daemon-reload'),check=True)
        hook.unlink(missing_ok=True) # C++ replaces this exact known legacy hook.
        target=Path('/etc/systemd/sleep.conf.d/50-sheng.conf');target.parent.mkdir(parents=True,exist_ok=True)
        text=(PROJECT/'device/50-sheng-sleep.conf').read_text(encoding='utf-8')
        target.write_text('\n'.join('MemorySleepMode='+args.sleep_mode if line.startswith('MemorySleepMode=') else line
                                    for line in text.splitlines())+'\n');target.chmod(0o644)
        marker=Path('/usr/share/sheng-power-management/native-policy.json');marker.parent.mkdir(parents=True,exist_ok=True)
        marker.write_text(json.dumps({'packageVersion':VERSION,'policyVersion':POLICY_VERSION})+'\n');marker.chmod(0o644)
        shutil.copyfile(LOCAL/'power-status.py','/usr/bin/sheng-power-status');Path('/usr/bin/sheng-power-status').chmod(0o755)
        shutil.copyfile(PROJECT/'scripts/configure-power-buttons.sh','/usr/libexec/sheng-configure-power-buttons')
        Path('/usr/libexec/sheng-configure-power-buttons').chmod(0o755)
        subprocess.run(user(owner,'systemctl','--user','start','plasma-powerdevil.service'),check=True)
        deadline=time.monotonic()+30
        while run(user(owner,'kreadconfig6','--file','powerdevilrc','--group','ShengPower','--key','PolicyVersion'))!=str(POLICY_VERSION):
            if time.monotonic()>deadline:raise RuntimeError('Native policy did not initialize')
            time.sleep(0.25)
        while run(user(owner,'kreadconfig6','--file','powerdevilrc','--group','ShengPower','--key','DisplayOffPolicyVersion'))!=str(DISPLAY_OFF_POLICY_VERSION):
            if time.monotonic()>deadline:raise RuntimeError('Native direct-display-off policy did not initialize')
            time.sleep(0.25)
        pid=int(run(user(owner,'systemctl','--user','show','plasma-powerdevil.service','-p','MainPID','--value')))
        library=Path('/usr/lib/aarch64-linux-gnu/libpowerdevilcore.so.6.7.4')
        mapped=[line.split() for line in Path(f'/proc/{pid}/maps').read_text().splitlines() if 'libpowerdevilcore.so' in line]
        if not mapped or any('(deleted)' in ' '.join(row) or int(row[4])!=library.stat().st_ino for row in mapped):
            raise RuntimeError('PowerDevil is not using the installed native library')
        if Path('/sys/class/power_supply/qcom-battmgr-bat').stat().st_ino!=battery_inode:
            raise RuntimeError('Unexpected battery provider replacement')
    except Exception:
        restore(backup,owner);raise
    cache=STATE/'installed-packages';cache.mkdir(exist_ok=True)
    for package in candidates.values():shutil.copy2(package,cache/package.name)
    report={'nativePackageVersion':VERSION,'sleepMode':args.sleep_mode,'nativePolicyVersion':POLICY_VERSION,
            'displayOffPolicyVersion':DISPLAY_OFF_POLICY_VERSION,
            'legacyDesktopSleepHookRemoved':not hook.exists(),'batteryProviderRetained':True,
            'coreLibrarySha256':hashlib.sha256(library.read_bytes()).hexdigest(),
            'packages':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in candidates.items()},
            'backup':str(backup)}
    (STATE/'installed.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
