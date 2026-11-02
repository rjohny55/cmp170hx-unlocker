from configparser import ConfigParser
from pathlib import Path
import unittest


class Gen2ServiceTimeoutTests(unittest.TestCase):
    def test_boot_activation_has_bounded_start_and_stop(self):
        unit = ConfigParser(interpolation=None, strict=False)
        unit.read(Path(__file__).resolve().parents[1] /
                  "systemd/cmp170-gen2-second-pass.service")
        service = unit["Service"]
        self.assertEqual(service["Type"], "oneshot")
        self.assertEqual(service["TimeoutStartSec"], "120s")
        self.assertEqual(service["TimeoutStopSec"], "10s")
        self.assertEqual(service["KillMode"], "control-group")
        self.assertEqual(service["SendSIGKILL"], "yes")
        self.assertEqual(service["Restart"], "no")

    def test_activation_does_not_gate_boot_or_ssh(self):
        root = Path(__file__).resolve().parents[1]
        unit = ConfigParser(interpolation=None, strict=False)
        unit.read(root / "systemd/cmp170-gen2-second-pass.service")
        self.assertNotIn("Before", unit["Unit"])
        self.assertNotIn("DefaultDependencies", unit["Unit"])
        self.assertIn("multi-user.target", unit["Unit"]["After"])
        self.assertIn("ssh.service", unit["Unit"]["After"])
        self.assertNotIn("Install", unit)
        timer = ConfigParser(interpolation=None)
        timer.read(root / "systemd/cmp170-gen2-second-pass.timer")
        self.assertEqual(timer["Timer"]["OnBootSec"], "3min")
        self.assertEqual(timer["Timer"]["Unit"], "cmp170-gen2-second-pass.service")
        self.assertEqual(timer["Install"]["WantedBy"], "timers.target")
