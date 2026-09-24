# Eight-GPU host test: 2026-09-24

Host: Gigabyte server with AMD EPYC 7402P, Ubuntu 24.04.5, kernel
`6.8.0-142-generic`, eight `10de:20c2` CMP 170HX cards behind PMC-Sierra
`11f8:4052` PCIe switch downstream ports. Secure Boot was disabled.

Installed `nvidia-headless-610-open` and `nvidia-utils-610` version `610.57.04`,
then [`rjohny55/cmpunlocker`](https://github.com/rjohny55/cmpunlocker) commit
`88e39ce67488796b2c6c716fe8f9b4e6e943a55e` with
`--no-gen2-service --no-passthrough`. Its patched module reported srcversion
`44F04FA69F667FB5CF4F090`. The install configured
`amd_iommu=on iommu=pt` for the next boot.

Before Gen2 retrain, `nvidia-smi` showed all eight cards at 65536 MiB, Gen1 x16.
Running `gen2-second-pass.sh 8` manually reached Gen2 x16 on all eight in the
first endpoint-first/root-port pass; no FLR was needed on this host.

Installed `cmp170-gen2-second-pass.service` with an exact count of eight and
rebooted. At 18:49 UTC, the boot service initialized all eight GPUs, saw Gen1
x16 on each, and retrained all eight to Gen2 x16 on the first pass. The unit
finished with `Result=success` and `ExecMainStatus=0`. `nvidia-smi` after boot
reported all eight at **65536 MiB, Gen2 x16**. The fork's `verify.sh` exited 0
and marked memory unlock and Gen2 successful on 8/8 cards. The boot journal
had no matching NVIDIA Xid, PCIe bus error, or fatal AER message in the checked
patterns. The old `gen2.service` was not installed.

PCI BDFs: `03:00.0`, `04:00.0`, `43:00.0`, `44:00.0`, `88:00.0`, `89:00.0`,
`c3:00.0`, `c4:00.0` (domain `0000`). This test covers one reboot and does not
establish long-term workload stability.
