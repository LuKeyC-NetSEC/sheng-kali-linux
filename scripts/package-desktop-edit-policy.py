#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package an already compiled ARM64 native Plasma editing component."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

PROJECT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();build=args.build.resolve()
    plugin=(build/'policy-id.txt').read_text().strip()
    if not re.fullmatch(r'org\.sheng\.desktopeditpolicy\.[a-f0-9]{12}',plugin):raise SystemExit('Unexpected plugin ID')
    header=(build/(plugin+'.so')).read_bytes()[:20]
    if header[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(header[18:20],'little')!=183:raise SystemExit('Build ARM64 ELF first')
    version=subprocess.check_output(['dpkg-query','-W','-f=${Version}','libqt6core6t64:arm64'],text=True).strip()
    if version!='6.11.2+dfsg-5':raise SystemExit('Review this Qt ABI before packaging')
    with tempfile.TemporaryDirectory(prefix='sheng-desktop-edit-package-') as temporary:
        stage=Path(temporary)
        subprocess.run(['cmake','--install',str(build)],env={**os.environ,'DESTDIR':str(stage)},check=True)
        marker=stage/'usr/share/sheng-desktop-edit-policy/policy-id.txt';marker.parent.mkdir(parents=True,exist_ok=True)
        marker.write_text(plugin+'\n')
        setup=stage/'usr/libexec/sheng-desktop-edit-policy-setup';setup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PROJECT/'scripts/install-desktop-edit-policy.py',setup);setup.chmod(0o755)
        documentation=stage/'usr/share/doc/sheng-desktop-edit-policy';documentation.mkdir(parents=True)
        shutil.copyfile(PROJECT/'LICENSE',documentation/'copyright')
        control=stage/'DEBIAN';control.mkdir()
        (control/'control').write_text('''Package: sheng-desktop-edit-policy
Version: 1.0-1
Architecture: arm64
Maintainer: Sheng Kali builders
Depends: plasma-workspace (= 4:6.7.4-2+sheng1), libqt6core6t64 (= 6.11.2+dfsg-5), python3-dbus, qdbus-qt6
Description: Native explicit desktop-editing policy for sheng
 Prevent touch or synthesized mouse holds from accidentally entering editing.
''')
        (control/'postinst').write_text('''#!/bin/sh
set -e
if [ "$1" = configure ] && [ -S /run/user/1000/bus ]; then
    runuser -u kali -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/libexec/sheng-desktop-edit-policy-setup
fi
''');(control/'postinst').chmod(0o755)
        args.output.resolve().parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(args.output.resolve())],check=True)


if __name__=='__main__':main()
