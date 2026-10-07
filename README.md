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

During a GPU maintenance window, `sudo bash install-driver.sh auto` prepares
the driver matching the installed NVIDIA userspace version, then installs our
fast service. It disables the author's hammer service, IOMMU/GRUB modifications
and VM passthrough setup. The original bounded endpoint-first → FLR → second
driver pass sequence stays in `scripts/gen2-second-pass.sh`; it is not replaced
by the author's loop. This command changes kernel modules and initramfs; keep
recovery access and do not run it while GPU clients/monitoring are active.

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
