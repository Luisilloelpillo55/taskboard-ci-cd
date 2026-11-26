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
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 curl

systemctl enable --now docker
docker compose version

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
if ! grep -qx 'COOKIE_SECURE=true' /etc/taskboard/taskboard.env; then
    echo "Set COOKIE_SECURE=true in /etc/taskboard/taskboard.env before deploying." >&2
    exit 1
fi

image="${TASKBOARD_IMAGE:-ghcr.io/luisilloelpillo55/taskboard-ci-cd:latest}"
if [[ ! "${image}" =~ ^ghcr\.io/luisilloelpillo55/taskboard-ci-cd:(latest|sha-[0-9a-f]{40})$ ]]; then
    echo "TASKBOARD_IMAGE must be the public Taskboard GHCR image with a supported tag." >&2
    exit 1
fi

chown -R taskboard:taskboard /opt/taskboard
cat > /opt/taskboard/.env <<EOF
TASKBOARD_APP_ENV_FILE=/etc/taskboard/taskboard.env
TASKBOARD_DATA_DIR=/var/lib/taskboard
TASKBOARD_UID=$(id -u taskboard)
TASKBOARD_GID=$(id -g taskboard)
TASKBOARD_BIND_ADDRESS=127.0.0.1
TASKBOARD_IMAGE=${image}
EOF
chown root:root /opt/taskboard/.env
chmod 0600 /opt/taskboard/.env

compose=(docker compose --project-directory /opt/taskboard -f /opt/taskboard/deploy/compose.yaml)
"${compose[@]}" pull taskboard
if systemctl list-unit-files taskboard.service --no-legend | grep -q '^taskboard.service'; then
    systemctl disable --now taskboard.service
fi
"${compose[@]}" up -d --force-recreate taskboard
for attempt in {1..15}; do
    if curl --fail --silent http://127.0.0.1:8000/api/health; then
        printf '\nTaskboard container is healthy on localhost:8000.\n'
        "${compose[@]}" ps taskboard
        exit 0
    fi
    sleep 2
done

"${compose[@]}" ps taskboard
"${compose[@]}" logs --no-color --tail=80 taskboard >&2
echo "Taskboard did not become healthy; inspect the container logs." >&2
exit 1
