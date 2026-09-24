#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
[[ $# -eq 1 && "$1" =~ ^[1-9][0-9]*$ ]] || {
    echo 'Usage: sudo ./install-service.sh EXPECTED_GPU_COUNT' >&2
    exit 1
}
expected_count=$1
repo_dir=$(cd "$(dirname "$0")" && pwd)
backup_dir=/var/lib/cmp170-unlock/backups/$(date -u +%Y%m%dT%H%M%SZ)

bash -n "$repo_dir/scripts/gen2-second-pass.sh"
[[ -f $repo_dir/systemd/cmp170-gen2-second-pass.service ]] || exit 1

mkdir -p "$backup_dir"
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
printf 'CMP170_EXPECTED_GPUS=%s\n' "$expected_count" > /etc/cmp170-unlock.conf
chmod 0644 /etc/cmp170-unlock.conf

systemctl daemon-reload
systemctl enable cmp170-gen2-second-pass.service
echo "Installed cmp170-gen2-second-pass.service for $expected_count GPU(s)."
echo "Old gen2.service files saved under $backup_dir. Reboot to verify."
