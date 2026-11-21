#!/usr/bin/env python3
"""Build the tablet policy package on Linux from the device/ source tree."""
import argparse
import pathlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import json
import zipfile

here = pathlib.Path(__file__).resolve().parent
privacy = here.parent/'privacy'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('binary',type=pathlib.Path)
parser.add_argument('output',type=pathlib.Path)
parser.add_argument('--touch-guard-build',type=pathlib.Path,required=True)
args=parser.parse_args()
binary = args.binary.resolve()
output = args.output.resolve()
header=binary.read_bytes()[:20]
if header[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(header[18:20],'little')!=183:
    raise SystemExit('Expected a compiled ARM64 privacy helper')
guard_build=args.touch_guard_build.resolve()
guard_id=(guard_build/'touch-guard-id.txt').read_text().strip()
if not re.fullmatch(r'sheng_desktop_touch_guard_[a-f0-9]{12}',guard_id):
    raise SystemExit('Unexpected native touch plugin ID')
guard_bytes=(guard_build/(guard_id+'.so')).read_bytes()
if guard_bytes[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(guard_bytes[18:20],'little')!=183 or b'GetInputContext' not in guard_bytes or b'ControlCenterVisible' not in guard_bytes:
    raise SystemExit('Rebuild the native context/gesture plugin first')
output.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='sheng-tablet-controls-package-') as directory:
    stage = pathlib.Path(directory)
    files = [
        (here.parents[1]/'scripts/install-desktop-drawer.py','usr/bin/sheng-desktop-drawer-setup',0o755),
        (privacy/'privacy-control.py','usr/libexec/sheng-privacyctl',0o755),
        (privacy/'privacy-client.py','usr/bin/sheng-privacy',0o755),
        (binary,'usr/libexec/sheng-privacy-bpf',0o755),
        (privacy/'sheng-privacy@.service','etc/systemd/system/sheng-privacy@.service',0o644),
        (privacy/'sheng-privacy-restore.service','etc/systemd/system/sheng-privacy-restore.service',0o644),
        (privacy/'99-sheng-privacy.rules','etc/udev/rules.d/99-sheng-privacy.rules',0o644),
        (privacy/'51-sheng-privacy.rules','etc/polkit-1/rules.d/51-sheng-privacy.rules',0o644),
        (privacy/'README.md','usr/share/doc/sheng-tablet-controls/privacy.md',0o644),
        (here/'README.md','usr/share/doc/sheng-tablet-controls/desktop.md',0o644),
        (here.parent/'recents/LICENSE','usr/share/doc/sheng-tablet-controls/copyright',0o644),
        (here.parent/'plasma-integration/migrate-installed.py','usr/libexec/sheng-native-session-migrate',0o755),
    ]
    files.append((here.parent/'plasma-integration/org.sheng.DesktopPolicy.service',
                  'usr/share/dbus-1/services/org.sheng.DesktopPolicy.service',0o644))
    files.append((here.parent/'recents/install-native-tabbox.py','usr/libexec/sheng-native-tabbox-setup',0o755))
    for source,relative,mode in files:
        target = stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target);target.chmod(mode)
    subprocess.run(['cmake','--install',str(guard_build)],env={**os.environ,'DESTDIR':str(stage)},check=True)
    marker=stage/'usr/share/sheng-native-session/guard-id';marker.parent.mkdir(parents=True,exist_ok=True)
    marker.write_text(guard_id+'\n')
    # Package the effect from current source, including removal of its old
    # Python-policy publisher. No legacy user effect should load beside it.
    effect_output=stage/'effect-build'
    subprocess.run([sys.executable,str(here.parents[1]/'scripts/build-task-cards.py'),
                    '--output-dir',str(effect_output)],check=True,stdout=subprocess.DEVNULL)
    manifest=json.loads(next(effect_output.glob('*.manifest.json')).read_text())
    effect_id=manifest['id']
    if not re.fullmatch(r'sheng-task-cards-[a-f0-9]{12}',effect_id):raise SystemExit('Unexpected effect ID')
    with zipfile.ZipFile(effect_output/manifest['artifact']) as archive:
        destination=stage/'usr/share/kwin-wayland/effects'/effect_id
        for name in archive.namelist():
            relative=pathlib.PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts:raise SystemExit('Unsafe effect path')
            target=destination.joinpath(*relative.parts);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(name))
    if not effect_output.resolve().is_relative_to(stage.resolve()):raise SystemExit('Effect staging escaped package root')
    shutil.rmtree(effect_output)
    marker.with_name('effect-id').write_text(effect_id+'\n')
    for bus in ['system','session']:
        target = stage/('etc/dbus-1/'+bus+'.d/51-sheng-privacy.conf')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text('<busconfig>\n</busconfig>\n')
    control = stage/'DEBIAN';control.mkdir()
    metadata='''Package: sheng-tablet-controls
Version: 1.0-8+native1
Architecture: arm64
Conflicts: sheng-task-gestures
Replaces: sheng-task-gestures
Maintainer: Sheng tablet local setup
Depends: libc6 (>= 2.38), python3, python3-dbus, python3-gi, systemd, udev, polkitd, dbus, qdbus-qt6, alsa-utils, pulseaudio-utils, pipewire-bin, plasma-workspace (= 4:6.7.4-2+sheng1), kwin-wayland (= 4:6.7.4-2+sheng1), plasma-desktop, qml6-module-org-kde-plasma-workspace, kpackagetool6
Description: Dock, desktop gesture and process-level sensor privacy for sheng
 Includes the Linexin setup helper and uses a cgroup BPF device guard.
'''
    (control/'control').write_text(metadata)
    (control/'conffiles').write_text('\n'.join('/'+relative for _,relative,_ in files if relative.startswith('etc/'))+'\n/etc/dbus-1/system.d/51-sheng-privacy.conf\n/etc/dbus-1/session.d/51-sheng-privacy.conf\n')
    scripts = {
        'postinst': '''#!/bin/sh
set -e
if [ "$1" = configure ]; then
    udevadm control --reload-rules || true
    systemctl daemon-reload
    systemctl disable --now sheng-task-gestures.service || true
    systemctl enable sheng-privacy-restore.service
    systemctl start sheng-privacy-restore.service
    /usr/libexec/sheng-native-session-migrate "$(cat /usr/share/sheng-native-session/guard-id)" --task-effect-id "$(cat /usr/share/sheng-native-session/effect-id)"
    if [ -S /run/user/1000/bus ]; then
        runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user daemon-reload
        runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user stop sheng-desktop-policy.service || true
    fi
fi
''',
        'prerm': '''#!/bin/sh
set -e
if [ "$1" = remove ]; then
    /usr/libexec/sheng-privacyctl off
    systemctl disable sheng-privacy-restore.service || true
    if [ -S /run/user/1000/bus ]; then
        runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user disable --now sheng-desktop-policy.service || true
    fi
fi
''',
        'postrm': '''#!/bin/sh
systemctl daemon-reload || true
udevadm control --reload-rules || true
''',
    }
    for name,text in scripts.items():
        target = control/name;target.write_text(text);target.chmod(0o755)
    subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(output)],check=True)
print(output)
