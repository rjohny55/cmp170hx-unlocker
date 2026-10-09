#!/usr/bin/env bash
set -Eeuo pipefail
# The vendored driver changes and our bounded boot activation are independent.
repo_dir=$(cd "$(dirname "$0")" && pwd)
source "$repo_dir/scripts/inventory.sh"
source "$repo_dir/vendor/cmpunlocker/common/p2p.sh"
enable_p2p=0
enable_hbm=0
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo 'Usage: sudo bash install-driver.sh [EXPECTED_GPU_COUNT|auto] [--profile=8gb|10gb] [--p2p|--no-p2p] [--hbm-control|--no-hbm-control]'
    echo '--p2p: experimental BAR1 P2P; cold boot and real transfer tests required. Default: disabled.'
    echo '--hbm-control: experimental HBM register access only; no clock, refresh or idle-service changes. Default: disabled.'
    exit 0
fi
expected=${1:-auto}
requested_count=$expected
[[ $# -eq 0 ]] || shift
[[ $expected == auto || $expected =~ ^[1-9][0-9]*$ ]] || {
    echo 'Usage: sudo ./install-driver.sh [EXPECTED_GPU_COUNT|auto] [--profile=8gb|10gb] [--p2p|--no-p2p] [--hbm-control|--no-hbm-control]' >&2
    exit 1
}
for option in "$@"; do
    case $option in
        --profile=8gb|--profile=10gb) ;;
        --p2p) enable_p2p=1 ;;
        --no-p2p) enable_p2p=0 ;;
        --hbm-control) enable_hbm=1 ;;
        --no-hbm-control) enable_hbm=0 ;;
        *) echo "Unsupported option: $option" >&2; exit 1 ;;
    esac
done
[[ $EUID -eq 0 ]] || { echo 'Run as root, during a GPU maintenance window' >&2; exit 1; }
actual=$(cmp170_gpu_count)
[[ $expected != auto ]] || expected=$actual
cmp170_check_expected "$expected" "$actual"
if [[ $enable_p2p == 1 ]]; then
    cmp_p2p_check_host
    cmp_p2p_check_modprobe_options
    cmp_p2p_require_idle
    echo 'EXPERIMENTAL P2P: no performance or stability guarantee; cold boot and real peer transfers must be verified.'
fi
if [[ $enable_hbm == 1 ]]; then
    cmp_p2p_require_idle
    echo 'EXPERIMENTAL HBM: register permissions only; memory frequency and timing changes require separate per-card validation.'
fi
for tool in fuser modinfo flock; do
    command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done
exec 8>/run/cmp170-driver-install.lock
flock -n 8 || { echo 'Another CMP driver installation is running' >&2; exit 1; }
if fuser /dev/nvidia* >/dev/null 2>&1; then
    echo 'NVIDIA device files are in use; stop GPU clients and monitoring before driver installation' >&2
    exit 1
fi
# Upstream matches the installed userspace driver version, not its newest
# advertised default. Do not silently replace a working 610 stack with 615.
version=$(modinfo -F version nvidia)
grep -Fxq "$version" "$repo_dir/vendor/cmpunlocker/driver/VERSION" || {
    echo "Installed NVIDIA version $version is not supported by this driver snapshot" >&2
    exit 1
}
# No author hammer service, VFIO setup, or GRUB/IOMMU changes on the AI host.
CMPUNLOCKER_ENABLE_P2P="$enable_p2p" \
CMPUNLOCKER_ENABLE_HBM="$enable_hbm" \
    bash "$repo_dir/vendor/cmpunlocker/install.sh" --no-gen2-service --no-iommu --no-passthrough "$@"
bash "$repo_dir/install-service.sh" "$requested_count"
echo 'Driver prepared with upstream patches; our fast second-pass service is preserved. Reboot and verify in a maintenance window.'
