"""Check orchestration against isolated sysfs/commands, not real CUDA transfers."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class P2PCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        shutil.copytree(ROOT / "scripts", self.project / "scripts")
        shutil.copytree(ROOT / "vendor/cmpunlocker/common", self.project / "vendor/cmpunlocker/common")
        self.commands = self.base / "commands"
        self.commands.mkdir()
        for file in (self.project / "scripts/check-p2p.sh", self.project / "scripts/inventory.sh",
                     self.project / "vendor/cmpunlocker/common/p2p.sh"):
            code = file.read_text()
            for prefix in ("/lib/modules/", "/sys/", "/proc/", "/run/", "/dev/"):
                code = code.replace(prefix, str(self.base / "system") + prefix)
            code = code.replace('[[ $EUID == 0 ]]', '[[ 0 == 0 ]]')
            file.write_text(code)
        self.kernel = os.uname().release
        module = self.base / f"system/lib/modules/{self.kernel}/updates/cmpunlocker"
        module.mkdir(parents=True)
        (module / "p2p_enabled").write_text("1\n")
        (module / "nvidia.ko").write_text("mock module\n")
        for relative, text in {
            "sys/module/nvidia/srcversion": "MATCH\n",
            "proc/driver/nvidia/params": 'RegistryDwords: "RMForceStaticBar1=1;RMPcieP2PType=1"\n',
        }.items():
            file = self.base / "system" / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text)
        (self.base / "system/run").mkdir()
        (self.base / "system/dev").mkdir()
        (self.base / "system/dev/null").touch()
        self.sysfs = self.base / "system/sys/bus/pci/devices"
        for i in (1, 2):
            gpu = self.sysfs / f"0000:{i:02x}:00.0"
            gpu.mkdir(parents=True)
            for name, content in {
                "vendor": "0x10de\n", "device": "0x20c2\n", "class": "0x030200\n",
                "resource": "0 0 0\n1000000000 1fffffffff 200\n",
            }.items():
                (gpu / name).write_text(content)
        self.calls = self.base / "calls"
        for name, body in {
            "modinfo": "echo MATCH",
            "nvidia-smi": 'printf "nvidia-smi %s\\n" "$*" >> "$TEST_CALLS"',
            "fuser": 'exit "${TEST_BUSY:-1}"',
            "nvcc": '''printf "nvcc %s\\n" "$*" >> "$TEST_CALLS"
while [[ $# -gt 0 ]]; do
    if [[ $1 == -o ]]; then
        shift
        printf '#!/bin/sh\nprintf "fake-cuda %%s\\n" "$*" >> "$TEST_CALLS"\n' > "$1"
        chmod +x "$1"
        break
    fi
    shift
done''',
        }.items():
            file = self.commands / name
            file.write_text("#!/bin/bash\nset -eu\n" + body + "\n")
            file.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.commands) + ":" + os.environ["PATH"],
                    "TEST_CALLS": str(self.calls)}

    def run_check(self, *args, **env):
        return subprocess.run(["bash", str(self.project / "scripts/check-p2p.sh"), *args],
                              env={**self.env, **env}, text=True, capture_output=True, timeout=10)

    def test_default_status_never_compiles_or_claims_verified_transfers(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("data transfer is NOT verified", result.stdout)
        self.assertNotIn("nvcc", self.calls.read_text())
        self.assertNotIn("fake-cuda", self.calls.read_text())

    def test_old_running_module_requires_cold_boot(self):
        (self.base / "system/sys/module/nvidia/srcversion").write_text("OLD\n")
        result = self.run_check("--test", "0", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cold boot first", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_missing_active_option_is_not_accepted_as_enabled(self):
        (self.base / "system/proc/driver/nvidia/params").write_text('RegistryDwords: ""\n')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not active", result.stderr)

    def test_small_bar_is_rejected_before_cuda_launch(self):
        (self.sysfs / "0000:01:00.0/resource").write_text("0 0 0\n1000000000 100fffffff 200\n")
        result = self.run_check("--test")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BAR1 does not cover framebuffer", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_busy_gpus_are_rejected_before_compilation(self):
        result = self.run_check("--test", TEST_BUSY="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("in use", result.stderr)
        self.assertNotIn("nvcc", self.calls.read_text())

    def test_test_mode_passes_selected_gpu_indices_without_resetting_driver(self):
        result = self.run_check("--test", "0", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text()
        self.assertIn("nvcc -O2 -arch=sm_80", calls)
        self.assertIn("fake-cuda 0 1", calls)
        self.assertNotIn("modprobe", calls)

    def test_busy_check_error_does_not_allow_cuda_test(self):
        result = self.run_check("--test", TEST_BUSY="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not verify", result.stderr)
        self.assertNotIn("nvcc", self.calls.read_text())

    def test_help_does_not_require_gpu_or_installation(self):
        shutil.rmtree(self.base / "system")
        result = self.run_check("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--test", result.stdout)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
