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

## Run

Use a local or SSH shell with recovery access. Stop GPU workloads first. The
script refuses to continue if NVIDIA device files are in use or if the number
of enumerated cards differs from the count you supply:

```bash
sudo bash scripts/gen2-second-pass.sh 1
```

Replace `1` with the number of CMP 170HX cards physically expected. Install
the patched driver before running this script. Required commands: `setpci`,
`nvidia-smi`, `modprobe`, and `fuser`. The manual script does not modify the
driver, change BIOS settings, or reboot the host.

## Replace the early boot service

After a manual Gen2 test, install the one-shot second-pass service. The count
is an exact PCIe enumeration guard; use the number of cards physically expected
to be detected:

```bash
sudo bash install-service.sh 1
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

## Verified result and limits

On 2026-09-24, one enumerated CMP 170HX (`0000:81:00.0`) on a dual Xeon E5 v4
X99 host, Ubuntu 24.04.5, kernel `6.8.0-142-generic`, patched NVIDIA open driver
`610.57.04`, was initially **Gen1 x16**. Endpoint-first retrain before FLR did
not work: the endpoint's target-speed field returned to Gen1. After FLR and a
second driver initialization, the endpoint advertised and targeted Gen2. The
next endpoint-first/root-port retrain reached **Gen2 x16**; `lspci` and
`nvidia-smi` agreed, and the card still reported **65536 MiB**. See
[`docs/host-test-2026-09-24.md`](docs/host-test-2026-09-24.md).

The second physical CMP 170HX was absent from PCIe enumeration under this BIOS
layout, so this method has **not** been verified on two cards. The manual
second-pass sequence and one automated cold boot were verified on the first
card; the boot result is recorded in the host-test document.
