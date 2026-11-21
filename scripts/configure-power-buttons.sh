#!/bin/bash
set -euo pipefail
[[ $# == 0 || ( $# == 1 && $1 == --config-only ) ]] || exit 2
low_percent=${SHENG_LOW_BATTERY_PERCENT:-10}
[[ $low_percent =~ ^[0-9]+$ ]] && (( low_percent >= 6 && low_percent <= 40 )) || exit 2
kwriteconfig6 --file powerdevilrc --group BatteryManagement --key BatteryLowLevel "$low_percent"
kwriteconfig6 --file powerdevilrc --group BatteryManagement --key BatteryCriticalLevel 5
# This tablet exposes suspend-to-RAM, not a configured hibernation image.
kwriteconfig6 --file powerdevilrc --group BatteryManagement --key BatteryCriticalAction 1
for profile in AC Battery LowBattery; do
    # Native DPMS turns off directly; LockBeforeTurnOffDisplay below also locks.
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key PowerButtonAction 64
    # KWin emits PowerDown for a long hold; use Plasma's native power menu.
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key PowerDownAction 16
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key SleepMode 1
    case "$profile" in
        AC|Battery) suspend_seconds=60; suspend_action=0 ;;
        LowBattery) suspend_seconds=300; suspend_action=1 ;;
    esac
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key AutoSuspendAction "$suspend_action"
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key AutoSuspendIdleTimeoutSec "$suspend_seconds"
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayWhenIdle true
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayIdleTimeoutSec 60
    # Entering the lock screen blanks immediately; user activity still wakes it.
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayIdleTimeoutWhenLockedSec 0
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key LockBeforeTurnOffDisplay true
    old_command=$(kreadconfig6 --file powerdevilrc --group "$profile" --group RunScript --key ProfileLoadCommand)
    if [[ $old_command == '/usr/libexec/sheng-set-screen-lock-timeout '* ]]; then
        kwriteconfig6 --file powerdevilrc --group "$profile" --group RunScript --key ProfileLoadCommand --delete
    fi
done
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock true
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 1
kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockGrace 0
if [[ ${1:-} != --config-only ]]; then
    # reparseConfiguration() alone leaves the active profile's button actions
    # cached. refreshStatus() also calls loadProfile(true), without a restart.
    qdbus6 org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement org.kde.Solid.PowerManagement.refreshStatus
fi
