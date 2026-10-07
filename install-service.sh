#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
[[ $# -le 1 && ( ${1:-auto} == auto || ${1:-auto} =~ ^[1-9][0-9]*$ ) ]] || {
    echo 'Usage: sudo ./install-service.sh [EXPECTED_GPU_COUNT|auto]' >&2
    exit 1
}
repo_dir=$(cd "$(dirname "$0")" && pwd)
source "$repo_dir/scripts/inventory.sh"
actual_count=$(cmp170_gpu_count)
requested_count=${1:-auto}
expected_count=$requested_count
[[ $expected_count != auto ]] || expected_count=$actual_count
# Fail before touching an existing service/configuration when the count is stale.
cmp170_check_expected "$expected_count" "$actual_count"
command -v flock >/dev/null || { echo 'flock (util-linux) is required' >&2; exit 1; }
exec 9>/run/cmp170-gen2-second-pass.lock
flock -n 9 || { echo 'Gen2 activation is in progress; refusing to change its configuration' >&2; exit 1; }
backup_dir=/var/lib/cmp170-unlock/backups/$(date -u +%Y%m%dT%H%M%SZ)

bash -n "$repo_dir/scripts/gen2-second-pass.sh"
[[ -f $repo_dir/systemd/cmp170-gen2-second-pass.service ]] || exit 1

mkdir -p "$backup_dir"
for path in /etc/cmp170-unlock.conf \
            /etc/systemd/system/cmp170-gen2-second-pass.service \
            /usr/local/sbin/cmp170-gen2-second-pass; do
    [[ ! -e $path ]] || cp -a "$path" "$backup_dir/"
done
systemctl disable --now gen2.service 2>/dev/null || true
systemctl reset-failed gen2.service 2>/dev/null || true
for path in /etc/systemd/system/gen2.service \
            /etc/systemd/system/gen2.service.d \
            /usr/local/sbin/gen2-hammer; do
    if [[ -e $path ]]; then
        mv "$path" "$backup_dir/"
    fi
done

install -m 0755 "$repo_dir/scripts/gen2-second-pass.sh" \
    /usr/local/sbin/cmp170-gen2-second-pass
install -m 0644 "$repo_dir/systemd/cmp170-gen2-second-pass.service" \
    /etc/systemd/system/cmp170-gen2-second-pass.service
printf 'CMP170_EXPECTED_GPUS=%s\n' "$requested_count" > /etc/cmp170-unlock.conf
chmod 0644 /etc/cmp170-unlock.conf

systemctl daemon-reload
systemctl enable cmp170-gen2-second-pass.service
systemctl reset-failed cmp170-gen2-second-pass.service 2>/dev/null || true
echo "Installed cmp170-gen2-second-pass.service with inventory mode $requested_count; currently detected $actual_count GPU(s)."
echo "Previous service/config files saved under $backup_dir. Activation was not started; reboot during maintenance to verify."
