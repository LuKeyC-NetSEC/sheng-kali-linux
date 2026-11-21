#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read aggregate power state without collecting application or authentication data."""
import configparser
import json
from pathlib import Path
import subprocess


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def main():
    import dbus
    config=configparser.ConfigParser(interpolation=None,strict=False)
    config.read(Path.home()/'.config/powerdevilrc')
    profile=None; locked=None; warning=None; on_battery=None; blocks=None
    try:
        session=dbus.SessionBus()
        profile=str(dbus.Interface(session.get_object('org.kde.Solid.PowerManagement','/org/kde/Solid/PowerManagement'),
                                  'org.kde.Solid.PowerManagement').currentProfile())
        locked=bool(dbus.Interface(session.get_object('org.freedesktop.ScreenSaver','/ScreenSaver'),
                                   'org.freedesktop.ScreenSaver').GetActive())
    except dbus.DBusException:
        pass
    try:
        system=dbus.SystemBus()
        properties=dbus.Interface(system.get_object('org.freedesktop.UPower','/org/freedesktop/UPower'),
                                   'org.freedesktop.DBus.Properties')
        on_battery=bool(properties.Get('org.freedesktop.UPower','OnBattery'))
        display=dbus.Interface(system.get_object('org.freedesktop.UPower','/org/freedesktop/UPower/devices/DisplayDevice'),
                                'org.freedesktop.DBus.Properties')
        warning=int(display.Get('org.freedesktop.UPower.Device','WarningLevel'))
        inhibitors=dbus.Interface(system.get_object('org.freedesktop.login1','/org/freedesktop/login1'),
                                   'org.freedesktop.login1.Manager').ListInhibitors()
        blocks=sum(1 for row in inhibitors if 'sleep' in str(row[0]).split(':') and str(row[3])=='block')
    except dbus.DBusException:
        pass
    battery=Path('/sys/class/power_supply/qcom-battmgr-bat')
    values={key:read(battery/key) for key in ('capacity','current_now','voltage_now','temp','status')}
    net_power=None
    try:
        net_power=round(int(values['current_now'])*int(values['voltage_now'])/1e12,3)
    except (TypeError,ValueError):
        pass
    effective=None
    try:
        sleep=configparser.ConfigParser(interpolation=None,strict=False)
        sleep.read_string(subprocess.check_output(['systemd-analyze','cat-config','systemd/sleep.conf'],text=True,timeout=10))
        effective=sleep.get('Sleep','MemorySleepMode',fallback=None)
    except (OSError,subprocess.SubprocessError,configparser.Error):
        pass
    section=(profile or 'unknown')+'][SuspendAndShutdown'
    gpu=next(Path('/sys/class/devfreq').glob('*gpu*'),None)
    print(json.dumps({
        'profile':profile,'locked':locked,'onBattery':on_battery,'batteryWarningLevel':warning,
        'autoSuspendAction':config.getint(section,'AutoSuspendAction',fallback=None),
        'autoSuspendIdleSeconds':config.getint(section,'AutoSuspendIdleTimeoutSec',fallback=None),
        'lowBatteryPercent':config.getint('BatteryManagement','BatteryLowLevel',fallback=10),
        'criticalBatteryPercent':config.getint('BatteryManagement','BatteryCriticalLevel',fallback=5),
        'battery':values,'estimatedBatteryNetWatts':net_power,
        'netPowerMeaning':'negative means net battery discharge; fuel-gauge estimate, not USB input power',
        'dpms':read('/sys/class/drm/card0-DSI-1/dpms'),
        'reportedBacklightBrightness':read('/sys/class/backlight/ktz8866-backlight/actual_brightness'),
        'kernelMemorySleep':read('/sys/power/mem_sleep'),'systemdMemorySleepMode':effective,
        'suspendSuccess':read('/sys/power/suspend_stats/success'),'suspendFailures':read('/sys/power/suspend_stats/fail'),
        'blockingSleepInhibitors':blocks,
        'gpuRuntimeStatus':read(gpu/'device/power/runtime_status') if gpu else None,
        'cpuGovernors':sorted(set(value for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_governor') if (value:=read(p))))
    },indent=2))


if __name__=='__main__':
    main()
