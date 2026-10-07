import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FastActivationTests(unittest.TestCase):
    def test_inventory_counts_only_supported_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, (vendor, device) in enumerate([
                ("0x10de", "0x20c2"), ("0x10de", "0x2082"),
                ("0x10de", "0x20c2"), ("0x10de", "0x20b0"),
                ("0x1002", "0x20c2"),
            ]):
                gpu = root / f"0000:{i:02x}:00.0"
                gpu.mkdir()
                (gpu / "vendor").write_text(vendor)
                (gpu / "device").write_text(device)
            result = subprocess.run(["bash", "-c", 'source "$1"; cmp170_gpu_count "$2"',
                                     "inventory-test", str(ROOT / "scripts/inventory.sh"), str(root)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), "3")

    def test_stale_count_is_rejected(self):
        for expected, actual, ok in [("1", "4", False), ("4", "4", True),
                                     ("0", "0", False), ("x", "4", False)]:
            with self.subTest(expected=expected, actual=actual):
                result = subprocess.run(["bash", "-c", 'source "$1"; cmp170_check_expected "$2" "$3"',
                                         "guard-test", str(ROOT / "scripts/inventory.sh"), expected, actual],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, ok)

    def test_auto_activation_handles_current_inventory_at_each_boot(self):
        # Exercise the actual activation script with isolated sysfs and command
        # fixtures. No real PCI registers, device files or driver are touched.
        original = (ROOT / "scripts/gen2-second-pass.sh").read_text()
        for count, args, ok in [(1, [], True), (2, ["auto"], True),
                                (4, [], True), (8, ["auto"], True),
                                (0, [], False), (4, ["1"], False),
                                (4, ["4"], True)]:
            with self.subTest(count=count, args=args), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                sysfs = base / "sysfs"
                sysfs.mkdir()
                for i in range(count):
                    port = base / "pci" / f"0000:00:{i + 1:02x}.0"
                    port.mkdir(parents=True)
                    (port / "class").write_text("0x060400\n")
                    (sysfs / port.name).symlink_to(port, target_is_directory=True)
                    gpu = port / f"0000:{i + 1:02x}:00.0"
                    gpu.mkdir()
                    (gpu / "vendor").write_text("0x10de\n")
                    (gpu / "device").write_text("0x20c2\n" if i % 2 == 0 else "0x2082\n")
                    (gpu / "reset").touch()
                    (sysfs / gpu.name).symlink_to(gpu, target_is_directory=True)
                commands = base / "bin"
                commands.mkdir()
                # Already-Gen2 fixture avoids writes; sleep is mocked to make
                # the final stability wait deterministic and fast.
                for name, body in {
                    "fuser": "exit 1",
                    "modprobe": "printf 'MOCK_DRIVER_CALLED\\n'",
                    "nvidia-smi": "exit 0",
                    "setpci": "printf '0002\\n'",
                    "sleep": "exit 0",
                }.items():
                    command = commands / name
                    command.write_text("#!/bin/sh\n" + body + "\n")
                    command.chmod(0o755)
                script = base / "activation.sh"
                script.write_text(original.replace(
                    "[[ ${EUID} -eq 0 ]] || die 'run as root'", ": # fixture only"
                ).replace("/sys/bus/pci/devices", str(sysfs)).replace(
                    "/run/cmp170-gen2-second-pass.lock", str(base / "activation.lock")
                ).replace("/dev/nvidia", str(base / "dev-nvidia")))
                result = subprocess.run([
                    "bash", "-c", 'export PATH="$1:$PATH"; shift; exec bash "$@"',
                    "activation-test", str(commands), str(script), *args,
                ], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
                if ok:
                    self.assertIn(f"PASS: {count} detected CMP 170HX cards", result.stdout)
                else:
                    self.assertNotIn("MOCK_DRIVER_CALLED", result.stdout)

    def test_install_checks_before_mutating_and_keeps_boot_guard(self):
        install = (ROOT / "install-service.sh").read_text()
        self.assertLess(install.index('cmp170_check_expected "$expected_count" "$actual_count"'),
                        install.index('mkdir -p "$backup_dir"'))
        service = (ROOT / "systemd/cmp170-gen2-second-pass.service").read_text()
        self.assertIn("${CMP170_EXPECTED_GPUS}", service)
        self.assertIn("Environment=CMP170_EXPECTED_GPUS=auto", service)
        self.assertIn("EnvironmentFile=-/etc/cmp170-unlock.conf", service)
        self.assertIn('"$requested_count" > /etc/cmp170-unlock.conf', install)
        self.assertNotIn("gen2-hammer", service)
        activation = (ROOT / "scripts/gen2-second-pass.sh").read_text()
        self.assertIn("for pass in 1 2", activation)
        self.assertIn('"/sys/bus/pci/devices/${gpu}/driver/unbind"', activation)
        self.assertIn('printf \'1\\n\' > "/sys/bus/pci/devices/${gpu}/reset"', activation)
        self.assertIn('setpci -s "$gpu" CAP_EXP+10.w=0020:0020', activation)
        self.assertLess(activation.index('setpci -s "$gpu" CAP_EXP+10.w=0020:0020'),
                        activation.index('setpci -s "$port" CAP_EXP+10.w=0020:0020'))

    def test_driver_install_cannot_enable_author_hammer_or_vfio(self):
        wrapper = (ROOT / "install-driver.sh").read_text()
        self.assertIn("--no-gen2-service --no-iommu --no-passthrough", wrapper)
        self.assertIn('bash "$repo_dir/install-service.sh" "$requested_count"', wrapper)
        self.assertIn('fuser /dev/nvidia*', wrapper)
        pin = json.loads((ROOT / "UPSTREAM.json").read_text())
        self.assertEqual(pin["revision"], "17535a0ab1e8d8a9797e096ac5a2495f3da16d2c")

    def test_staging_never_activates_modules(self):
        build = (ROOT / "vendor/cmpunlocker/driver/build.sh").read_text()
        staging = build.index('ok "Modules staged at')
        self.assertLess(staging, build.index('depmod -a "${KVER}"'))
        self.assertIn('exit 0', build[staging:build.index('depmod -a "${KVER}"')])

    def test_bash_syntax(self):
        for script in ROOT.rglob("*.sh"):
            if ".git" in script.parts or ".build" in script.parts:
                continue
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
