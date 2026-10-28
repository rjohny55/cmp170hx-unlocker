"""Offline PCI-ID guards: no real driver loading or register access."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_p2p_driver import hunks

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "vendor/cmpunlocker/driver/patches"
CC = shutil.which("gcc") or shutil.which("clang")


class DeviceScopeTests(unittest.TestCase):
    def compile_run(self, text):
        if not CC:
            self.skipTest("C compiler unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scope.c"
            binary = Path(tmp) / "scope"
            source.write_text(text)
            r = subprocess.run([CC, "-std=c99", "-Wall", "-Wextra", "-Werror",
                                str(source), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_per_device_defaults_exclude_rtx_and_other_cards(self):
        body = "".join(next(hunks(PATCHES / "cmp-device-options.patch"))[3])
        for p2p in (False, True):
            with self.subTest(p2p=p2p):
                code = body
                if p2p:
                    _, _, old, new = next(hunks(PATCHES / "p2p/0016-device-options.patch"))
                    self.assertIn("".join(old), code)
                    code = code.replace("".join(old), "".join(new))
                self.compile_run('''#include <assert.h>
#include <stddef.h>
#define PCI_VENDOR_ID_NVIDIA 0x10de
struct state { struct { unsigned vendor_id, device_id; } pci_info; };
static int writes;
static void rm_write_registry_dword(void *sp, struct state *nv, const char *key, unsigned value) {
    (void)sp; assert(nv != NULL); assert(key != NULL); assert(value == 1); ++writes;
}
#define nv_init_tegra_gpu_pg_mask(sp, dev) ((void)(sp), (void)(dev))
#define rm_get_gpu_uuid_raw(sp, nv) ((void)(sp), (void)(nv))
static void probe(struct state *nv) {
    void *sp = NULL, *pci_dev = NULL;
''' + code + '''
}
int main(void) {
    unsigned ids[] = {0x20c2, 0x2082, 0x2684, 0x20b0, 0x1db4, 0x1e09};
    for (unsigned i = 0; i < sizeof(ids)/sizeof(ids[0]); ++i) {
        struct state nv = {{0x10de, ids[i]}};
        writes = 0; probe(&nv);
        assert(writes == (i < 2 ? ''' + ("4" if p2p else "2") + ''' : 0));
    }
    struct state other = {{0x1002, 0x20c2}};
    writes = 0; probe(&other); assert(writes == 0);
    return 0;
}
''')

    def test_probe_policy_remains_upstream_without_cmp(self):
        body = "".join(next(hunks(PATCHES / "cmp-probe-serialized.patch"))[3])
        self.compile_run('''#include <assert.h>
#include <stddef.h>
#define NV_PCI_ASYNC_PROBE_SUPPORTED 1
#define PCI_VENDOR_ID_NVIDIA 0x10de
#define PROBE_PREFER_ASYNCHRONOUS 1
#define PROBE_FORCE_SYNCHRONOUS 2
#define NV_TRUE 1
#define smp_store_release(p,v) (*(p) = (v))
static struct { struct { int probe_type; } driver; } nv_pci_driver;
struct pci_dev { unsigned vendor, device; };
static struct pci_dev device;
static int references, nv_pci_driver_registration_in_progress;
static struct pci_dev *pci_get_device(unsigned vendor, unsigned id, void *from) {
    (void)from;
    if (device.vendor == vendor && device.device == id) { ++references; return &device; }
    return NULL;
}
static void pci_dev_put(struct pci_dev *p) { assert(p == &device); --references; }
static void register_driver(void) {
    if (0) { return;
''' + body + '''
}
int main(void) {
    unsigned ids[] = {0x2684, 0x20c2, 0x2082, 0x20b0, 0x1db4, 0x1e09};
    for (unsigned i = 0; i < sizeof(ids)/sizeof(ids[0]); ++i) {
        device.vendor = 0x10de; device.device = ids[i];
        register_driver();
        assert(nv_pci_driver.driver.probe_type == (i == 1 || i == 2 ? 2 : 1));
        assert(references == 0);
    }
    device.vendor = 0x1002; device.device = 0x20c2;
    register_driver(); assert(nv_pci_driver.driver.probe_type == 1);
    return 0;
}
''')

    def test_rebar_does_not_mutate_global_enable_flag(self):
        patch = (PATCHES / "bar1-resize-unlock.patch").read_text()
        self.assertNotIn("+    NVreg_EnableResizableBar =", patch)
        self.assertIn("NVreg_EnableResizableBar == 0 &&", patch)
        self.assertIn("pci_dev->vendor == PCI_VENDOR_ID_NVIDIA", patch)
        self.assertIn("pci_dev->device == 0x20C2 || pci_dev->device == 0x2082", patch)
