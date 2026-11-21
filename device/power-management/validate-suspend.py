#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-shot acceptance test using PowerDevil's own alarm and suspend APIs.

This test actively suspends the tablet and pauses networking. It is never
installed as a background service. Run only when a short interruption is OK.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=20)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-suspend',action='store_true')
    args=parser.parse_args()
    if not args.allow_suspend or not 10<=args.seconds<=45:
        raise SystemExit('Explicit --allow-suspend and a duration from 10 to 45 seconds are required')
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus=dbus.SessionBus()
    manager=dbus.Interface(bus.get_object('org.kde.Solid.PowerManagement','/org/kde/Solid/PowerManagement'),
                           'org.kde.Solid.PowerManagement')
    saver=dbus.Interface(bus.get_object('org.freedesktop.ScreenSaver','/ScreenSaver'),'org.freedesktop.ScreenSaver')
    def number(name):
        try:return int(Path('/sys/power/suspend_stats',name).read_text())
        except (OSError,ValueError):return None
    def pids():
        text=subprocess.check_output(['systemctl','--user','show','plasma-kwin_wayland.service',
                                      'plasma-plasmashell.service','-p','MainPID','--value'],text=True)
        return [int(x) for x in text.split() if x.isdigit()]
    def snapshot():
        return {'success':number('success'),'fail':number('fail'),'locked':bool(saver.GetActive()),
                'memorySleep':Path('/sys/power/mem_sleep').read_text().strip(),
                'dpms':Path('/sys/class/drm/card0-DSI-1/dpms').read_text().strip()}
    before=snapshot(); processes=pids()
    monotonic=time.monotonic();boottime=time.clock_gettime(time.CLOCK_BOOTTIME)
    loop=GLib.MainLoop(); result={}; cookie=None
    name=dbus.service.BusName('org.sheng.PowerValidation',bus=bus)
    def save(success):
        after=snapshot()
        result.update(before=before,after=after,alarmCallbackReceived=success,
                      observedSleepSeconds=round((time.clock_gettime(time.CLOCK_BOOTTIME)-boottime)-(time.monotonic()-monotonic),3),
                      sessionProcessesPreserved=processes==pids(),
                      lockPreserved=not before['locked'] or after['locked'])
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        loop.quit();return False
    class Consumer(dbus.service.Object):
        @dbus.service.method('org.kde.PowerManagement',in_signature='i',out_signature='')
        def wakeupCallback(self, received):
            if int(received)!=int(cookie):return
            # Request a full wake through the native API. This turns on the
            # display and cancels timer-only re-suspend; it never unlocks it.
            manager.wakeup()
            GLib.timeout_add_seconds(5,lambda:save(True))
    consumer=Consumer(name,'/org/sheng/PowerValidation')
    cookie=manager.scheduleWakeup('org.sheng.PowerValidation',dbus.ObjectPath('/org/sheng/PowerValidation'),
                                  dbus.UInt64(int(time.time())+args.seconds))
    def suspend():
        target=bus.get_object('org.kde.Solid.PowerManagement','/org/kde/Solid/PowerManagement/Actions/SuspendSession')
        dbus.Interface(target,'org.kde.Solid.PowerManagement.Actions.SuspendSession').suspendToRam()
        return False
    GLib.timeout_add(300,suspend)
    GLib.timeout_add_seconds(args.seconds+35,lambda:save(False))
    try:
        loop.run()
    finally:
        manager.clearWakeup(int(cookie))
        consumer.remove_from_connection()
    print(json.dumps(result))


if __name__=='__main__':main()
