"""Isolated installer tests: no real GPU, module or system files are changed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class P2PModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        shutil.copytree(ROOT / "scripts", self.project / "scripts")
        shutil.copytree(ROOT / "vendor/cmpunlocker/common", self.project / "vendor/cmpunlocker/common")
        self.sysfs = self.base / "sysfs"
        self.sysfs.mkdir()
        self.cards(["0x20c2", "0x2082"])
        self.calls = self.base / "calls"
        (self.project / "vendor/cmpunlocker/install.sh").write_text(
            '#!/bin/bash\nprintf "driver %s p2p=%s hbm=%s\\n" "$*" "${CMPUNLOCKER_ENABLE_P2P:-unset}" "${CMPUNLOCKER_ENABLE_HBM:-unset}" >> "$TEST_CALLS"\n')
        (self.project / "install-service.sh").write_text(
            '#!/bin/bash\nprintf "service %s\\n" "$*" >> "$TEST_CALLS"\n')
        script = (ROOT / "install-driver.sh").read_text().replace(
            '[[ $EUID -eq 0 ]]', '[[ 0 -eq 0 ]]').replace(
            'cmp170_gpu_count)', 'cmp170_gpu_count "' + str(self.sysfs) + '")').replace(
            'cmp_p2p_check_host', 'cmp_p2p_check_host "' + str(self.sysfs) + '"').replace(
            '/run/cmp170-driver-install.lock', str(self.base / "lock"))
        (self.project / "install-driver.sh").write_text(script)
        driver = self.project / "vendor/cmpunlocker/driver"
        driver.mkdir()
        shutil.copy(ROOT / "vendor/cmpunlocker/driver/VERSION", driver / "VERSION")
        bindir = self.base / "bin"
        bindir.mkdir()
        for name, body in {"fuser": "exit 1", "modinfo": "echo 615.71.09"}.items():
            command = bindir / name
            command.write_text("#!/bin/sh\n" + body + "\n")
            command.chmod(0o755)
        self.env = {**os.environ, "PATH": str(bindir) + ":" + os.environ["PATH"],
                    "TEST_CALLS": str(self.calls)}

    def cards(self, devices):
        for old in self.sysfs.iterdir():
            shutil.rmtree(old)
        for i, device in enumerate(devices):
            gpu = self.sysfs / f"0000:{i + 1:02x}:00.0"
            gpu.mkdir()
            for name, value in {"vendor": "0x10de", "device": device,
                                "class": "0x030200"}.items():
                (gpu / name).write_text(value + "\n")

    def run_install(self, *args, **env):
        return subprocess.run(["bash", str(self.project / "install-driver.sh"), *args],
                              env={**self.env, **env}, capture_output=True, text=True, timeout=10)

    def test_default_ignores_exported_feature_and_keeps_fast_service(self):
        result = self.run_install("auto", CMPUNLOCKER_ENABLE_P2P="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text()
        self.assertIn("--no-gen2-service --no-iommu --no-passthrough", calls)
        self.assertIn("p2p=0", calls)
        self.assertIn("service auto", calls)

    def test_explicit_feature_is_forwarded_and_no_service_is_started(self):
        result = self.run_install("auto", "--p2p")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text()
        self.assertIn("--p2p", calls)
        self.assertIn("p2p=1", calls)
        self.assertIn("service auto", calls)
        self.assertNotIn("reboot", calls)

    def test_explicit_disable_is_forwarded(self):
        result = self.run_install("auto", "--no-p2p", CMPUNLOCKER_ENABLE_P2P="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("p2p=0", self.calls.read_text())

    def test_hbm_defaults_off_even_with_exported_feature(self):
        result = self.run_install("auto", CMPUNLOCKER_ENABLE_HBM="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("hbm=0", self.calls.read_text())

    def test_hbm_is_independent_from_p2p_and_supports_one_card(self):
        self.cards(["0x20c2"])
        result = self.run_install("auto", "--hbm-control")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("p2p=0 hbm=1", self.calls.read_text())

    def test_both_features_require_explicit_selection(self):
        result = self.run_install("auto", "--p2p", "--hbm-control")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("p2p=1 hbm=1", self.calls.read_text())

    def test_explicit_hbm_disable_wins_over_enable(self):
        result = self.run_install("auto", "--hbm-control", "--no-hbm-control")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("hbm=0", self.calls.read_text())

    def test_mixed_nvidia_host_is_rejected_before_driver_install(self):
        self.cards(["0x20c2", "0x2082", "0x20b0"])
        result = self.run_install("auto", "--p2p")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mixed NVIDIA", result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())

    def test_single_card_has_no_p2p_pair_and_is_rejected(self):
        self.cards(["0x20c2"])
        result = self.run_install("auto", "--p2p")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least two", result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())

    def test_unknown_option_is_rejected_before_mutation(self):
        result = self.run_install("auto", "--p2p=yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_base_driver_and_gen2_are_not_overwritten_by_feature(self):
        build = (ROOT / "vendor/cmpunlocker/driver/build.sh").read_text()
        self.assertIn("cmp-probe-serialized.patch", build)
        self.assertIn("ecc-enable.patch", build)
        self.assertIn("CMPUNLOCKER_STAGE_DIR", build)
        pin = json.loads((ROOT / "UPSTREAM.json").read_text())
        self.assertEqual(pin["revision"], "17535a0ab1e8d8a9797e096ac5a2495f3da16d2c")


if __name__ == "__main__":
    unittest.main()
