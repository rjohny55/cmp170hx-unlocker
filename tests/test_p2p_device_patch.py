"""P2P defaults must stay on the host, not become GSP registry entries."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from test_p2p_driver import hunks

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCH = ROOT / 'vendor/cmpunlocker/driver/patches/p2p/0016-device-options.patch'


class P2PDevicePatchContext(unittest.TestCase):
    def test_late_bif_defaults_preserve_other_cards_and_explicit_overrides(self):
        cc = shutil.which('gcc') or shutil.which('clang')
        if not cc:
            self.skipTest('C compiler required')
        patch = ROOT / 'vendor/cmpunlocker/driver/patches/p2p/0017-late-bif-defaults.patch'
        _, _, _, new = next(hunks(patch))
        body = ''.join(new[2:-4])
        code = '''#include <assert.h>
typedef unsigned NvU32;
typedef struct bif KernelBif;
struct bif { unsigned pcieP2PType, p2pOverride, disabled[2];
 void (*setProperty)(KernelBif *, unsigned, unsigned); };
struct gpu { struct { unsigned PCIDeviceID; } idInfo; KernelBif *bif; int explicit; };
#define GPU_GET_KERNEL_BIF(p) ((p)->bif)
#define NV_REG_STR_RM_PCIEP2P_TYPE 1
#define NV_REG_STR_CL_FORCE_P2P 2
#define NV_REG_STR_RM_PCIEP2P_TYPE_BAR1 1
#define PDB_PROP_KBIF_P2P_READS_DISABLED 0
#define PDB_PROP_KBIF_P2P_WRITES_DISABLED 1
#define NV_OK 0
#define NV_FALSE 0
static int osReadRegistryDword(struct gpu *p, unsigned key, unsigned *out) {
 (void)key; *out=42; return p->explicit ? NV_OK : 1;
}
static void set(KernelBif *b, unsigned prop, unsigned value) { b->disabled[prop]=value; }
static void late(struct gpu *pGpu) {
''' + body + '''}
int main(void) {
 unsigned ids[]={0x20c2,0x2082,0x2684,0x20b0,0x1e09};
 for(unsigned i=0;i<5;i++) for(int explicit=0;explicit<2;explicit++) {
  KernelBif bif={88,99,{1,1},set}; struct gpu gpu={{ids[i]<<16},&bif,explicit};
  late(&gpu);
  int change=i<2 && !explicit;
  assert(bif.pcieP2PType==(change?1:88));
  assert(bif.p2pOverride==(change?0x11:99));
  assert(bif.disabled[0]==!change && bif.disabled[1]==!change);
 }
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / 'late.c'
            exe = pathlib.Path(tmp) / 'late'
            src.write_text(code)
            subprocess.run([cc, '-std=c99', '-Wall', '-Werror', str(src), '-o', str(exe)],
                           check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, timeout=5)

    def test_host_default_patch_applies_with_zero_fuzz(self):
        target, _, old, new = next(hunks(PATCH))
        self.assertEqual(target, 'src/nvidia/src/kernel/gpu/bus/kern_bus.c')
        self.assertNotIn('rm_write_registry_dword', PATCH.read_text())
        if not shutil.which('patch'):
            self.skipTest('GNU patch is required')
        for padding in (180, 210):
            with self.subTest(padding=padding), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / target
                path.parent.mkdir(parents=True)
                before = '/* unrelated */\n' * padding + ''.join(old) + '/* more */\n' * 50
                path.write_text(before)
                result = subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1'],
                                        input=PATCH.read_text(), cwd=tmp, text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(path.read_text(), before.replace(''.join(old), ''.join(new)))

    def test_static_bar1_default_is_cmp_only(self):
        cc = shutil.which('gcc') or shutil.which('clang')
        if not cc:
            self.skipTest('C compiler required')
        _, _, _, new = next(hunks(PATCH))
        body = ''.join(new)
        code = '''#include <assert.h>
#define NV_REG_STR_RM_FORCE_STATIC_BAR1_ENABLE 1
#define NV_REG_STR_RM_FORCE_STATIC_BAR1_AUTO 2
typedef unsigned NvU32;
struct gpu { struct { NvU32 PCIDeviceID; } idInfo; };
struct bus { NvU32 staticBar1ForceType; };
static unsigned run(unsigned id, int override) {
 struct gpu gpu = {{id << 16}}; struct bus bus = {99};
 struct gpu *pGpu = &gpu; struct bus *pKernelBus = &bus;
 if (override >= 0) { pKernelBus->staticBar1ForceType = override;
''' + body + '''return bus.staticBar1ForceType;
}
int main(void) {
 unsigned ids[] = {0x20c2,0x2082,0x2684,0x20b0,0x1e09};
 for (unsigned i=0;i<5;i++) {
  assert(run(ids[i],-1)==(i<2?1:2));
  assert(run(ids[i],0)==0); assert(run(ids[i],2)==2);
 }
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src=pathlib.Path(tmp)/'test.c'; exe=pathlib.Path(tmp)/'test'
            src.write_text(code)
            subprocess.run([cc,'-std=c99','-Wall','-Werror',str(src),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,timeout=5)
