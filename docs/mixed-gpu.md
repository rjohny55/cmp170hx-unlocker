# CMP170 and ordinary NVIDIA GPUs

Use one NVIDIA driver release, with matching userspace, GSP firmware and kernel
modules. Do not install competing stock and patched NVIDIA modules for different
cards in the same kernel. CMP-specific unlock and link patches are gated by
PCI device IDs `10de:20c2` / `10de:2082`; RTX 4090 (`10de:2684`) is not a CMP.
The common module is still patched, not a second independently loaded stock
driver. Unrelated devices must retain their ordinary driver paths.

The 615 build retains the upstream asynchronous probe policy on hosts without
CMP devices. If a supported CMP is present, synchronous driver probing remains
necessary for the multi-CMP RM attach workaround. This ordering policy is shared
by the driver; it is not a claim that every mixed-GPU topology is qualified.
Gen2 driver registry writes and the ReBAR opt-in are selected using the current
device's NVIDIA vendor and CMP device IDs, not a fixed PCI bus address. Replacing
a CMP at that address with an RTX therefore does not inherit CMP options.

An ordinary RTX GPU uses its normal negotiated PCIe capabilities. The CMP Gen2
helper neither caps it at Gen2 nor forces a higher generation on it. Verify
endpoint and upstream-port link capabilities, then measure the current link
under load; an idle link can downshift, and the slot/platform can limit both
generation and lane count.

In automatic mode the Gen2 boot helper succeeds without touching drivers or PCI
registers when no supported CMP is present. An explicit nonzero expected count
still fails on missing cards. On mixed hosts the first CMP-only retrain remains
available, but a global unload/FLR second pass is refused to avoid interrupting
other NVIDIA cards. This does not certify mixed hardware or guarantee CMP Gen2.
Automatic installation also skips without supported CMP devices. Offline staged
driver builds remain possible without a CMP; staging does not load the modules.

The optional P2P mode remains disabled by default and refuses mixed NVIDIA
hosts. Although its registry options are CMP-scoped, its other experimental HAL
and mapping changes have not been qualified for an RTX/CMP mixed host.

Before enabling NVIDIA, blacklist nouveau (see `config/nvidia-no-nouveau.conf`)
and update the initramfs for the boot kernel. Do not apply global CMP-only
`NVreg_RegistryDwords` settings to an RTX GPU. Preserve backups before changing
host boot configuration. A GPU whose GSP/MMIO timed out during nouveau startup
may need a full power cycle; changing files does not recover an already wedged
card or prove a successful NVIDIA/CUDA initialization.
