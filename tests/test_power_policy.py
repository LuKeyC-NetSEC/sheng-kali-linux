"""Native KConfig migration checks, isolated from the running desktop session."""
import configparser
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/configure-power-buttons.sh'


@unittest.skipUnless(os.name == 'posix' and shutil.which('kwriteconfig6') and shutil.which('kreadconfig6'),
                     'Requires the target Linux KDE configuration tools')
class PowerPolicyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = {**os.environ, 'XDG_CONFIG_HOME':str(self.directory), 'SHENG_LOW_BATTERY_PERCENT':'10'}
        (self.directory/'powerdevilrc').write_text(
            '[Battery][SuspendAndShutdown]\nAutoSuspendAction=8\nCustomKeep=unchanged\n'
            '[LowBattery][SuspendAndShutdown]\nAutoSuspendAction=0\n'
            '[General]\nUserPreference=preserve\n')

    def apply(self, percent='10', check=True):
        return subprocess.run(['bash',str(SCRIPT),'--config-only'],
                              env={**self.environment,'SHENG_LOW_BATTERY_PERCENT':percent},
                              text=True,capture_output=True,check=check)

    def read(self):
        config=configparser.ConfigParser(interpolation=None)
        config.read(self.directory/'powerdevilrc')
        return config

    def test_migrate_legacy_shutdown_policy_to_low_battery_only_suspend(self):
        self.apply()
        config=self.read()
        for profile in ('AC','Battery'):
            self.assertEqual(config.getint(profile+'][SuspendAndShutdown','AutoSuspendAction'),0)
        self.assertEqual(config.getint('LowBattery][SuspendAndShutdown','AutoSuspendAction'),1)
        self.assertEqual(config.getint('LowBattery][SuspendAndShutdown','AutoSuspendIdleTimeoutSec'),300)
        self.assertEqual(config.getint('BatteryManagement','BatteryLowLevel'),10)
        self.assertEqual(config.getint('BatteryManagement','BatteryCriticalLevel'),5)
        self.assertEqual(config.getint('BatteryManagement','BatteryCriticalAction'),1)
        self.assertEqual(config.get('Battery][SuspendAndShutdown','CustomKeep'),'unchanged')
        self.assertEqual(config.get('General','UserPreference'),'preserve')

    def test_display_timeouts_and_power_button_behavior_survive_migration(self):
        self.apply()
        config=self.read()
        for profile in ('AC','Battery','LowBattery'):
            self.assertEqual(config.getint(profile+'][Display','TurnOffDisplayIdleTimeoutSec'),60)
            self.assertEqual(config.getint(profile+'][Display','TurnOffDisplayIdleTimeoutWhenLockedSec'),0)
            self.assertEqual(config.getint(profile+'][SuspendAndShutdown','PowerButtonAction'),64)
            self.assertTrue(config.getboolean(profile+'][Display','LockBeforeTurnOffDisplay'))
            self.assertEqual(config.getint(profile+'][SuspendAndShutdown','PowerDownAction'),16)
        locker=configparser.ConfigParser(interpolation=None)
        locker.read(self.directory/'kscreenlockerrc')
        self.assertEqual(locker.getint('Daemon','Timeout'),1)
        before=(self.directory/'powerdevilrc').read_bytes()
        self.apply()
        self.assertEqual((self.directory/'powerdevilrc').read_bytes(),before)

    def test_invalid_threshold_cannot_partially_overwrite_user_settings(self):
        before=(self.directory/'powerdevilrc').read_bytes()
        for value in ('0','5','101','ten','10;false'):
            with self.subTest(value=value):
                self.assertNotEqual(self.apply(value,check=False).returncode,0)
                self.assertEqual((self.directory/'powerdevilrc').read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
