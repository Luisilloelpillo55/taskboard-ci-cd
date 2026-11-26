#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
if [[ "${repo_dir}" != "/opt/taskboard" ]]; then
    echo "Clone the repository to /opt/taskboard before installing the collector." >&2
    exit 1
fi

env_file="/etc/taskboard/taskboard.env"
if [[ ! -f "${env_file}" ]]; then
    echo "Missing ${env_file}; configure the Taskboard OTLP endpoint first." >&2
    exit 1
fi
if ! grep -Eq '^OTEL_EXPORTER_OTLP_ENDPOINT=.+' "${env_file}"; then
    echo "OTEL_EXPORTER_OTLP_ENDPOINT is missing from ${env_file}." >&2
    exit 1
fi
if ! grep -Eq '^OTEL_EXPORTER_OTLP_HEADERS=.+' "${env_file}"; then
    echo "OTEL_EXPORTER_OTLP_HEADERS is missing from ${env_file}." >&2
    exit 1
fi

headers_line="$(grep -m 1 '^OTEL_EXPORTER_OTLP_HEADERS=' "${env_file}")"
headers_value="${headers_line#*=}"
if [[ "${headers_value}" == \"*\" ]]; then
    headers_value="${headers_value:1:${#headers_value}-2}"
elif [[ "${headers_value}" == \'*\' ]]; then
    headers_value="${headers_value:1:${#headers_value}-2}"
fi

authorization=""
IFS=',' read -r -a configured_headers <<< "${headers_value}"
for header in "${configured_headers[@]}"; do
    if [[ "${header}" == Authorization=* ]]; then
        authorization="${header#Authorization=}"
        break
    fi
done
if [[ ! "${authorization}" =~ ^Basic[[:space:]][A-Za-z0-9+/=]+$ ]]; then
    echo "OTEL_EXPORTER_OTLP_HEADERS must contain a Basic Authorization value." >&2
    exit 1
fi

chmod 0600 "${env_file}"

collector_version="0.166.0"
case "$(dpkg --print-architecture)" in
    amd64)
        collector_arch="amd64"
        expected_sha256="928cb39c115d428c53211818b7e33cd8b26810b8896dc74e0bd13b8d1457c391"
        ;;
    arm64)
        collector_arch="arm64"
        expected_sha256="595e0f99e24d6e161f6fb4a0deea28ac18c4b93c5a4ee482fd3c0f85cbf15582"
        ;;
    *)
        echo "Unsupported Debian architecture: $(dpkg --print-architecture)" >&2
        exit 1
        ;;
esac

archive_name="otelcol-contrib_${collector_version}_linux_${collector_arch}.tar.gz"
release_url="https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${collector_version}/${archive_name}"
archive="$(mktemp "/tmp/${archive_name}.XXXXXX")"
temp_dir="$(mktemp -d /tmp/taskboard-otelcol.XXXXXX)"
trap 'rm -f -- "${archive}"; rm -rf -- "${temp_dir}"' EXIT

curl --fail --silent --show-error --location \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --output "${archive}" "${release_url}"
if ! printf '%s  %s\n' "${expected_sha256}" "${archive}" | sha256sum --check --status; then
    echo "OpenTelemetry Collector archive checksum verification failed." >&2
    exit 1
fi

tar -xzf "${archive}" -C "${temp_dir}" otelcol-contrib
install -o root -g root -m 0755 \
    "${temp_dir}/otelcol-contrib" /usr/local/bin/otelcol-contrib

if ! getent group otelcol >/dev/null 2>&1; then
    groupadd --system otelcol
fi
if ! id otelcol >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin \
        --gid otelcol otelcol
fi

install -d -o root -g otelcol -m 0750 /etc/otelcol-contrib
install -o root -g otelcol -m 0640 \
    "${repo_dir}/deploy/hostmetrics-collector.yaml" \
    /etc/otelcol-contrib/taskboard-hostmetrics.yaml
install -o root -g root -m 0644 \
    "${repo_dir}/deploy/taskboard-hostmetrics.service" \
    /etc/systemd/system/taskboard-hostmetrics.service
umask 0077
printf 'OPENOBSERVE_AUTHORIZATION="%s"\n' "${authorization}" \
    > /etc/taskboard/otelcol.env
chmod 0600 /etc/taskboard/otelcol.env

OTEL_EXPORTER_OTLP_ENDPOINT="https://validation.invalid/api/taskboard" \
OPENOBSERVE_AUTHORIZATION="Basic validation-only" \
    /usr/local/bin/otelcol-contrib validate \
    --config=/etc/otelcol-contrib/taskboard-hostmetrics.yaml

systemctl daemon-reload
systemctl enable taskboard-hostmetrics.service
systemctl restart taskboard-hostmetrics.service
if ! systemctl is-active --quiet taskboard-hostmetrics.service; then
    systemctl --no-pager --full status taskboard-hostmetrics.service
    echo "Host metrics collector did not start; inspect its journal." >&2
    exit 1
fi

echo "Host metrics collector is active. It exports every 60 seconds over HTTPS."
