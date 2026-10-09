#!/usr/bin/env bash
# Optional P2P changes shared driver paths. Reject mixed NVIDIA GPU hosts.
cmp_p2p_check_host() {
    local root=${1:-/sys/bus/pci/devices} path device count=0
    [[ -d $root ]] || { echo 'P2P: PCI inventory is unavailable' >&2; return 1; }
    for path in "$root"/*; do
        [[ -r $path/vendor && -r $path/device && -r $path/class ]] || continue
        [[ $(<"$path/vendor") == 0x10de ]] || continue
        case $(<"$path/class") in 0x0300*|0x0302*) ;; *) continue ;; esac
        device=$(<"$path/device")
        case $device in
            0x20c2|0x2082) count=$((count + 1)) ;;
            *) echo "P2P: mixed NVIDIA GPU host is not supported (device $device at ${path##*/})" >&2; return 1 ;;
        esac
    done
    [[ $count -ge 2 ]] || { echo 'P2P requires at least two supported CMP GPUs' >&2; return 1; }
}

cmp_p2p_check_modprobe_options() {
    local root=${1:-/etc/modprobe.d} path
    for path in "$root"/*.conf; do
        [[ -r $path && ${path##*/} != cmp-pcie-gen2.conf ]] || continue
        if grep -Eq '^[[:space:]]*options[[:space:]]+nvidia[[:space:]].*NVreg_RegistryDwords[[:space:]]*=' "$path"; then
            echo "P2P: competing NVreg_RegistryDwords in $path; consolidate options before installation" >&2
            return 1
        fi
    done
}

cmp_p2p_require_idle() {
    local status=0
    command -v fuser >/dev/null || { echo 'P2P: fuser is required to check GPU clients' >&2; return 1; }
    fuser /dev/nvidia* >/dev/null 2>&1 || status=$?
    case $status in
        0) echo 'P2P: GPU device files are in use; stop workloads and monitoring' >&2; return 1 ;;
        1) return 0 ;;
        *) echo 'P2P: could not verify that GPU device files are idle' >&2; return 1 ;;
    esac
}
