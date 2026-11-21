"""Regressions for PIN detachment and Fcitx input-panel composition."""
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

path = pathlib.Path(__file__).resolve().parents[1] / 'scripts/keyboard-policy.py'
spec = importlib.util.spec_from_file_location('keyboard_policy', path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class Properties:
    def __init__(self):
        self.values = {'mode': 0, 'active': True, 'activeClientSupportsTextInput': True, 'visible': True}
        self.writes = []

    def Get(self, interface, name):
        return self.values[name]

    def Set(self, interface, name, value):
        self.writes.append((name, value))
        self.values[name] = value


class Osk:
    def __init__(self):
        self.manual = False
        self.mode = 0
        self.requested_manual = None
        self.shown = 0
        self.hidden = 0
        self.forced_hidden = 0

    def Get(self, interface, name):
        return {'ManualMode': self.manual, 'Mode': self.mode}[name]

    def ChangeManualMode(self, value):
        # Acknowledgement occurs asynchronously, as on the real controller.
        self.requested_manual = value

    def ShowVirtualKeyboard(self):
        self.shown += 1

    def Show(self):
        raise AssertionError('Must activate Fcitx OSK mode, not only show its window')

    def Hide(self):
        self.hidden += 1

    def ForceHide(self):
        self.forced_hidden += 1


class KeyboardPolicyTests(unittest.TestCase):
    def setUp(self):
        policy._osk_visibility_state = None
        self.kwin = Properties()
        self.osk = Osk()
        self.owner = ':1.5'
        self.context = {'locked': False, 'foreground': 'application', 'generation': 1}
        self.bus = types.SimpleNamespace(
            get_object=lambda name, path: self.kwin if path == '/VirtualKeyboard' else self.osk,
            get_name_owner=lambda name: self.owner)
        self.dbus = types.ModuleType('dbus')
        self.dbus.Interface = lambda obj, interface: obj
        self.dbus.Boolean = bool
        self.dbus.Int32 = int
        self.dbus.DBusException = RuntimeError
        config = types.SimpleNamespace(read=lambda *_: None, get=lambda *_args, **_kwargs: '/usr/share/applications/sheng-msime-fcitx5.desktop')
        self.patches = [patch.dict(sys.modules, {'dbus': self.dbus}),
                        patch.object(policy.configparser, 'ConfigParser', return_value=config),
                        patch.object(policy, 'session_context', side_effect=lambda bus: self.context),
                        patch.object(policy, 'physical_keyboards', return_value=[])]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def apply(self):
        return policy.apply_policy(self.bus)

    def test_detach_while_context_already_active_and_wait_for_manual_ack(self):
        self.osk.manual = True
        self.apply()
        self.assertIs(self.osk.requested_manual, False)
        self.assertEqual(self.osk.shown, 0)
        self.osk.manual = False
        self.apply()
        self.assertEqual(self.osk.shown, 1)
        self.assertEqual(self.kwin.values['mode'], 2)
        # Dismissing the keyboard must survive periodic polling.
        for _ in range(4):
            self.apply()
        self.assertEqual(self.osk.shown, 1)

    def test_attached_keyboard_never_deactivates_chinese_context(self):
        with patch.object(policy, 'physical_keyboards', return_value=['Xiaomi PIN keyboard']):
            self.apply()
        self.assertTrue(self.kwin.values['active'])
        self.assertNotIn(('active', False), self.kwin.writes)
        self.assertEqual(self.osk.shown, 0)
        self.assertEqual(self.osk.forced_hidden, 1)

    def test_text_focus_changes_show_and_hide_without_tablet_mode(self):
        self.apply()
        self.assertEqual(self.osk.shown, 1)
        self.kwin.values['activeClientSupportsTextInput'] = False
        self.apply()
        self.assertEqual(self.osk.hidden, 1)
        self.kwin.values['activeClientSupportsTextInput'] = True
        self.apply()
        self.assertEqual(self.osk.shown, 2)

    def test_lockscreen_is_left_to_launcher_and_new_owner_is_reconciled(self):
        self.osk.mode = 1
        self.apply()
        self.assertEqual((self.osk.shown, self.osk.hidden), (0, 0))
        self.osk.mode = 0
        self.apply()
        self.assertEqual(self.osk.shown, 1)
        self.owner = ':1.6'
        self.apply()
        self.assertEqual(self.osk.shown, 2)

    def test_desktop_residual_text_context_cannot_show_keyboard(self):
        self.context['foreground'] = 'desktop'
        self.apply()
        self.assertTrue(self.osk.requested_manual)
        self.assertEqual(self.osk.shown, 0)
        self.assertEqual(self.osk.forced_hidden, 1)
        # An asynchronously acknowledged suppression remains in place.
        self.osk.manual = True
        self.apply()
        for _ in range(4): self.apply()
        self.assertEqual(self.osk.shown, 0)

    def test_back_from_desktop_waits_for_manual_ack_before_showing(self):
        self.context['foreground'] = 'desktop'
        self.apply()
        self.osk.manual = True
        self.context.update(foreground='application', generation=2)
        self.apply()
        self.assertFalse(self.osk.requested_manual)
        self.assertEqual(self.osk.shown, 0)
        self.osk.manual = False
        self.apply()
        self.assertEqual(self.osk.shown, 1)

    def test_locking_suppresses_stale_normal_panel(self):
        self.context.update(locked=True, foreground='lockscreen', generation=2)
        self.apply()
        self.assertEqual(self.osk.shown, 0)
        self.assertEqual(self.osk.forced_hidden, 1)
        self.assertNotIn(('active', False), self.kwin.writes)
        # Secure panel belongs to the greeter and is untouched without a keyboard.
        self.osk.mode = 1
        self.apply()
        self.assertEqual(self.osk.forced_hidden, 1)

    def test_drawer_search_can_show_keyboard_when_explicitly_focused(self):
        self.context['foreground'] = 'drawer'
        self.apply()
        self.assertEqual(self.osk.shown, 1)

    def test_optional_native_context_failure_preserves_application_input(self):
        self.context['foreground'] = 'unknown'
        self.apply()
        self.assertIsNone(self.osk.requested_manual)
        self.assertEqual(self.osk.shown, 1)
        self.assertTrue(self.kwin.values['active'])

    def test_detach_on_password_page_resets_never_and_secure_manual_mode(self):
        self.context.update(locked=True, foreground='lockscreen')
        self.osk.mode = 1
        self.osk.manual = True
        self.apply()
        self.assertEqual(self.kwin.values['mode'], 2)
        self.assertFalse(self.osk.requested_manual)
        self.assertEqual((self.osk.shown, self.osk.forced_hidden), (0, 0))
        self.assertTrue(self.kwin.values['active'])

    def test_attaching_keyboard_on_password_page_hides_without_cancelling_input(self):
        self.context.update(locked=True, foreground='lockscreen')
        self.osk.mode = 1
        self.kwin.values['mode'] = 2
        with patch.object(policy, 'physical_keyboards', return_value=['Xiaomi PIN keyboard']):
            self.apply()
        self.assertEqual(self.kwin.values['mode'], 0)
        self.assertTrue(self.osk.requested_manual)
        self.assertEqual(self.osk.forced_hidden, 1)
        self.assertTrue(self.kwin.values['active'])


if __name__ == '__main__':
    unittest.main()
