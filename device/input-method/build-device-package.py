#!/usr/bin/env python3
"""Package the pinned Fcitx5 OSK staging tree with the tablet integration."""
import pathlib
import shutil
import subprocess
import sys

source = pathlib.Path(__file__).resolve().parent
stage = pathlib.Path(sys.argv[1]).resolve()
guard = pathlib.Path(sys.argv[2]).resolve()
output = pathlib.Path(sys.argv[3]).resolve()
assert (stage/'usr/bin/fcitx5-osk').is_file()
old = stage/'usr/lib/aarch64-linux-gnu/systemd/system/fcitx5-osk-key-helper.service'
target = stage/'usr/lib/systemd/system/fcitx5-osk-key-helper.service'
target.parent.mkdir(parents=True,exist_ok=True)
if old.exists(): old.rename(target)
for original,relative,mode in [
    (source/'sheng-msime-launcher','usr/libexec/sheng-msime-launcher',0o755),
    (source/'sheng-msime-fcitx5.desktop','usr/share/applications/sheng-msime-fcitx5.desktop',0o644),
    (source/'82-sheng-osk.rules','etc/udev/rules.d/82-sheng-osk.rules',0o644),
    (guard,'usr/libexec/sheng-fcitx-keyboard-policy.py',0o644),
    (source/'50-msime-keyboard-policy.conf','usr/lib/systemd/user/sheng-keyboard-policy.service.d/50-msime.conf',0o644),
]:
    destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(original,destination);destination.chmod(mode)
control=stage/'DEBIAN';control.mkdir(exist_ok=True)
(control/'control').write_text('''Package: sheng-msime-integration
Version: 0.2.1-2
Architecture: arm64
Maintainer: Sheng tablet local setup
Depends: msime-linux (>= 0.16.1), fcitx5, libc6 (>= 2.38), libgcc-s1, libssl3t64, libwayland-client0, libxkbcommon0, libfontconfig1, libegl1, libvulkan1, python3-dbus, python3-gi, qdbus-qt6, xdg-desktop-portal, xdg-desktop-portal-kde
Description: Water杉 input and touch keyboard integration for sheng
 Pinned Fcitx5 OSK with physical-keyboard suppression and KWin launcher.
''')
(control/'postinst').write_text('''#!/bin/sh
set -e
if [ "$1" = configure ]; then
    udevadm control --reload-rules || true
    systemctl daemon-reload
    systemctl enable --now fcitx5-osk-key-helper.service
    if [ -S /run/user/1000/bus ]; then
        runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user daemon-reload
        runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user restart sheng-keyboard-policy.service
    fi
fi
''')
(control/'postinst').chmod(0o755)
(control/'prerm').write_text('''#!/bin/sh
set -e
if [ "$1" = remove ]; then
    systemctl disable --now fcitx5-osk-key-helper.service || true
    if [ -S /run/user/1000/bus ]; then
        method=$(runuser -u kali -- kreadconfig6 --file kwinrc --group Wayland --key InputMethod)
        case "$method" in
          */sheng-msime-fcitx5.desktop)
            runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus kwriteconfig6 --file kwinrc --group Wayland --key InputMethod --notify /usr/share/applications/org.kde.plasma.keyboard.desktop
            ;;
        esac
        runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus qdbus6 fyi.fortime.Fcitx5Osk /fyi/fortime/Fcitx5Osk/Controller fyi.fortime.Fcitx5Osk.Controller1.Shutdown >/dev/null 2>&1 || true
    fi
fi
''')
(control/'prerm').chmod(0o755)
(control/'postrm').write_text('''#!/bin/sh
systemctl daemon-reload || true
if [ "$1" = remove ] && [ -S /run/user/1000/bus ]; then
    runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user daemon-reload || true
    runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user restart sheng-keyboard-policy.service || true
fi
''')
(control/'postrm').chmod(0o755)
output.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(output)],check=True)
print(output)
