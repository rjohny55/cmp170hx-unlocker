#!/usr/bin/env bash
# Configuration-only recovery: never reset GPUs, stop containers or reboot.
set -Eeuo pipefail
[[ $EUID == 0 && $(uname -r) == 7.0.0-38-generic ]]
stage=${1:?staging directory required}
[[ $stage == /tmp/asm-driver-168.* && -d $stage ]]
backup=/var/lib/cmp170-unlock/mixed-gpu-168-20261028
[[ ! -e $backup ]] || { echo "Backup already exists: $backup; refusing to overwrite" >&2; exit 1; }
[[ $(modinfo -F version nvidia) == 615.71.09 ]]
[[ $(readlink -f /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1) == */libnvidia-ml.so.615.71.09 ]]
[[ -f $stage/gen2-second-pass.sh && -f $stage/nvidia-no-nouveau.conf ]]
[[ ! -e /etc/modprobe.d/asm-nvidia-no-nouveau.conf ]]
grep -q '^options nvidia NVreg_RegistryDwords=' /etc/modprobe.d/cmp-pcie-gen2.conf
bash -n "$stage/gen2-second-pass.sh"
install -d -m 0700 "$backup"
cp -a /usr/local/sbin/cmp170-gen2-second-pass "$backup/helper"
cp -a /etc/modprobe.d/cmp-pcie-gen2.conf "$backup/cmp-pcie-gen2.conf"
cp -a /boot/initrd.img-7.0.0-38-generic "$backup/initrd.img-7.0.0-38-generic"
sha256sum "$backup/helper" "$backup/cmp-pcie-gen2.conf" "$backup/initrd.img-7.0.0-38-generic" > "$backup/backup.sha256"
rollback() {
    rc=$?
    if ((rc != 0)); then
        cp -a "$backup/helper" /usr/local/sbin/cmp170-gen2-second-pass
        cp -a "$backup/cmp-pcie-gen2.conf" /etc/modprobe.d/cmp-pcie-gen2.conf
        # Only this task's exact new file is removed on failed preparation.
        if [[ -f /etc/modprobe.d/asm-nvidia-no-nouveau.conf ]]; then
            mv /etc/modprobe.d/asm-nvidia-no-nouveau.conf "$backup/failed-nouveau.conf"
        fi
        cp -a "$backup/initrd.img-7.0.0-38-generic" /boot/initrd.img-7.0.0-38-generic
        echo 'Preparation failed; original files and initramfs restored' >&2
    fi
    exit "$rc"
}
trap rollback EXIT
install -m 0755 "$stage/gen2-second-pass.sh" /usr/local/sbin/cmp170-gen2-second-pass
install -m 0644 "$stage/nvidia-no-nouveau.conf" /etc/modprobe.d/asm-nvidia-no-nouveau.conf
# Preserve this CMP-only global option outside modprobe.d, so an RTX card
# cannot inherit forced CMP PCIe link settings. Per-device CMP code remains.
mv /etc/modprobe.d/cmp-pcie-gen2.conf "$backup/disabled-cmp-pcie-gen2.conf"
update-initramfs -u -k 7.0.0-38-generic
lsinitramfs /boot/initrd.img-7.0.0-38-generic > "$backup/initramfs-files.txt"
grep -Fxq etc/modprobe.d/asm-nvidia-no-nouveau.conf "$backup/initramfs-files.txt"
if grep -Fxq etc/modprobe.d/cmp-pcie-gen2.conf "$backup/initramfs-files.txt"; then
    echo 'Old global CMP option remains in initramfs' >&2; exit 1
fi
[[ $(modinfo -F version nvidia) == 615.71.09 ]]
systemctl reset-failed cmp170-gen2-second-pass.service
systemctl start cmp170-gen2-second-pass.service
[[ $(systemctl show cmp170-gen2-second-pass.service -p Result --value) == success ]]
sha256sum /usr/local/sbin/cmp170-gen2-second-pass /etc/modprobe.d/asm-nvidia-no-nouveau.conf /boot/initrd.img-7.0.0-38-generic > "$backup/prepared.sha256"
echo "PREPARED: configuration only; full power cycle required. Backup: $backup"
