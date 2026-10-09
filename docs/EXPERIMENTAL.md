# Experimental CMP 170HX modes

## Scope and defaults

P2P and HBM control are independent **opt-in** driver-build modes. Neither is
in the default patch list. Ordinary installation keeps the existing unlocks,
615 serialized probing and our bounded Gen2 second-pass service. No GPU tests,
reboot or automatic power-cycle are performed by the installer.

The source imports remain under the vendored GPL-2.0 license:

- P2P: [upstream PR #54](https://github.com/amoghmunikote/cmpunlocker/pull/54),
  revision `b03855bc95be2f815892c5e336152f255d3e6d42`, from
  `sayhellotojungle/cmpunlocker`, based on Bayley's P2P work. Our integration
  adapts source context for 615, preserves IOVAS diagnostics and removes the
  unrelated Blackwell coherency/global ReBAR changes.
- HBM: [upstream PR #60](https://github.com/amoghmunikote/cmpunlocker/pull/60),
  revision `6e0d2e3ca3124c743233065dada24097a2e93e32`, by `cibernox`, with
  register provenance attributed there to `asm64-hooligan` and `bayley`.
  We combine the five new PLMs and the dynamic loop bound in one optional
  patch, rather than changing the baseline loop or enabling HBM by default.

These are experiments, not assertions of production stability or speedup.

## Installation and disabling

Use an SSH/local recovery console during a GPU maintenance window. Stop GPU
workloads, mining and monitoring clients first. Keep a known-good driver,
initramfs and rollback path. The installed userspace NVIDIA version must be
one of `615.71.09`, `610.57.04`, `610.43.03`, `610.43.02`; the wrapper matches
that version and does not automatically upgrade the driver.

```bash
# Default: neither optional feature.
sudo bash install-driver.sh auto

# Select only the experiment needed, or explicitly select both.
sudo bash install-driver.sh auto --p2p
sudo bash install-driver.sh auto --hbm-control
sudo bash install-driver.sh auto --p2p --hbm-control

# Rebuild without either feature.
sudo bash install-driver.sh auto --no-p2p --no-hbm-control
```

After enabling **or disabling** either experiment, installation deliberately
skips live module reload. Successfully rebuild initramfs, then manually perform
a **cold boot** (power off/on) in the maintenance window and verify the loaded
module. A failed initramfs rebuild is an error, not a boot-ready result.
Reinstalling without flags removes previously selected experiments for the
next cold boot. HBM register settings already changed by another tool require
that tool's verified restore procedure; removing permissions is not a reset.

The installer records `p2p_enabled` and `hbm_control_enabled` with the installed
modules. Switching either mode invalidates the cached driver source/build
stamp; a patch-byte change does too. Exported feature environment variables
cannot silently enable a mode through either installer: explicit flags win.
The low-level build API accepts `CMPUNLOCKER_ENABLE_P2P=0|1` and
`CMPUNLOCKER_ENABLE_HBM=0|1` for deliberate staging builds only when chosen by
the caller; do not invoke it casually on a live host.

## P2P prerequisites and checking

The integration refuses P2P on a host with non-CMP NVIDIA GPUs: the imported
patch changes shared HAL defaults. At least two CMP GPUs are required. Firmware
must assign a sufficiently large BAR1 (64 GiB for `20c2`, 40 GiB for `2082`),
usually requiring Above-4G decoding and enough MMIO space. PCIe switch/root-port
routing, ACS and IOMMU policy can still prevent real peer access. This installer
does not disable IOMMU/ACS or modify BIOS/GRUB settings to force success.

```bash
# Read-only: installed/loaded module identity, active options, BAR1, matrices.
bash scripts/check-p2p.sh --status

# Explicit GPU workload: both read and write kernels, selected CUDA indices.
sudo bash scripts/check-p2p.sh --test 0 1

# With no indices, exercise all directed pairs of visible CUDA GPUs.
sudo bash scripts/check-p2p.sh --test
```

The data test requires `nvcc`, `timeout`, `fuser`, `flock`, root and idle GPUs.
It checks 16 MiB per endpoint with different initial patterns, reads both
endpoints back, and returns nonzero on mismatches or CUDA errors. It does not
reset GPUs or install modules. The timeout is 120 seconds plus a five-second
kill grace; it cannot recover a hung GPU/driver, and large topologies may need
testing in smaller groups. GPU indices are CUDA indices, not PCI bus numbers.

`nvidia-smi topo -p2p` is **not proof of transfers**: capability overrides can
say OK for a broken mapping. The imported IOVAS changes avoid assertions in
the experiment but do not prove the mapping lifecycle correct; retained
diagnostic warnings still require investigation. Passing the small correctness
test is not a bandwidth benchmark, NCCL qualification or sustained-load proof.

## HBM access and idle power

The optional HBM patch opens `FBPA_MEM`, `FBPA_PLL0`, `FBPA_PLL1`, `FBPA_PLL2`
and `FBPA0_PLL`, and replaces the literal PLM-loop limit with the table size.
It does not change SM count, VRAM size, HBM clock, refresh interval or timings.

```bash
bash scripts/check-hbm.sh --status
```

This read-only checker confirms build metadata and the identity of the loaded
module. It explicitly does **not** verify register writes or memory integrity.
Review a tuning tool separately and perform per-card preflight before changing
registers. Do not infer working HBM access from an old boot log.

The idle-power daemon is a separate, unmerged
[170tune PR #9](https://github.com/cachenetics/170tune/pull/9), not included,
installed or enabled here. Its author's reported savings are not our results.
Do not automatically copy refresh values or assume an `ECC Enabled` report
proves protection: our baseline includes ECC reporting overrides. Refresh/PLL
experiments may silently corrupt resident model weights or hang a GPU, even
without an Xid. Validate retention at temperature, repeated transitions,
long-idle behavior, rollback and model/output correctness on every card.

## Validation checklist

- [x] Default installers leave both modes disabled.
- [x] Explicit flags and independent P2P/HBM combinations covered offline.
- [x] Staging does not modify running modules or initramfs.
- [x] Feature/patch-byte changes invalidate the build stamp.
- [x] Identity checkers do not claim hardware transfer or HBM validation.
- [ ] Build full kernel modules for the target host kernel/driver.
- [ ] Verify enable/disable across a real cold boot.
- [ ] Check actual P2P reads/writes, then NCCL/application throughput.
- [ ] Validate HBM access, memory retention, temperature and long-term stability.
- [ ] Exercise recovery and rollback on the target machine.

Offline tests use redirected filesystem fixtures and mocked privileged commands.
`Dockerfile.tests` compiles the real CUDA test binary without accessing GPUs.
For pristine NVIDIA source context checks (no changes to the supplied tree):

```bash
python3 scripts/check-p2p-source.py --source /path/to/pristine/nvidia --version 615.71.09
python3 scripts/check-hbm-source.py --source /path/to/pristine/nvidia --version 615.71.09
```

These targeted context checks are not a full module build or hardware test.
