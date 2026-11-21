#!/usr/bin/env python3
"""Suppress the on-screen keyboard while a real keyboard is connected."""
import json
import configparser
import os
from pathlib import Path
import sys

_osk_visibility_state = None


def session_context(bus):
    """Only window roles/lock status are used; never inspect field text or captions."""
    import dbus
    saver = dbus.Interface(bus.get_object('org.freedesktop.ScreenSaver', '/ScreenSaver'),
                           'org.freedesktop.ScreenSaver')
    locked = bool(saver.GetActive())
    try:
        guard = dbus.Interface(bus.get_object('org.sheng.DesktopTouch', '/org/sheng/DesktopTouch'),
                               'org.sheng.DesktopTouch')
        context = json.loads(str(guard.GetKeyboardContext()))
        return {'locked': locked or bool(context.get('locked')), 'foreground': context.get('foreground', 'unknown'),
                'generation': int(context.get('generation', 0))}
    except (dbus.DBusException, ValueError, TypeError):
        # A missing optional desktop guard must not disable application input.
        # Keep the established text-input policy until window roles return.
        return {'locked': locked, 'foreground': 'unknown', 'generation': 0}


def physical_keyboards():
    result = []
    dock = Path('/sys/class/misc/nanosic_hinge/keyboard_attached')
    try:
        if dock.read_text().strip() == '1':
            result.append('Xiaomi PIN keyboard')
    except OSError:
        pass
    for event in Path('/sys/class/input').glob('event*'):
        try:
            properties = Path('/run/udev/data/c' + (event / 'dev').read_text().strip()).read_text()
            fields = dict(line[2:].split('=', 1) for line in properties.splitlines()
                          if line.startswith('E:') and '=' in line)
            if fields.get('ID_INPUT_KEYBOARD') != '1':
                continue
            name = (event / 'device/name').read_text().strip()
            if name == 'fcitx5-osk-key-helper':
                continue
            if fields.get('ID_BUS') in ('usb', 'bluetooth') or fields.get('ID_INTEGRATION') == 'external':
                result.append(name)
        except OSError:
            continue
    return sorted(set(result))


def apply_policy(bus):
    global _osk_visibility_state
    import dbus
    keyboards = physical_keyboards()
    context = session_context(bus)
    locked = context['locked']
    eligible = context['foreground'] not in ('desktop', 'none', 'lockscreen')
    config = configparser.ConfigParser(interpolation=None,strict=False)
    config.read(Path.home()/'.config/kwinrc')
    fcitx = 'fcitx' in config.get('Wayland','InputMethod',fallback='').lower()
    obj = bus.get_object('org.kde.KWin', '/VirtualKeyboard')
    properties = dbus.Interface(obj, 'org.freedesktop.DBus.Properties')
    interface = 'org.kde.kwin.VirtualKeyboard'
    # Fcitx's panel is separate from KWin's candidates. AnyInput avoids a
    # stale last-input-device classification after detaching the PIN dock.
    desired = 0 if keyboards else (2 if fcitx else 1)
    # Hotplug still matters on the greeter: Never left over from a connected
    # PIN keyboard must be cleared when that keyboard is detached while locked.
    if int(properties.Get(interface, 'mode')) != desired:
        properties.Set(interface, 'mode', dbus.Int32(desired))
    # Fcitx candidates also use an input-panel overlay. Deactivating that
    # context would cancel physical-keyboard Chinese composition.
    if not locked and keyboards and not fcitx and bool(properties.Get(interface, 'visible')):
        properties.Set(interface, 'active', dbus.Boolean(False))
    if fcitx:
        try:
            name = 'fyi.fortime.Fcitx5Osk'
            owner = str(bus.get_name_owner(name))  # Do not start the GUI merely to poll it.
            target = bus.get_object(name,'/fyi/fortime/Fcitx5Osk/Controller')
            osk = dbus.Interface(target,'fyi.fortime.Fcitx5Osk.Controller1')
            osk_properties = dbus.Interface(target,'org.freedesktop.DBus.Properties')
            current = osk_properties.Get('fyi.fortime.Fcitx5Osk.Controller1','ManualMode')
            # Upstream's normal-session launcher only calls Show() when
            # KWin reports tabletMode. PIN detachment is handled independently
            # here, so text-input activation must also drive the OSK directly.
            # Show is edge-triggered: polling must not reopen a keyboard that
            # the user dismissed. Leave lockscreen mode to its own launcher.
            active = bool(properties.Get(interface, 'active'))
            supports = bool(properties.Get(interface, 'activeClientSupportsTextInput'))
            osk_mode = int(osk_properties.Get('fyi.fortime.Fcitx5Osk.Controller1','Mode'))
            # The secure input panel is owned by the greeter. A stale normal
            # session panel must not be auto-shown on top of the clock page.
            if locked or osk_mode != 0:
                # ManualMode is shared/persisted across normal and secure
                # panels. Restore automatic mode for the secure panel after
                # detaching a keyboard; only the greeter drives its visibility.
                manual = bool(keyboards) or (locked and osk_mode == 0)
                if bool(current) != manual: osk.ChangeManualMode(dbus.Boolean(manual))
                if manual:
                    osk.ForceHide()
                _osk_visibility_state = (owner, bool(keyboards), bool(current), active, supports, osk_mode, locked)
                return {'physical_keyboard_present': bool(keyboards), 'keyboards': keyboards,
                        'virtual_keyboard_mode': desired, **context}
            manual = bool(keyboards) or not eligible
            if bool(current) != manual: osk.ChangeManualMode(dbus.Boolean(manual))
            state = (owner, bool(keyboards), bool(current), active, supports, osk_mode,
                     locked, context['foreground'], context['generation'])
            if keyboards: osk.ForceHide()
            if state != _osk_visibility_state:
                if not eligible:
                    osk.ForceHide()
                elif not keyboards and not current and osk_mode == 0:
                    if active and supports:
                        # Set Fcitx's OnScreenKeyboard mode as well as showing
                        # the window. Calling OSK.Show alone leaves Fcitx in
                        # PhysicalKeyboard mode after the last real key, so
                        # later focus-in requests can fail to auto-show.
                        bus.get_name_owner('org.fcitx.Fcitx5')
                        controller = bus.get_object('org.fcitx.Fcitx5', '/virtualkeyboard')
                        dbus.Interface(controller, 'org.fcitx.Fcitx.VirtualKeyboard1').ShowVirtualKeyboard()
                    else:
                        osk.Hide()
                _osk_visibility_state = state
        except dbus.DBusException:
            _osk_visibility_state = None
    else:
        _osk_visibility_state = None
    return {'physical_keyboard_present': bool(keyboards), 'keyboards': keyboards,
            'virtual_keyboard_mode': desired, **context}


def main():
    import dbus
    if '--apply-once' in sys.argv:
        print(json.dumps(apply_policy(dbus.SessionBus())))
        return
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    last = None

    def reconcile(*_):
        nonlocal last
        try:
            state = apply_policy(bus)
            if state != last:
                print(json.dumps(state), flush=True)
                last = state
        except dbus.DBusException:
            pass  # KWin may be starting or resuming; retry without restarting its session.
        return True

    bus.add_signal_receiver(reconcile, signal_name='modeChanged',
                            dbus_interface='org.kde.kwin.VirtualKeyboard', path='/VirtualKeyboard')
    bus.add_signal_receiver(reconcile, signal_name='visibleChanged',
                            dbus_interface='org.kde.kwin.VirtualKeyboard', path='/VirtualKeyboard')
    bus.add_signal_receiver(reconcile, signal_name='activeChanged',
                            dbus_interface='org.kde.kwin.VirtualKeyboard', path='/VirtualKeyboard')
    bus.add_signal_receiver(reconcile, signal_name='activeClientSupportsTextInputChanged',
                            dbus_interface='org.kde.kwin.VirtualKeyboard', path='/VirtualKeyboard')
    bus.add_signal_receiver(reconcile, signal_name='PropertiesChanged',
                            dbus_interface='org.freedesktop.DBus.Properties',
                            path='/fyi/fortime/Fcitx5Osk/Controller',
                            arg0='fyi.fortime.Fcitx5Osk.Controller1')
    bus.add_signal_receiver(reconcile, signal_name='NameOwnerChanged',
                            dbus_interface='org.freedesktop.DBus',arg0='fyi.fortime.Fcitx5Osk')
    bus.add_signal_receiver(reconcile, signal_name='ActiveChanged',
                            dbus_interface='org.freedesktop.ScreenSaver', path='/ScreenSaver')
    bus.add_signal_receiver(reconcile, signal_name='KeyboardContextChanged',
                            dbus_interface='org.sheng.DesktopTouch', path='/org/sheng/DesktopTouch')
    GLib.timeout_add_seconds(1, reconcile)
    reconcile()
    GLib.MainLoop().run()


if __name__ == '__main__':
    main()
