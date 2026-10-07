#!/usr/bin/env bash
# Read-only helpers. The optional sysfs argument is for isolated fixture tests.
cmp170_gpu_list() {
    local root=${1:-/sys/bus/pci/devices} path
    for path in "$root"/*; do
        [[ -r $path/vendor && -r $path/device ]] || continue
        [[ $(<"$path/vendor") == 0x10de ]] || continue
        case $(<"$path/device") in
            0x20c2|0x2082) printf '%s\n' "${path##*/}" ;;
        esac
    done
}

cmp170_gpu_count() {
    local -a cards=()
    mapfile -t cards < <(cmp170_gpu_list "${1:-/sys/bus/pci/devices}")
    printf '%s\n' "${#cards[@]}"
}

cmp170_check_expected() {
    local expected=$1 actual=$2
    [[ $expected =~ ^[1-9][0-9]*$ && $actual =~ ^[1-9][0-9]*$ ]] || {
        echo 'No supported CMP 170HX detected or invalid expected GPU count' >&2
        return 1
    }
    [[ $expected == "$actual" ]] || {
        echo "Detected $actual CMP 170HX, expected $expected. Nothing changed; correct the count or check PCIe enumeration." >&2
        return 1
    }
}
