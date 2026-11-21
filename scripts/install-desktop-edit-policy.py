#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Configure the native editing-policy applet once; no runtime script loop."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-id')
    args=parser.parse_args()
    if os.geteuid()==0:raise SystemExit('Run as the desktop user')
    plugin=args.plugin_id
    if not plugin:
        marker=Path('/usr/share/sheng-desktop-edit-policy/policy-id.txt')
        plugin=marker.read_text().strip()
    if not re.fullmatch(r'org\.sheng\.desktopeditpolicy\.[a-f0-9]{12}',plugin):
        raise SystemExit('Unexpected native policy ID')
    owner_root=Path.home()
    state=owner_root/'.local/state/sheng-desktop-edit-policy'
    backup=state/('backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
    source=owner_root/'.config/plasma-org.kde.plasma.desktop-appletsrc'
    if source.exists():shutil.copy2(source,backup/source.name)
    import dbus
    bus=dbus.SessionBus()
    plasma=dbus.Interface(bus.get_object('org.kde.plasmashell','/PlasmaShell'),'org.kde.PlasmaShell')
    script='''var target=TARGET;var d=desktops()[0];if(!d)throw new Error("Desktop not found");var current=d.widgets().find(w=>w.type===target);if(!current)current=d.addWidget(target);if(!current||current.type!==target)throw new Error("Native policy did not load");d.widgets().filter(w=>w.type.indexOf("org.sheng.desktopeditpolicy.")===0&&w.type!==target).forEach(w=>w.remove());print(JSON.stringify({nativePolicy:current.type,desktop:d.id}));'''.replace('TARGET',json.dumps(plugin))
    print(plasma.evaluateScript(script,timeout=15))


if __name__=='__main__':main()
