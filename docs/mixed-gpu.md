# CMP170 and ordinary NVIDIA GPUs

Use one NVIDIA driver release, with matching userspace, GSP firmware and kernel
modules. Do not install competing stock and patched NVIDIA modules for different
cards in the same kernel. CMP-specific unlock and link patches are gated by
PCI device IDs `10de:20c2` / `10de:2082`; RTX 4090 (`10de:2684`) is not a CMP.
The common module is still patched, not a second independently loaded stock
driver. Unrelated devices must retain their ordinary driver paths.

In automatic mode the Gen2 boot helper succeeds without touching drivers or PCI
registers when no supported CMP is present. An explicit nonzero expected count
still fails on missing cards. On mixed hosts the first CMP-only retrain remains
available, but a global unload/FLR second pass is refused to avoid interrupting
other NVIDIA cards. This does not certify mixed hardware or guarantee CMP Gen2.

Before enabling NVIDIA, blacklist nouveau (see `config/nvidia-no-nouveau.conf`)
and update the initramfs for the boot kernel. Do not apply global CMP-only
`NVreg_RegistryDwords` settings to an RTX GPU. Preserve backups before changing
host boot configuration. A GPU whose GSP/MMIO timed out during nouveau startup
may need a full power cycle; changing files does not recover an already wedged
card or prove a successful NVIDIA/CUDA initialization.
