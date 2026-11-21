#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-time package migration; never a runtime desktop policy."""
import datetime
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import signal
import subprocess
import sys


def run(arguments,check=True):
    return subprocess.run(arguments,text=True,capture_output=True,check=check)


def main():
    if os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().find(b'xiaomi,sheng')<0:
        raise SystemExit('Run as root on sheng during native package deployment')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('guard_id')
    parser.add_argument('--backup-only',action='store_true')
    parser.add_argument('--task-effect-id')
    args=parser.parse_args();guard_id=args.guard_id
    if not re.fullmatch(r'sheng_desktop_touch_guard_[a-f0-9]{12}',guard_id):
        raise SystemExit('Unexpected native guard ID')
    effect_id=args.task_effect_id
    if effect_id and not re.fullmatch(r'sheng-task-cards-[a-f0-9]{12}',effect_id):
        raise SystemExit('Unexpected native task effect ID')
    for package in (() if args.backup_only else ('kwin-wayland','plasma-workspace')):
        if run(['dpkg-query','-W','-f=${Version}',package]).stdout.strip()!='4:6.7.4-2+sheng1':
            raise SystemExit('Install the matched native KWin and Plasma packages first')
    input_package=run(['dpkg-query','-W','-f=${db:Status-Status}','sheng-msime-integration'],False)
    if not args.backup_only and input_package.returncode==0 and input_package.stdout.strip() not in ('not-installed','config-files'):
        launcher=run(['/usr/bin/fcitx5-osk-kwin-launcher','--sheng-native-version'],False)
        if launcher.returncode or launcher.stdout.strip()!='kwin-api=1 input-context=2 visibility-policy=1':
            raise SystemExit('Unpack the native input launcher before retiring its old policy')
    owner=pwd.getpwnam('kali');owner_root=Path(owner.pw_dir)
    if owner.pw_uid!=1000:raise SystemExit('Review fixed user ownership for this deployment')
    user=['runuser','-u',owner.pw_name,'--','env','XDG_RUNTIME_DIR=/run/user/1000',
          'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus']
    plugin_root=Path('/usr/lib/aarch64-linux-gnu/qt6/plugins/kwin/effects/plugins')
    if not args.backup_only and not (plugin_root/(guard_id+'.so')).is_file():raise SystemExit('Missing native touch plugin')
    paths=[Path(name) for name in (
        '/usr/libexec/sheng-desktop-policy','/usr/libexec/sheng-keyboard-policy.py',
        '/usr/libexec/sheng-fcitx-keyboard-policy.py','/usr/libexec/sheng-desktop-resume.py',
        '/usr/libexec/sheng-set-screen-lock-timeout','/usr/libexec/sheng-task-gestures',
        '/usr/lib/systemd/user/sheng-desktop-policy.service','/usr/lib/systemd/user/sheng-keyboard-policy.service',
        '/usr/lib/systemd/user/sheng-keyboard-policy.service.d/50-msime.conf',
        '/usr/lib/systemd/user/graphical-session.target.wants/sheng-keyboard-policy.service',
        '/etc/systemd/system/sheng-task-gestures.service','/etc/udev/rules.d/83-sheng-task-gestures.rules',
        '/usr/lib/systemd/system-sleep/60-sheng-desktop')]
    for target in ('graphical-session.target','plasma-workspace.target'):
        for unit in ('sheng-keyboard-policy.service','sheng-desktop-policy.service'):
            paths.append(owner_root/'.config/systemd/user'/(target+'.wants')/unit)
    for unit in ('sheng-keyboard-policy.service','sheng-desktop-policy.service'):
        paths.append(owner_root/'.config/systemd/user'/unit)
    activation=owner_root/'.local/share/dbus-1/services/org.sheng.DesktopPolicy.service'
    if activation.is_file() and 'sheng-desktop-policy' in activation.read_text():paths.append(activation)
    paths += [p for p in plugin_root.glob('sheng_desktop_touch_guard_*.so')
              if re.fullmatch(r'sheng_desktop_touch_guard_[a-f0-9]{12}\.so',p.name) and p.stem!=guard_id]
    widgets=owner_root/'.local/share/plasma/plasmoids'
    old_widgets=[]
    if widgets.is_dir():
        if not widgets.resolve().is_relative_to(owner_root.resolve()):raise SystemExit('Review the redirected widget directory')
        for path in widgets.glob('org.sheng.desktop-gesture*'):
            if path.is_symlink():old_widgets.append(path)
            elif path.is_dir() and path.resolve().is_relative_to(widgets.resolve()):old_widgets.append(path)
    old_effects=[]
    for directory in (owner_root/'.local/share/kwin-wayland/effects',owner_root/'.local/share/kwin/effects',Path('/usr/share/kwin-wayland/effects')):
        if not directory.is_dir():continue
        for path in directory.glob('sheng-task-cards-*'):
            if path.name==effect_id or not re.fullmatch(r'sheng-task-cards-[a-f0-9]{12}',path.name):continue
            if path.is_symlink() or (path.is_dir() and path.resolve().is_relative_to(directory.resolve())):old_effects.append(path)
    state=Path('/var/lib/sheng-native-session');state.mkdir(mode=0o700,exist_ok=True);state.chmod(0o700)
    backup=state/('backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'));backup.mkdir(mode=0o700)
    manifest=[]
    configuration=[owner_root/'.config'/name for name in ('kwinrc','plasma-org.kde.plasma.desktop-appletsrc','plasmashellrc')]
    for index,path in enumerate(paths+old_widgets+old_effects+configuration):
        if not path.exists() and not path.is_symlink():continue
        item={'target':str(path),'backup':str(index),'configuration':path in configuration}
        info=path.lstat();item.update(uid=info.st_uid,gid=info.st_gid,mode=stat.S_IMODE(info.st_mode))
        if path.is_symlink():
            item['symlink']=os.readlink(path)
        elif path.is_dir():shutil.copytree(path,backup/str(index),symlinks=True)
        else:shutil.copy2(path,backup/str(index))
        manifest.append(item)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (state/('pre-deployment-backup' if args.backup_only else 'last-backup')).write_text(str(backup)+'\n')
    if args.backup_only:
        print(json.dumps({'backupOnly':True,'filesPreserved':len(manifest),'servicesChanged':False}))
        return
    # APT has already unpacked the replacement files. Stop only superseded
    # helpers; the compositor, shell, applications and lockscreen stay alive.
    run(['systemctl','disable','--now','sheng-task-gestures.service'],False)
    for unit in ('sheng-keyboard-policy.service','sheng-desktop-policy.service'):
        run(user+['systemctl','--user','stop',unit],False)
        run(user+['systemctl','--user','disable',unit],False)
        if run(user+['systemctl','--user','is-active','--quiet',unit],False).returncode==0:
            raise RuntimeError('Legacy policy did not stop: '+unit)
    retired_launchers=0
    launcher=Path('/usr/bin/fcitx5-osk-kwin-launcher')
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:
            if process.stat().st_uid!=owner.pw_uid:continue
            executable=os.readlink(process/'exe').removesuffix(' (deleted)')
            arguments=(process/'cmdline').read_bytes().split(b'\0')
            if executable!=str(launcher) or b'--dbus-server' not in arguments:continue
            if (process/'exe').stat().st_ino==launcher.stat().st_ino:continue
            identity=(process/'stat').read_text().rsplit(')',1)[1].split()[19]
            if (process/'stat').read_text().rsplit(')',1)[1].split()[19]!=identity:continue
            os.kill(int(process.name),signal.SIGTERM);retired_launchers+=1
        except (OSError,IndexError):continue
    for path in paths:path.unlink(missing_ok=True)
    for path in old_widgets:
        if path.is_symlink():path.unlink()
        elif path.resolve().is_relative_to(widgets.resolve()):shutil.rmtree(path)
    for path in old_effects:
        if path.is_symlink():path.unlink()
        elif path.resolve().is_relative_to(path.parent.resolve()):shutil.rmtree(path)
    import configparser
    config=configparser.ConfigParser(interpolation=None,strict=False);config.optionxform=str
    config.read(owner_root/'.config/kwinrc')
    previous=list(config['Plugins']) if config.has_section('Plugins') else []
    for key in previous:
        if key.startswith(('sheng_desktop_touch_guard_','sheng-task-cards-')) and key.endswith('Enabled'):
            run(user+['kwriteconfig6','--file','kwinrc','--group','Plugins','--key',key,'false'])
    run(user+['kwriteconfig6','--file','kwinrc','--group','Plugins','--key',guard_id+'Enabled','true'])
    if effect_id:run(user+['kwriteconfig6','--file','kwinrc','--group','Plugins','--key',effect_id+'Enabled','true'])
    run(['systemctl','daemon-reload']);run(['udevadm','control','--reload-rules'])
    run(user+['systemctl','--user','daemon-reload'],False)
    run(user+['systemctl','--user','reset-failed','sheng-desktop-policy.service','sheng-keyboard-policy.service'],False)
    run(user+['dbus-send','--session','--print-reply','--dest=org.freedesktop.DBus','/org/freedesktop/DBus',
              'org.freedesktop.DBus.ReloadConfig'],False)
    existing={item['target'] for item in manifest}
    print(json.dumps({'legacyFilesRemoved':sum(str(path) in existing for path in paths),'legacyWidgetsRemoved':len(old_widgets),
                      'legacyEffectsRemoved':len(old_effects),
                      'legacyLauncherServersRetired':retired_launchers,
                      'newGuard':guard_id,'sessionRestarted':False,'requiresNormalLogin':True}))


if __name__=='__main__':main()
