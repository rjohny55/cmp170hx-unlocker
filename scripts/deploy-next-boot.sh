#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 && $# -eq 1 ]] || { echo 'Usage: sudo scripts/deploy-next-boot.sh STAGE_DIR' >&2; exit 1; }
stage=$(readlink -f "$1")
[[ $stage == /var/lib/cmp170-unlock/stage-17535a0.* && -f $stage/status ]] || { echo 'Invalid staging directory' >&2; exit 1; }
[[ $(<"$stage/status") == verified ]] || { echo 'Staged build has not passed verification' >&2; exit 1; }
kernel=$(uname -r)
version=$(modinfo -F version nvidia)
[[ $(<"$stage/kernel-version") == "$kernel" && $(<"$stage/driver-version") == "$version" ]] || {
    echo 'Kernel/driver changed since staging; rebuild before deployment' >&2; exit 1;
}
command -v update-initramfs >/dev/null || { echo 'This safe deployment requires update-initramfs' >&2; exit 1; }
exec 8>/run/cmp170-driver-install.lock
flock -n 8 || { echo 'Another driver build/install is running' >&2; exit 1; }
exec 9>/run/cmp170-gen2-second-pass.lock
flock -n 9 || { echo 'Gen2 activation is in progress' >&2; exit 1; }
sha256sum -c "$stage/modules.sha256"
target="/lib/modules/$kernel/updates/cmpunlocker"
[[ -d $target && -f $target/nvidia.ko ]] || { echo 'Existing patched driver is required for backup/rollback' >&2; exit 1; }
backup=$(mktemp -d /var/lib/cmp170-unlock/backups/driver-before-17535a0.XXXXXX)
cp -a "$target" "$backup/modules"
initramfs="/boot/initrd.img-$kernel"
[[ -f $initramfs ]] || { echo 'Existing initramfs is required for rollback' >&2; exit 1; }
cp -a "$initramfs" "$backup/initrd.img"
changed=0
rollback() {
    rc=$?
    trap - EXIT
    if (( rc != 0 && changed == 1 )); then
        cp -a "$backup/modules/." "$target/"
        cp -a "$backup/initrd.img" "$initramfs"
        depmod -a "$kernel" || true
        echo "Deployment failed; previous modules/initramfs restored from $backup" >&2
    fi
    exit "$rc"
}
trap rollback EXIT
changed=1
for module in nvidia nvidia-uvm nvidia-modeset nvidia-drm nvidia-peermem; do
    file="$stage/modules/$module.ko"
    [[ $(modinfo -F version "$file") == "$version" && $(modinfo -F vermagic "$file") == "$kernel "* ]] || exit 1
    install -m 0644 "$file" "$target/$module.ko"
done
depmod -a "$kernel"
update-initramfs -u -k "$kernel"
printf 'installed-next-boot\n' > "$stage/status"
echo "New driver patches installed for NEXT BOOT. Running GPU driver was not reloaded. BACKUP=$backup"
