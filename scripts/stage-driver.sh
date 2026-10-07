#!/usr/bin/env bash
set -Eeuo pipefail
# Build and verify inactive modules. This script never unloads/reloads a GPU.
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
[[ $EUID -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
source "$repo_dir/scripts/inventory.sh"
count=$(cmp170_gpu_count)
cmp170_check_expected "${1:?Expected GPU count is required}" "$count"
version=$(modinfo -F version nvidia)
kernel=$(uname -r)
grep -Fxq "$version" "$repo_dir/vendor/cmpunlocker/driver/VERSION" || {
    echo "Unsupported installed NVIDIA version: $version" >&2; exit 1;
}
[[ -d /lib/modules/$kernel/build ]] || { echo 'Matching kernel headers are required' >&2; exit 1; }
exec 8>/run/cmp170-driver-install.lock
flock -n 8 || { echo 'Another driver build/install is running' >&2; exit 1; }
stage=$(mktemp -d /var/lib/cmp170-unlock/stage-17535a0.XXXXXX)
chmod 0755 "$stage"
echo "STAGE=$stage"
env CMPUNLOCKER_DRIVER_VERSION="$version" CMPUNLOCKER_CARD_PROFILE=mixed \
    CMPUNLOCKER_BUILD_DIR="$stage/build" CMPUNLOCKER_STAGE_DIR="$stage/modules" \
    CMPUNLOCKER_MAX_JOBS="${CMPUNLOCKER_MAX_JOBS:-16}" \
    bash "$repo_dir/vendor/cmpunlocker/driver/build.sh"
for module in nvidia nvidia-uvm nvidia-modeset nvidia-drm nvidia-peermem; do
    file="$stage/modules/$module.ko"
    [[ -s $file ]] || { echo "Missing staged module: $module" >&2; exit 1; }
    [[ $(modinfo -F version "$file") == "$version" ]] || { echo "Wrong module version: $module" >&2; exit 1; }
    [[ $(modinfo -F vermagic "$file") == "$kernel "* ]] || { echo "Wrong module kernel: $module" >&2; exit 1; }
done
sha256sum "$stage/modules/"*.ko > "$stage/modules.sha256"
printf '%s\n' "$version" > "$stage/driver-version"
printf '%s\n' "$kernel" > "$stage/kernel-version"
printf '%s\n' "$count" > "$stage/gpu-count"
printf 'verified\n' > "$stage/status"
echo "Verified inactive modules in $stage; deploy-next-boot.sh applies them with a rollback backup."
