#!/bin/bash
set -euo pipefail
[[ $# == 0 || ( $# == 1 && $1 == --config-only ) ]] || exit 2
low_percent=${SHENG_LOW_BATTERY_PERCENT:-10}
[[ $low_percent =~ ^[0-9]+$ ]] && (( low_percent >= 6 && low_percent <= 40 )) || exit 2
native_policy=false
[[ ! -f /usr/share/sheng-power-management/native-policy.json ]] || native_policy=true
kwriteconfig6 --file powerdevilrc --group BatteryManagement --key BatteryLowLevel "$low_percent"
kwriteconfig6 --file powerdevilrc --group BatteryManagement --key BatteryCriticalLevel 5
# This tablet exposes suspend-to-RAM, not a configured hibernation image.
kwriteconfig6 --file powerdevilrc --group BatteryManagement --key BatteryCriticalAction 1
for profile in AC Battery LowBattery; do
    # Short press locks the session on every power source.
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key PowerButtonAction 32
    # KWin emits PowerDown for a long hold; use Plasma's native power menu.
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key PowerDownAction 16
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key SleepMode 1
    case "$profile" in
        AC) idle_minutes=60; suspend_action=0 ;;
        Battery) idle_minutes=30; suspend_action=0 ;;
        LowBattery) idle_minutes=5; suspend_action=1 ;;
    esac
    idle_seconds=$((idle_minutes * 60))
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key AutoSuspendAction "$suspend_action"
    kwriteconfig6 --file powerdevilrc --group "$profile" --group SuspendAndShutdown --key AutoSuspendIdleTimeoutSec "$idle_seconds"
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayWhenIdle true
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayIdleTimeoutSec "$idle_seconds"
    # Entering the lock screen blanks immediately; user activity still wakes it.
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayIdleTimeoutWhenLockedSec 0
    kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key LockBeforeTurnOffDisplay true
    if $native_policy; then
        old_command=$(kreadconfig6 --file powerdevilrc --group "$profile" --group RunScript --key ProfileLoadCommand)
        if [[ $old_command == '/usr/libexec/sheng-set-screen-lock-timeout '* ]]; then
            kwriteconfig6 --file powerdevilrc --group "$profile" --group RunScript --key ProfileLoadCommand --delete
        fi
    else
        # Compatibility for the base image until the native PowerDevil package
        # is installed. The native package handles this in C++ without a hook.
        kwriteconfig6 --file powerdevilrc --group "$profile" --group RunScript --key ProfileLoadCommand "/usr/libexec/sheng-set-screen-lock-timeout $idle_minutes"
    fi
done
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock true
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 60
kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockGrace 0
if [[ ${1:-} != --config-only ]]; then
    # reparseConfiguration() alone leaves the active profile's button actions
    # cached. refreshStatus() also calls loadProfile(true), without a restart.
    qdbus6 org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement org.kde.Solid.PowerManagement.refreshStatus
    profile=$(qdbus6 org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement org.kde.Solid.PowerManagement.currentProfile)
    case "$profile" in
        AC) idle_minutes=60 ;;
        Battery) idle_minutes=30 ;;
        LowBattery) idle_minutes=5 ;;
        *) echo "Unknown PowerDevil profile: $profile" >&2; exit 1 ;;
    esac
    if ! $native_policy; then /usr/libexec/sheng-set-screen-lock-timeout "$idle_minutes"; fi
fi
