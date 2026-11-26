#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
if [[ "${repo_dir}" != "/opt/taskboard" ]]; then
    echo "Clone the repository to /opt/taskboard before deploying." >&2
    exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip curl

if ! id taskboard >/dev/null 2>&1; then
    useradd --system --home-dir /opt/taskboard --shell /usr/sbin/nologin taskboard
fi

install -d -o taskboard -g taskboard -m 0750 /var/lib/taskboard
install -d -m 0750 /etc/taskboard
if [[ ! -f /etc/taskboard/taskboard.env ]]; then
    printf 'COOKIE_SECURE=true\nOTEL_SERVICE_NAME=taskboard\n' \
        > /etc/taskboard/taskboard.env
    chmod 0600 /etc/taskboard/taskboard.env
fi

chown -R taskboard:taskboard /opt/taskboard
runuser -u taskboard -- python3 -m venv /opt/taskboard/.venv
runuser -u taskboard -- /opt/taskboard/.venv/bin/python -m pip install \
    -r /opt/taskboard/requirements.txt

install -m 0644 /opt/taskboard/deploy/taskboard.service \
    /etc/systemd/system/taskboard.service
systemctl daemon-reload
systemctl enable taskboard
systemctl restart taskboard

for attempt in {1..15}; do
    if curl --fail --silent http://127.0.0.1:8000/api/health; then
        printf '\nTaskboard is running on localhost:8000.\n'
        exit 0
    fi
    sleep 2
done

systemctl --no-pager --full status taskboard || true
echo "Taskboard did not become healthy; inspect journalctl -u taskboard." >&2
exit 1
