"""HBM identity checker tests, with redirected system paths and no real GPU."""
import subprocess
import test_p2p_check as fixtures
import unittest


class HBMCheckTests(unittest.TestCase):
    def setUp(self):
        self.host = fixtures.P2PCheckTests("runTest")
        self.host.setUp()
        self.addCleanup(self.host.doCleanups)
        script = self.host.project / "scripts/check-hbm.sh"
        code = script.read_text()
        for prefix in ("/lib/modules/", "/sys/"):
            code = code.replace(prefix, str(self.host.base / "system") + prefix)
        script.write_text(code)
        self.script = script
        self.flag = self.host.base / f"system/lib/modules/{self.host.kernel}/updates/cmpunlocker/hbm_control_enabled"
        self.flag.write_text("1\n")

    def run_check(self, *args):
        return subprocess.run(["bash", str(self.script), *args], env=self.host.env,
                              text=True, capture_output=True, timeout=10)

    def test_status_does_not_claim_register_or_memory_validation(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NOT verified", result.stdout)
        self.assertFalse(self.host.calls.exists())

    def test_disabled_build_does_not_pass(self):
        self.flag.write_text("0\n")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("disabled", result.stderr)

    def test_old_loaded_module_requires_cold_boot(self):
        (self.host.base / "system/sys/module/nvidia/srcversion").write_text("OLD\n")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cold boot first", result.stderr)


if __name__ == "__main__":
    unittest.main()
