#!/usr/bin/env bash
# Install verified inactive modules for next boot. Never unload a live GPU.
set -Eeuo pipefail
[[ $EUID == 0 && $(uname -r) == 7.0.0-38-generic ]]
base=/var/lib/cmp170-unlock/scope-168-20261028
target=/lib/modules/7.0.0-38-generic/updates/cmpunlocker
backup=$base/backup
[[ -d $base/modules && -d $target && ! -e $backup ]]
[[ $(modinfo -F version nvidia) == 615.71.09 ]]
[[ $(readlink -f /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1) == */libnvidia-ml.so.615.71.09 ]]
[[ ! -e /etc/modprobe.d/cmp-pcie-gen2.conf ]]
grep -Fxq 'blacklist nouveau' /etc/modprobe.d/asm-nvidia-no-nouveau.conf
# Freeze the exact staged set reviewed before activation; no download/install
# of NVIDIA userspace or firmware is performed here.
declare -A sums=(
    [nvidia]=2359c9bd1e8609a75bd52efedef7537d0711dae03b8aa6705924b86e4c5ed343
    [nvidia-drm]=4852f24f312efadf731c8a13886f8d88aa9aa2fc65315b440e9c3f340f07b6e4
    [nvidia-modeset]=158615caeb83cec72aa8497142e986eae2f56e393cb9e2143239d47103d0be63
    [nvidia-peermem]=8470b0d49d0ef104ab3514a24b20baa59031fcd9f2fab951e53d3a005645fcfc
    [nvidia-uvm]=8e2ff6526bfe9b1f96338b93112f2af61613eafc2243f5c0aa8a79e75452b9da
)
for name in nvidia nvidia-drm nvidia-modeset nvidia-peermem nvidia-uvm; do
    [[ $(sha256sum "$base/modules/$name.ko" | cut -d' ' -f1) == "${sums[$name]}" ]]
    [[ $(modinfo -F version "$base/modules/$name.ko") == 615.71.09 ]]
    [[ $(modinfo -F vermagic "$base/modules/$name.ko") == '7.0.0-38-generic '* ]]
done
cmp /var/lib/cmp170-unlock/maintenance-168-20261009/build-hwe7/open-gpu-kernel-modules-615.71.09/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c \
    "$base/build/open-gpu-kernel-modules-615.71.09/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c"
exec 8>/run/cmp170-driver-install.lock
flock -n 8
install -d -m 0700 "$backup"
cp -a "$target" "$backup/modules"
cp -a /boot/initrd.img-7.0.0-38-generic "$backup/initrd.img"
cp -a /usr/local/sbin/cmp170-gen2-second-pass "$backup/gen2-helper"
cp -a /etc/modprobe.d/asm-nvidia-no-nouveau.conf "$backup/nouveau.conf"
cp /proc/sys/kernel/random/boot_id "$backup/boot-id"
sha256sum "$backup/modules/"*.ko "$backup/initrd.img" > "$backup/original.sha256"
rollback() {
    rc=$?
    if ((rc != 0)); then
        for name in nvidia nvidia-drm nvidia-modeset nvidia-peermem nvidia-uvm; do
            install -m 0644 "$backup/modules/$name.ko" "$target/$name.ko"
        done
        depmod -a 7.0.0-38-generic || true
        cp -a "$backup/initrd.img" /boot/initrd.img-7.0.0-38-generic
        echo 'Installation failed; previous modules/initramfs restored; no reboot issued' >&2
    fi
    exit "$rc"
}
trap rollback EXIT
for name in nvidia nvidia-drm nvidia-modeset nvidia-peermem nvidia-uvm; do
    install -m 0644 "$base/modules/$name.ko" "$target/$name.ko"
done
depmod -a 7.0.0-38-generic
[[ $(modinfo -F filename nvidia) == "$target/nvidia.ko" ]]
for name in nvidia nvidia-drm nvidia-modeset nvidia-peermem nvidia-uvm; do
    [[ $(sha256sum "$target/$name.ko" | cut -d' ' -f1) == "${sums[$name]}" ]]
done
update-initramfs -u -k 7.0.0-38-generic
lsinitramfs /boot/initrd.img-7.0.0-38-generic > "$base/initramfs-files.txt"
grep -Fxq etc/modprobe.d/asm-nvidia-no-nouveau.conf "$base/initramfs-files.txt"
if grep -Fxq etc/modprobe.d/cmp-pcie-gen2.conf "$base/initramfs-files.txt"; then
    echo 'Old global options still embedded in initramfs' >&2; exit 1
fi
systemctl reset-failed cmp170-gen2-second-pass.service
systemctl start cmp170-gen2-second-pass.service
[[ $(systemctl show cmp170-gen2-second-pass.service -p Result --value) == success ]]
sha256sum "$target/"*.ko /boot/initrd.img-7.0.0-38-generic > "$base/installed.sha256"
echo "INSTALLED_FOR_NEXT_BOOT: 615.71.09; CMP-only options; backup=$backup; live driver not reloaded"
