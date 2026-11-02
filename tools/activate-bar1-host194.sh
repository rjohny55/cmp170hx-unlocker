#!/usr/bin/env bash
# Validated G292-Z20 GPU-only switch topology. Never scan a root bus or a NIC.
# Boot keeps the baseline driver; this optional, bounded pass runs after SSH.
set -Eeuo pipefail
[[ $EUID == 0 && $(hostname) == gigabyte && $(uname -r) == 6.8.0-147-generic ]]
task=/var/lib/cmp170-unlock/p2p-host-static-194-20261102
modules=$task/staged
branches=('0000:00:03.1 01 03 04' '0000:40:01.1 41 43 44'
          '0000:80:03.1 86 88 89' '0000:c0:01.1 c1 c3 c4')
exec 8>/run/cmp170-bar1-maintenance.lock
flock -n 8
[[ ! -e /run/cmp170-bar1-p2p-ready ]]
[[ ! -e /run/modprobe.d/cmp170-bar1-maintenance.conf ]]
for p in /sys/bus/pci/devices/*; do
    [[ -r $p/vendor && -r $p/class && -r $p/device ]] || continue
    [[ $(cat "$p/vendor") == 0x10de && $(cat "$p/class") == 0x03* ]] || continue
    [[ $(cat "$p/device") == 0x20c2 ]] || { echo 'Mixed NVIDIA GPU host; refusing'; exit 1; }
done
sha256sum -c "$task/staged.sha256"
for name in nvidia nvidia-uvm; do
    [[ $(modinfo -F version "$modules/$name.ko") == 615.71.09 ]]
    [[ $(modinfo -F vermagic "$modules/$name.ko") == '6.8.0-147-generic '* ]]
done
for branch in "${branches[@]}"; do
    read -r root bus first second <<< "$branch"
    actual=$(readlink -f /sys/bus/pci/devices/$root)
    [[ -e /sys/bus/pci/devices/$root && -w /sys/class/pci_bus/0000:$bus/rescan ]]
    for iface in /sys/class/net/*; do
        [[ ! -e $iface/device ]] || [[ $(readlink -f "$iface/device") != "$actual/"* ]]
    done
    for p in /sys/bus/pci/devices/*; do
        [[ $(readlink -f "$p") == "$actual/"* ]] || continue
        case "$(cat "$p/vendor"):$(cat "$p/device")" in
            0x11f8:0x4052|0x10de:0x20c2) ;;
            *) echo "Refusing non-GPU branch device $p" >&2; exit 1 ;;
        esac
    done
    for gpu in "$first" "$second"; do
        p=/sys/bus/pci/devices/0000:$gpu:00.0
        [[ $(readlink -f "$p") == "$actual/"* && $(cat "$p/device") == 0x20c2 ]]
        cap=$(setpci -s "0000:$gpu:00.0" bb0.l)
        [[ $((16#$cap & 65535)) == 21 ]]
    done
done
apps=$(timeout -k 2s 30s nvidia-smi --query-compute-apps=pid --format=csv,noheader)
[[ -z $apps ]] || { echo 'Active CUDA clients; leaving driver unchanged'; exit 1; }
panel=0; persist=0; touched=0; ready=0; autoload_block_owned=0
power_controls=$(mktemp /run/cmp170-bar1-power.XXXXXX)
finish() {
    rc=$?; trap - EXIT
    if ((autoload_block_owned)); then
        rm /run/modprobe.d/cmp170-bar1-maintenance.conf
    fi
    if ((touched && !ready)); then
        echo 'Activation failed; restoring baseline driver (boot files unchanged)' >&2
        for m in nvidia_drm nvidia_modeset nvidia_uvm nvidia_peermem nvidia; do
            if grep -q "^$m " /proc/modules; then timeout -k 2s 15s modprobe -r "$m" || true; fi
        done
        timeout -k 2s 80s modprobe nvidia || true
        timeout -k 2s 15s modprobe nvidia_uvm || true
    fi
    while read -r p control; do
        [[ ! -w $p/power/control ]] || printf '%s\n' "$control" > "$p/power/control"
    done < "$power_controls"
    rm "$power_controls"
    if ((persist)); then systemctl start --no-block nvidia-persistenced.service || true; fi
    if ((panel)); then timeout -k 2s 30s docker start ai-manager || true; fi
    echo "BAR1_P2P_ACTIVATION_EXIT=$rc ready=$ready"
    exit "$rc"
}
trap finish EXIT
if [[ $(docker inspect -f '{{.State.Running}}' ai-manager 2>/dev/null) == true ]]; then
    panel=1; timeout -k 2s 35s docker stop -t 20 ai-manager
fi
if systemctl is-active --quiet nvidia-persistenced.service; then
    persist=1; timeout -k 2s 12s systemctl stop nvidia-persistenced.service
fi
if fuser /dev/nvidia* >/dev/null 2>&1; then echo 'GPU clients remain; refusing'; exit 1; fi
timeout -k 5s 120s /usr/local/sbin/cmp170-gen2-second-pass auto
[[ ! -e /run/modprobe.d/cmp170-bar1-maintenance.conf ]]
install -d /run/modprobe.d
install -m 0644 /usr/local/share/cmp170-bar1-maintenance.conf /run/modprobe.d/cmp170-bar1-maintenance.conf
autoload_block_owned=1
for branch in "${branches[@]}"; do
    read -r root bus first second <<< "$branch"
    actual=$(readlink -f /sys/bus/pci/devices/$root)
    for p in /sys/bus/pci/devices/*; do
        resolved=$(readlink -f "$p")
        [[ $resolved == "$actual" || $resolved == "$actual/"* ]] || continue
        [[ -w $p/power/control ]] || continue
        printf '%s %s\n' "$p" "$(cat "$p/power/control")" >> "$power_controls"
        printf 'on\n' > "$p/power/control"
    done
done
touched=1
for m in nvidia_drm nvidia_modeset nvidia_uvm nvidia_peermem nvidia; do
    if grep -q "^$m " /proc/modules; then timeout -k 2s 20s modprobe -r "$m"; fi
done
! grep -q '^nvidia ' /proc/modules
for branch in "${branches[@]}"; do
    read -r root bus first second <<< "$branch"
    needs_resize=0
    for gpu in "$first" "$second"; do
        read -r start end flags < <(sed -n '2p' /sys/bus/pci/devices/0000:$gpu:00.0/resource)
        ((end-start+1 == 68719476736)) || needs_resize=1
    done
    ((needs_resize)) || continue
    for gpu in "$first" "$second"; do
        pci=0000:$gpu:00.0
        ctrl=$(setpci -s "$pci" bc0.l)
        [[ $((16#$ctrl & 7)) == 1 ]]
        setpci -s "$pci" COMMAND.w=0000:0006
        setpci -s "$pci" bc0.l=00001000:00003f00
    done
    printf '1\n' > /sys/bus/pci/devices/0000:$bus:00.0/remove
    printf '1\n' > /sys/bus/pci/devices/0000:$bus:00.1/remove
    printf '1\n' > /sys/class/pci_bus/0000:$bus/rescan
    for gpu in "$first" "$second"; do
        read -r start end flags < <(sed -n '2p' /sys/bus/pci/devices/0000:$gpu:00.0/resource)
        [[ $((end-start+1)) == 68719476736 ]]
        echo "0000:$gpu:00.0 BAR1=64GiB"
    done
done
timeout -k 2s 90s insmod "$modules/nvidia.ko"
timeout -k 2s 20s insmod "$modules/nvidia-uvm.ko"
count=$(timeout -k 2s 30s nvidia-smi --query-gpu=name --format=csv,noheader | grep -cx 'NVIDIA CMP 170HX')
[[ $count == 8 ]]
CUDA_DEVICE_ORDER=PCI_BUS_ID timeout -k 5s 90s /home/rjohny/cmp170-forgejo-dff7179-20261102/test-p2p > "$task/last-boot-peer-test.txt" 2>&1
grep -Fx '56/56 directed pairs passed real peer reads and writes.' "$task/last-boot-peer-test.txt"
ready=1
cp /proc/sys/kernel/random/boot_id /run/cmp170-bar1-p2p-ready
echo 'All 8 BAR1 apertures and 56 peer links verified; boot baseline preserved'
