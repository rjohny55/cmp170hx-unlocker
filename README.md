# CMP 170HX Gen2 second pass

Manual, bounded PCIe Gen2 procedure for NVIDIA CMP 170HX (`10de:20c2` and
`10de:2082`) with a patched `cmpunlocker` driver. The tested sequence is:

1. Initialize the patched NVIDIA driver and read each card's PCIe state.
2. Try endpoint-first, then upstream-port retrain (at most twice per card).
3. If Gen2 fails, unload the idle driver, perform PCIe FLR, and initialize the
   same driver again.
4. Repeat endpoint-first, then upstream-port retrain. Verify both ends and
   `nvidia-smi` after a short stability wait.

This adapts the second-pass and retrain order from
[rjohny55/cmp50-unlock](https://github.com/rjohny55/cmp50-unlock), without
copying TU102 GPU-register writes into GA100. It retains the CMP 170HX
protected-register unlock from
[rjohny55/cmpunlocker](https://github.com/rjohny55/cmpunlocker).

## Driver updates, without replacing our fast activation

The upstream driver source is pinned in `vendor/cmpunlocker` to commit
`17535a0ab1e8d8a9797e096ac5a2495f3da16d2c` (2026-10-05).
`UPSTREAM.json` records the comparison and important changes: additional SM
unlocking, CMP-scoped DRAM/SRAM ECC, profiling support, VFIO helpers and driver
615 compatibility. These are code imports, **not hardware-tested guarantees**.
ECC and newly enabled SMs need memory/error/stability checks before production.

For driver **615.71.09**, our build additionally serializes PCI device probes.
The upstream asynchronous probe path produced RM GPU-lock/attach failures on
the eight-card host 194, with only four cards available after boot. The local
`cmp-probe-serialized.patch` disables that concurrency for 615 only; it keeps
all unlock patches and our bounded Gen2 service. Driver 610 builds are unchanged.
Passing compilation is not a substitute for checking all GPUs after reboot.

On **host 194, 2026-10-08**, upgrading from 610.57.04 to **615.71.09**
and applying this serialization fix restored all **eight** CMP 170HX after
reboot. Every card reported **65536 MiB, Gen2 x16, compute capability 8.0,
and 74 SM** (previously 70). A small Torch CUDA matrix multiplication passed
on each GPU. `cmp170-gen2-second-pass.service` completed with status 0 using
automatic inventory; AI Server Manager and the healthy StackShark containers
restarted. These are startup/smoke checks, not a sustained workload or ECC
qualification. The previous driver packages, modules, initramfs and service
configuration were preserved for rollback under `/var/lib/cmp170-unlock/backups/`.

During a GPU maintenance window, `sudo bash install-driver.sh auto` prepares
the driver matching the installed NVIDIA userspace version, then installs our
fast service. It disables the author's hammer service, IOMMU/GRUB modifications
and VM passthrough setup. The original bounded endpoint-first → FLR → second
driver pass sequence stays in `scripts/gen2-second-pass.sh`; it is not replaced
by the author's loop. This command changes kernel modules and initramfs; keep
recovery access and do not run it while GPU clients/monitoring are active.

## Optional experiments: P2P and HBM control

Both modes are **disabled by default**. Ordinary `install-driver.sh auto` does
not add the optional P2P or HBM patches. Our fast Gen2 activation is unchanged.
The two features are independent and require explicit installer flags:
`--p2p` and `--hbm-control`. They are not automatically activated or tested.

P2P adds experimental BAR1 peer mapping and a real CUDA read/write checker.
HBM control only opens the clock/refresh privilege masks from upstream PR #60;
it does **not** change clock, refresh or timing values, install `170tune`, or
enable an idle-power service. See [experimental modes and test checklist](docs/EXPERIMENTAL.md)
for the opt-in, cold-boot, verification and disable procedures. These modes
have source-context and offline checks, **not hardware qualification**.

## Manual activation

Use a local or SSH shell with recovery access. Stop GPU workloads first. The
script refuses to continue if NVIDIA device files are in use. By default it
automatically processes every supported card enumerated by PCIe:

```bash
sudo bash scripts/gen2-second-pass.sh auto
```

The argument can also be omitted. An explicit positive count, such as `4`,
optionally enforces an exact PCIe enumeration guard. Install the patched driver
before running this script. Required commands: `setpci`, `nvidia-smi`,
`modprobe`, `fuser`, and `flock`. The manual script does not modify the
driver, change BIOS settings, or reboot the host.

## Replace the early boot service

After a manual Gen2 test, install the one-shot second-pass service. Automatic
inventory is the default and is recalculated at every boot, including systems
with 1, 2, 4, or 8 supported cards:

```bash
sudo bash install-service.sh auto
sudo systemctl reboot
```

The installer disables and removes the old `gen2.service`, its timeout
override, and `gen2-hammer`; it keeps copies under
`/var/lib/cmp170-unlock/backups/`. The new service runs before normal services,
has no 600-attempt hammer loop, and has no custom startup timer. After reboot:

```bash
systemctl status cmp170-gen2-second-pass.service
nvidia-smi --query-gpu=pci.bus_id,memory.total,pcie.link.gen.current,pcie.link.width.current --format=csv
```

`sudo bash install-service.sh auto` (or no argument) verifies that supported
cards exist and saves `CMP170_EXPECTED_GPUS=auto`, not today's card count. No
reinstallation is needed when cards are added or removed. The unit also defaults
to `auto` if its optional configuration file is absent. Zero supported cards,
active GPU clients, invalid bridges and missing FLR support still stop activation.
Automatic inventory cannot detect a physically installed card that PCIe failed
to enumerate. For that extra guard, install with an explicit positive count;
an incorrect count fails before changing any files. Previous fast service,
script and configuration files are backed up.

On host 200 on 2026-10-07, the driver was installed, but the service failed:
`detected 4 CMP 170HX, expected 1`. The old `/etc/cmp170-unlock.conf` was stale.
This is independent of model-loading errors. The server root ports currently
advertise only x4 width: Gen2 activation cannot make an x4 port become x16.

After installing the new driver patches and rebooting on 2026-10-07, the fast
service automatically detected all four cards and completed successfully in
48 seconds. All four reached **Gen2 x4**, retained **65536 MiB** each, and Torch
reported **74 SM per card**, versus **70 SM** before the update. This is a 5.7%
increase in reported SM count, not a measured 5.7% application speedup. The
server's DHCP address changed from `192.168.1.200` to `192.168.1.201`; the SSH
host keys confirmed its identity. The panel and containers returned, and mining
resumed on all four cards. Sustained stability, actual ECC protection and model
throughput remain separate validation tasks; the imported ECC reporting
overrides mean an `Enabled` flag alone is not proof of working ECC.

## Verified result and limits

### SM count compared with a stock A100

| GPU / state | SM count per card | FP32 CUDA cores | Change |
| --- | ---: | ---: | --- |
| CMP 170HX on the tested host, before this update | 70 | 4480 | Baseline |
| CMP 170HX on the tested host, after this update | 74 | 4736 | +4 SM / +256 cores, approximately +5.7% |
| Stock NVIDIA A100 (whole GPU, not a MIG partition) | 108 | 6912 | NVIDIA specification |

The A100 count is documented in NVIDIA's
[Ampere architecture description](https://developer.nvidia.com/blog/nvidia-ampere-architecture-in-depth/).
The full GA100 die design has 128 SM, but the shipping A100 exposes 108, not
128. Our observed 74 SM is approximately 68.5% of the A100's SM count (34 fewer
SM). Neither this ratio nor the +5.7% count increase is a measured performance
ratio: clocks, memory bandwidth, enabled features and the workload also matter.
The observed 74 SM is confirmed on the tested cards, not guaranteed for every
CMP 170HX sample.

Torch confirmed compute capability **8.0** and **74 SM** on every card. FP32
core counts are calculated from the GA100 architecture's **64 CUDA cores per
SM**, not read from an independent core-count field: `74 * 64 = 4736` per
card, or **18944** across the four cards (previously 17920).

On 2026-10-07 at 13:45 UTC, `nvidia-smi -q -d ECC` reported **Current: Enabled**
and **Pending: Enabled** on all four GPUs. All reported volatile and aggregate
DRAM/SRAM error counters were zero; repair flags were `No`. These are driver
report values, not independent verification of ECC protection, because the
vendored patch overrides some ECC reporting responses.

### PCIe Gen2 is independent of x4 / x8 / x16 width

The same service handles **Gen2 x4, Gen2 x8 and Gen2 x16**; there is no x4-only
branch, lane-width setting or separate build. GPU count (1, 2, 4 or 8 cards) is
also independent of PCIe lane width.

The service changes only Target Link Speed (`CAP_EXP+30.w=0002:000f`) and the
Retrain Link bit (`CAP_EXP+10.w=0020:0020`), on the endpoint and upstream port.
These masked writes do not force a lane count; negotiated width is determined
by the slot, upstream port, BIOS bifurcation, wiring and successful link
training. An x4 connection cannot be made x16 by this service.

Isolated tests exercise Gen1-to-Gen2 retraining at x4, x8 and x16, including
the FLR/second-driver-pass path, and verify that the service writes only the
speed/retrain masks. Hardware verification with the latest patches includes
**four cards at Gen2 x4 on 610 and eight cards at Gen2 x16 on 615**.
Earlier hardware tests of the same activation sequence reached **Gen2 x16**,
as recorded below. x8 and other x16 servers still need physical verification;
use the same patch and
`install-service.sh auto`, then check both generation and width:

```bash
nvidia-smi --query-gpu=pci.bus_id,pcie.link.gen.current,pcie.link.width.current --format=csv
```

### Earlier hardware checks

On 2026-09-24, one enumerated CMP 170HX (`0000:81:00.0`) on a dual Xeon E5 v4
X99 host, Ubuntu 24.04.5, kernel `6.8.0-142-generic`, patched NVIDIA open driver
`610.57.04`, was initially **Gen1 x16**. Endpoint-first retrain before FLR did
not work: the endpoint's target-speed field returned to Gen1. After FLR and a
second driver initialization, the endpoint advertised and targeted Gen2. The
next endpoint-first/root-port retrain reached **Gen2 x16**; `lspci` and
`nvidia-smi` agreed, and the card still reported **65536 MiB**. See
[`docs/host-test-2026-09-24.md`](docs/host-test-2026-09-24.md).

The second physical CMP 170HX was absent from PCIe enumeration under this X99
BIOS layout; the first card's second-pass and cold-boot results are recorded in
the host-test document. On a separate AMD EPYC server, the method was verified
on **eight** CMP 170HX cards at Gen2 x16 after reboot. All eight retained
65536 MiB. See [`docs/eight-gpu-test-2026-09-24.md`](docs/eight-gpu-test-2026-09-24.md).
