#!/usr/bin/env bash
set -Eeuo pipefail
# Status is read-only. --test explicitly runs CUDA peer kernels on idle GPUs.
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=vendor/cmpunlocker/common/p2p.sh
source "$repo_dir/vendor/cmpunlocker/common/p2p.sh"
# shellcheck source=scripts/inventory.sh
source "$repo_dir/scripts/inventory.sh"
die() { echo "P2P: $*" >&2; exit 1; }
mode=${1:---status}
case $mode in
    --help|-h)
        echo 'Usage: bash scripts/check-p2p.sh [--status | --test [CUDA_GPU_ID ...]]'
        echo '--status: module identity, active options, BAR1 and diagnostic capability matrices.'
        echo '--test: additionally compile/run real peer reads and writes; idle CMP-only host, nvcc and timeout required.'
        exit 0 ;;
    --status|--test) [[ $# -eq 0 ]] || shift ;;
    *) die 'unknown mode; use --help' ;;
esac
[[ $mode != --status || $# == 0 ]] || die '--status takes no GPU indices'
for tool in modinfo nvidia-smi python3; do
    command -v "$tool" >/dev/null || die "$tool is required"
done
metadata=/lib/modules/$(uname -r)/updates/cmpunlocker
[[ -r $metadata/p2p_enabled && $(<"$metadata/p2p_enabled") == 1 ]] || die 'on-disk driver is not P2P-enabled; install with --p2p first'
[[ -r /sys/module/nvidia/srcversion ]] || die 'NVIDIA module is not loaded'
installed=$(modinfo -F srcversion "$metadata/nvidia.ko")
running=$(< /sys/module/nvidia/srcversion)
[[ -n $installed && $installed == "$running" ]] || die 'running module differs from installed P2P module; cold boot first'
[[ -r /proc/driver/nvidia/params ]] || die 'active NVIDIA parameters unavailable'
grep -Eq '^[[:space:]]*RegistryDwords:.*RMForceStaticBar1=1([;"[:space:]]|$)' /proc/driver/nvidia/params || die 'static BAR1 option is not active'
grep -Eq '^[[:space:]]*RegistryDwords:.*RMPcieP2PType=1([;"[:space:]]|$)' /proc/driver/nvidia/params || die 'BAR1 P2P option is not active'
mapfile -t cards < <(cmp170_gpu_list)
[[ ${#cards[@]} -ge 2 ]] || die 'at least two CMP cards must be visible'
python3 - "${cards[@]}" <<'PY'
from pathlib import Path
import sys
for bdf in sys.argv[1:]:
    gpu = Path('/sys/bus/pci/devices') / bdf
    device = gpu.joinpath('device').read_text().strip()
    start, end, _ = [int(value, 16) for value in gpu.joinpath('resource').read_text().splitlines()[1].split()]
    size = end - start + 1 if start and end >= start else 0
    required = (64 if device == '0x20c2' else 40) << 30
    print(f'{bdf}: BAR1={size / (1 << 30):.2f} GiB; required >= {required >> 30} GiB')
    if size < required:
        sys.exit('P2P: BAR1 does not cover framebuffer; check firmware MMIO/Above-4G configuration')
PY
nvidia-smi --query-gpu=pci.bus_id,memory.total,pcie.link.gen.current,pcie.link.width.current --format=csv
echo 'Capability matrices are diagnostic only: overrides can report OK even when transfers fail.'
nvidia-smi topo -p2p r
nvidia-smi topo -p2p w
if [[ $mode == --test ]]; then
    cmp_p2p_check_host || die 'test host preflight failed'
    for tool in nvcc timeout fuser flock; do
        command -v "$tool" >/dev/null || die "$tool is required for real peer tests"
    done
    [[ $EUID == 0 ]] || die 'run --test as root so the busy-device check can inspect other users'
    exec 9>/run/cmp170-gen2-second-pass.lock
    flock -n 9 || die 'Gen2 activation is in progress'
    exec 8>/run/cmp170-driver-install.lock
    flock -n 8 || die 'driver installation is in progress'
    cmp_p2p_require_idle || die 'GPU-client preflight failed'
    task_tmp=$(mktemp -d /tmp/cmp170-p2p-test.XXXXXXXX)
    trap 'rm -f "$task_tmp/test-p2p"; rmdir "$task_tmp"' EXIT
    nvcc -O2 -arch=sm_80 -o "$task_tmp/test-p2p" "$repo_dir/vendor/cmpunlocker/tools/test-p2p.cu"
    timeout -k 5 120 "$task_tmp/test-p2p" "$@"
    echo 'PASS: actual peer reads and writes passed; this is not a throughput or sustained stability benchmark.'
else
    echo 'Status checks passed, but data transfer is NOT verified. Run --test during a maintenance window.'
fi
