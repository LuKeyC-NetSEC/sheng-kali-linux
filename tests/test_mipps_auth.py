# SPDX-License-Identifier: GPL-2.0-only
"""No hardware, root, real sysfs, keys, or charging commands are used here."""
import contextlib
import hashlib
import hmac
import importlib.machinery
import importlib.util
import io
import pathlib
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'out/mipps-source/xiaomi-mipps-auth'


class MippsHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest('Prepare pinned source with scripts/prepare-mipps-auth.py first')

    def setUp(self):
        loader = importlib.machinery.SourceFileLoader('mipps_under_test', str(SOURCE))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.auth = importlib.util.module_from_spec(spec)
        # pwd is Linux-only. These tests do not exercise notification privilege
        # changes, and must never attempt them on the Windows source-review host.
        stub_pwd = types.ModuleType('pwd')
        stub_pwd.getpwuid = mock.Mock(side_effect=AssertionError('Privilege changes are forbidden in offline tests'))
        with mock.patch.dict('sys.modules', {'pwd': stub_pwd}):
            loader.exec_module(self.auth)  # __main__ never runs; functions remain dormant.

    def test_connection_change_stops_writes(self):
        a = self.auth
        with mock.patch.object(a, 'usb_is_online', return_value=True), mock.patch.object(a, 'current_attach_token', return_value='synthetic-A') as token:
            a.begin_session()
            token.return_value = 'synthetic-B'
            with mock.patch('builtins.open') as file:
                with self.assertRaises(ConnectionError):
                    a.write_node('/synthetic-only', 'pd_verifed', '1')
                file.assert_not_called()

    def test_offline_cancels_session(self):
        a = self.auth
        with mock.patch.object(a, 'usb_is_online', return_value=True) as online, mock.patch.object(a, 'current_attach_token', return_value='synthetic-A'):
            a.begin_session()
            online.return_value = False
            with self.assertRaises(ConnectionError):
                a.check_connection()

    def test_timeout_does_not_print_auth_payload(self):
        a = self.auth
        with mock.patch.object(a, 'vdm_state', return_value=(5, 'SENSITIVE_SYNTHETIC')), mock.patch.object(a.time, 'monotonic', side_effect=[0.0, 0.1, 2.0]), mock.patch.object(a.time, 'sleep'):
            with self.assertRaises(a.UnsupportedChargerError) as failure:
                a.wait_state('/synthetic', 8, 1.0)
            self.assertNotIn('SENSITIVE_SYNTHETIC', str(failure.exception))

    def test_completed_requires_verdict_and_both_gauges(self):
        a = self.auth
        with mock.patch.object(a, 'pd_verified', return_value=False):
            self.assertFalse(a.auth_already_completed('/synthetic', 7))
        with mock.patch.object(a, 'pd_verified', return_value=True), mock.patch.object(a, 'node_is_one', side_effect=lambda root, name: name != 'slave_authentic'):
            self.assertFalse(a.auth_already_completed('/synthetic', 6))
        with mock.patch.object(a, 'pd_verified', return_value=True), mock.patch.object(a, 'node_is_one', return_value=True):
            self.assertTrue(a.auth_already_completed('/synthetic', 7))
            self.assertFalse(a.auth_already_completed('/synthetic', 8))
            self.assertFalse(a.auth_already_completed('/synthetic', 5))

    def test_vdm_payload_lengths(self):
        a = self.auth
        with mock.patch.object(a, 'write_node') as write:
            for command, payload in [(4, '00'), (5, 'x' * 32), (8, '0' * 34), (6, '1'), (7, '0' * 10)]:
                with self.assertRaises(ValueError):
                    a.send_vdm('/synthetic', command, payload)
            write.assert_not_called()
        with mock.patch.object(a, 'write_node') as write, mock.patch.object(a, 'vdm_state', return_value=(6, 'Null')), mock.patch.object(a.time, 'sleep'):
            a.send_vdm('/synthetic', 6, '01000000', wait=False)
            write.assert_called_once_with('/synthetic', 'request_vdm_cmd', '6,01000000')

    def test_adapter_identifier_is_not_silently_truncated(self):
        a = self.auth
        self.assertEqual(a.normalize_adapter_id(' A1B2C3D4 '), 'a1b2c3d4')
        for value in ('00000000', 'a1b2c3', 'a1b2c3d4dead', 'zzzzzzzz'):
            self.assertIsNone(a.normalize_adapter_id(value))

    def test_status_never_reads_digest_or_vdm_payload(self):
        a = self.auth
        names = []
        def read(root, name):
            names.append(name)
            return '0'
        with mock.patch.object(a.os.path, 'exists', return_value=True), mock.patch.object(a, 'read_node', side_effect=read), contextlib.redirect_stdout(io.StringIO()):
            a.print_status('/synthetic')
        self.assertNotIn('request_vdm_cmd', names)
        self.assertNotIn('verify_digest', names)

    def test_capability_is_not_measured_power_and_pd_is_not_pps(self):
        a = self.auth
        with mock.patch.object(a, 'current_battery_capacity', return_value=30), mock.patch.object(a, 'current_power_max_watts', return_value=120), mock.patch.object(a, 'current_int_value', return_value=1), mock.patch.object(a, 'current_string_value', return_value='PD'), mock.patch.object(a, 'pd_verified', return_value=False):
            self.assertEqual(a.current_charge_profile('/synthetic', False), ('PD', 120))
            self.assertEqual(a.current_charge_profile('/synthetic', True), ('PD', 120))
        self.assertIn('not measured input power', a.charge_mode_body('MiPPS', 120))

    def test_unknown_fastcharge_state_is_not_active_mipps(self):
        a = self.auth
        with mock.patch.object(a, 'current_battery_capacity', return_value=30), mock.patch.object(a, 'current_power_max_watts', return_value=120), mock.patch.object(a, 'current_int_value', return_value=None), mock.patch.object(a, 'current_string_value', return_value='PD_PPS'), mock.patch.object(a, 'pd_verified', return_value=True):
            self.assertEqual(a.current_charge_profile('/synthetic', True), ('PPS', 120))

    def test_gauge_truncation_rejected_without_success_flag(self):
        a = self.auth
        with mock.patch.object(a, 'write_node'), mock.patch.object(a, 'write_node_if_present') as verdict, mock.patch.object(a, 'read_node', return_value='0' * 66), mock.patch.object(a.time, 'sleep'):
            with self.assertRaises(ValueError):
                a.verify_fuel_gauge_once('/synthetic', False)
            verdict.assert_not_called()

    def test_synthetic_gauge_success_and_failure(self):
        a = self.auth
        # Replace ALL upstream constants with fabricated material before calling
        # the algorithm. No actual device/key values enter assertions or output.
        challenge = 'ab' * 32
        key = 'cd' * 32
        digest = hmac.new(bytes.fromhex(key), bytes.fromhex(challenge), hashlib.sha256).hexdigest()
        with mock.patch.object(a, 'FG_KEYS', [key]), mock.patch.object(a.secrets, 'token_hex', return_value=challenge), mock.patch.object(a, 'write_node'), mock.patch.object(a, 'read_node', return_value=digest), mock.patch.object(a, 'write_node_if_present') as verdict, mock.patch.object(a.time, 'sleep'):
            self.assertTrue(a.verify_fuel_gauge_once('/synthetic', False))
            verdict.assert_called_once_with('/synthetic', 'authentic', '1')
        with mock.patch.object(a, 'FG_KEYS', [key]), mock.patch.object(a.secrets, 'token_hex', return_value=challenge), mock.patch.object(a, 'write_node'), mock.patch.object(a, 'read_node', return_value='ef' * 32), mock.patch.object(a, 'write_node_if_present') as verdict, mock.patch.object(a.time, 'sleep'):
            self.assertFalse(a.verify_fuel_gauge_once('/synthetic', True))
            verdict.assert_called_once_with('/synthetic', 'slave_authentic', '0')

    def test_online_trigger_failure_does_not_set_retry_latch(self):
        a = self.auth
        with mock.patch('sys.argv', ['xiaomi-mipps-auth', '--usb-online-trigger']), mock.patch.object(a, 'read_state_file', return_value='0'), mock.patch.object(a, 'start_systemd_unit', side_effect=OSError('synthetic')), mock.patch.object(a, 'write_state_file') as write:
            with self.assertRaises(OSError):
                a.main()
            write.assert_not_called()

    def test_service_budget_allows_both_gauge_retry_loops(self):
        service = (SOURCE.parent/'xiaomi-mipps-auth.service').read_text(encoding='utf-8')
        settings = dict(line.split('=', 1) for line in service.splitlines() if '=' in line)
        self.assertGreaterEqual(int(settings['TimeoutStartSec']), 120)
        self.assertEqual(settings['Restart'], 'on-failure')
        self.assertEqual(settings['StartLimitBurst'], '3')
        self.assertEqual(settings['UMask'], '0077')

    def test_reverse_auth_failure_never_sets_final_success(self):
        a = self.auth
        challenge = '56' * 16
        key = '34' * 32
        adapter_id = '01020304'
        digest = hmac.new(bytes.fromhex(key), bytes.fromhex(challenge + adapter_id), hashlib.sha256).hexdigest()
        commands = []
        def send(root, command, *args, **kwargs):
            commands.append(command)
            if command == 5:
                return 5, digest[:32]
            if command == 8:
                raise a.UnsupportedChargerError('synthetic timeout')
            return command, 'Null'
        replacements = {
            'wait_usb_online': lambda *args: True,
            'write_state_file': mock.Mock(), 'begin_session': mock.Mock(),
            'vdm_state': lambda *args: (0, 'Null'),
            'auth_already_completed': lambda *args: False,
            'wait_real_type': lambda *args: 'PD', 'ensure_typec_host': lambda *args: True,
            'current_adapter_svid': lambda *args: a.XIAOMI_SVID,
            'should_skip_pdo2': lambda *args: False,
            'enable_battery_auth': mock.Mock(), 'send_vdm': send,
            'detect_adapter_id': lambda *args: adapter_id,
            'notify_completed_charge': mock.Mock(),
            'write_node': mock.Mock(), 'print_status': mock.Mock(),
            'SEEDS': ['12' * 16] * 10, 'KEYS': [key] * 10,
        }
        output = io.StringIO()
        with mock.patch('sys.argv', ['xiaomi-mipps-auth', '--sysfs', '/synthetic']), mock.patch.multiple(a, **replacements), mock.patch.object(a.secrets, 'token_hex', return_value=challenge), contextlib.redirect_stdout(output):
            with self.assertRaises(a.UnsupportedChargerError):
                a.main()
        self.assertNotIn(7, commands)
        replacements['write_node'].assert_not_called()
        self.assertNotIn(challenge, output.getvalue())
        self.assertNotIn(digest, output.getvalue())


if __name__ == '__main__':
    unittest.main()
