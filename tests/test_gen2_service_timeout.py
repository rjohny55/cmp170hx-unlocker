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
