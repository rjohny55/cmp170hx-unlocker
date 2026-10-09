#!/usr/bin/env bash
set -Eeuo pipefail
# Read-only identity check, not a test of register writes or memory integrity.
case ${1:---status} in
    --help|-h)
        echo 'Usage: bash scripts/check-hbm.sh [--status]'
        echo 'Read-only: experimental HBM build metadata and installed/running module identity.'
        exit 0 ;;
    --status) [[ $# -le 1 ]] || { echo 'No additional arguments allowed' >&2; exit 1; } ;;
    *) echo 'Unknown mode; use --help' >&2; exit 1 ;;
esac
die() { echo "HBM: $*" >&2; exit 1; }
command -v modinfo >/dev/null || die 'modinfo is required'
metadata=/lib/modules/$(uname -r)/updates/cmpunlocker
[[ -r $metadata/hbm_control_enabled && $(<"$metadata/hbm_control_enabled") == 1 ]] || die 'on-disk HBM experiment is disabled; no access verified'
[[ -r /sys/module/nvidia/srcversion ]] || die 'NVIDIA module is not loaded'
installed=$(modinfo -F srcversion "$metadata/nvidia.ko")
running=$(< /sys/module/nvidia/srcversion)
[[ -n $installed && $installed == "$running" ]] || die 'running module differs from installed HBM module; cold boot first'
echo 'The running module matches the HBM-enabled build. No memory clocks/timings changed by this checker.'
echo 'Register write access and memory integrity are NOT verified. Use per-card, read-only preflight in a separately reviewed tuning tool before any experiment.'
