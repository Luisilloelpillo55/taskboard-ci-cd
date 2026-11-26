#!/usr/bin/env bash
set -Eeuo pipefail

required_variables=(
    OPENOBSERVE_URL
    OPENOBSERVE_ORG
    OPENOBSERVE_STREAM
    OPENOBSERVE_AUTHORIZATION
    CI_EVENT_TYPE
    CI_RESULT
    CI_COMMIT_SHA
    CI_BRANCH
    CI_ACTOR
    CI_REPOSITORY
    CI_RUN_ID
    CI_RUN_ATTEMPT
    CI_RUN_URL
)
for variable in "${required_variables[@]}"; do
    if [[ -z "${!variable:-}" ]]; then
        echo "${variable} is required to send a pipeline event." >&2
        exit 1
    fi
done

if [[ ! "${OPENOBSERVE_URL}" =~ ^https://[^/]+/?$ ]]; then
    echo "OPENOBSERVE_URL must be an HTTPS base URL without a path." >&2
    exit 1
fi
if [[ ! "${OPENOBSERVE_ORG}" =~ ^[A-Za-z0-9._-]+$ ||
      ! "${OPENOBSERVE_STREAM}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "OPENOBSERVE_ORG and OPENOBSERVE_STREAM contain unsupported characters." >&2
    exit 1
fi
if [[ ! "${OPENOBSERVE_AUTHORIZATION}" =~ ^Basic[[:space:]][A-Za-z0-9+/=]+$ ]]; then
    echo "OPENOBSERVE_AUTHORIZATION must contain a Basic authorization value." >&2
    exit 1
fi

event_time="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
payload="$(jq -cn \
    --arg event_time "${event_time}" \
    --arg event_type "${CI_EVENT_TYPE}" \
    --arg result "${CI_RESULT}" \
    --arg test_result "${CI_TEST_RESULT:-}" \
    --arg image_result "${CI_IMAGE_RESULT:-}" \
    --arg commit "${CI_COMMIT_SHA}" \
    --arg branch "${CI_BRANCH}" \
    --arg actor "${CI_ACTOR}" \
    --arg repository "${CI_REPOSITORY}" \
    --arg run_id "${CI_RUN_ID}" \
    --arg run_attempt "${CI_RUN_ATTEMPT}" \
    --arg run_url "${CI_RUN_URL}" \
    '[
      {
        level: (if $result == "success" then "info" elif $result == "skipped" then "warn" else "error" end),
        event_time: $event_time,
        event_type: $event_type,
        result: $result,
        test_result: $test_result,
        image_result: $image_result,
        commit: $commit,
        branch: $branch,
        actor: $actor,
        repository: $repository,
        run_id: $run_id,
        run_attempt: $run_attempt,
        run_url: $run_url,
        service: "taskboard",
        log: "Taskboard CI/CD pipeline event"
      }
    ]')"

endpoint="${OPENOBSERVE_URL%/}/api/${OPENOBSERVE_ORG}/${OPENOBSERVE_STREAM}/_json"
curl --fail-with-body --silent --show-error \
    --connect-timeout 5 --max-time 20 \
    --request POST "${endpoint}" \
    --header "Authorization: ${OPENOBSERVE_AUTHORIZATION}" \
    --header "Content-Type: application/json" \
    --data-binary "${payload}"
printf '\nPipeline event sent to OpenObserve stream %s/%s.\n' \
    "${OPENOBSERVE_ORG}" "${OPENOBSERVE_STREAM}"
