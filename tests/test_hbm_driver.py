"""Offline HBM opt-in tests. No memory clocks, real modules or GPUs touched."""
import hashlib
import test_p2p_driver as fixtures
import unittest


class HBMIntegration(unittest.TestCase):
    def setUp(self):
        self.host = fixtures.P2PIntegration("runTest")
        self.host.setUp()
        self.addCleanup(self.host.doCleanups)

    def test_baseline_has_no_hbm_patch_and_records_disabled(self):
        events = self.host.successful_build()
        self.assertEqual(sum(e["cmd"] == "patch" for e in events), 15)
        self.assertEqual((self.host.moddir / "hbm_control_enabled").read_text(), "0\n")

    def test_hbm_enable_disable_rebuilds_without_live_reload(self):
        self.host.successful_build()
        stamp = self.host.build_root / self.host.src_name / ".cmpunlocker-stamp"
        baseline = stamp.read_text()
        events = self.host.successful_build(CMPUNLOCKER_ENABLE_HBM="1")
        patches = [e for e in events if e["cmd"] == "patch"]
        self.assertEqual(len(patches), 16)
        patch = self.host.project / "driver/patches/hbm/hbm-control-plm.patch"
        self.assertEqual(patches[-1]["sha256"], hashlib.sha256(patch.read_bytes()).hexdigest())
        self.assertIn("--fuzz=0", patches[-1]["args"])
        self.assertNotEqual(stamp.read_text(), baseline)
        self.assertEqual((self.host.moddir / "hbm_control_enabled").read_text(), "1\n")
        self.assertNotIn("StaticBar1", self.host.conf.read_text())
        self.assertFalse(any(e["cmd"] == "modprobe" for e in events))
        events = self.host.successful_build(CMPUNLOCKER_ENABLE_HBM="0")
        self.assertEqual(sum(e["cmd"] == "patch" for e in events), 15)
        self.assertEqual(stamp.read_text(), baseline)
        self.assertEqual((self.host.moddir / "hbm_control_enabled").read_text(), "0\n")
        self.assertFalse(any(e["cmd"] == "modprobe" for e in events))

    def test_hbm_and_p2p_compose_and_stage_without_activation(self):
        stage = self.host.tmp / "inactive-experimental"
        events = self.host.successful_build("1", CMPUNLOCKER_ENABLE_HBM="1",
                                            CMPUNLOCKER_STAGE_DIR=str(stage))
        self.assertEqual(sum(e["cmd"] == "patch" for e in events), 20)
        self.assertEqual((stage / "hbm_control_enabled").read_text(), "1\n")
        self.assertEqual((stage / "p2p_enabled").read_text(), "1\n")
        self.assertFalse(any(e["cmd"] in ("depmod", "modprobe", "update-initramfs") for e in events))

    def test_invalid_hbm_setting_fails_before_mutation(self):
        result = self.host.run_script(CMPUNLOCKER_ENABLE_HBM="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be 0 or 1", result.stdout + result.stderr)
        self.assertFalse(any(e["cmd"] in ("patch", "make", "depmod") for e in self.host.events()))

    def test_hbm_refuses_busy_or_unverifiable_gpu_clients(self):
        for status in ("0", "2"):
            result = self.host.run_script(CMPUNLOCKER_ENABLE_HBM="1", MOCK_FUSER_STATUS=status)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any(e["cmd"] in ("patch", "make", "depmod") for e in self.host.events(clear=True)))

    def test_failed_initramfs_is_not_a_ready_hbm_install(self):
        result = self.host.run_script(CMPUNLOCKER_ENABLE_HBM="1", FAIL_INITRAMFS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("initramfs was not rebuilt", result.stdout + result.stderr)
        self.assertFalse(any(e["cmd"] == "modprobe" for e in self.host.events()))

    def test_hbm_patch_revision_invalidates_cached_build(self):
        self.host.successful_build(CMPUNLOCKER_ENABLE_HBM="1")
        patch = self.host.project / "driver/patches/hbm/hbm-control-plm.patch"
        patch.write_text("Fixture revision\n" + patch.read_text())
        events = self.host.successful_build(CMPUNLOCKER_ENABLE_HBM="1")
        self.assertEqual(sum(e["cmd"] == "patch" for e in events), 16)

    def test_failed_hbm_patch_does_not_install_or_stamp(self):
        result = self.host.run_script(CMPUNLOCKER_ENABLE_HBM="1", FAIL_PATCH="FBPA_PLL0")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.host.moddir / "hbm_control_enabled").exists())
        self.assertFalse((self.host.build_root / self.host.src_name / ".cmpunlocker-stamp").exists())

    def test_installer_ignores_exported_hbm_and_forwards_only_explicit_flags(self):
        result = self.host.run_script("install.sh", ("--no-gen2-service", "--no-iommu", "--no-passthrough"),
                                      CMPUNLOCKER_ENABLE_HBM="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.host.moddir / "hbm_control_enabled").read_text(), "0\n")
        self.host.events(clear=True)
        result = self.host.run_script("install.sh", ("--hbm-control", "--no-gen2-service", "--no-iommu", "--no-passthrough"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.host.moddir / "hbm_control_enabled").read_text(), "1\n")

    def test_optional_patch_does_not_set_clocks_or_refresh(self):
        patch = (fixtures.ROOT / "driver/patches/hbm/hbm-control-plm.patch").read_text()
        changes = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        self.assertEqual(changes.count('0xffffffffU, "FBPA'), 5)
        self.assertIn("NV_ARRAY_ELEMENTS(plmTable)", changes)
        self.assertNotIn("GPU_REG_WR32", changes)
        self.assertNotIn("idle_power", changes)


if __name__ == "__main__":
    unittest.main()
