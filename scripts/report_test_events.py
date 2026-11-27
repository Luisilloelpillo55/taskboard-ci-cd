#!/usr/bin/env python3
"""Send per-test backend and API load-test results to OpenObserve."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


MAX_OUTPUT_LENGTH = 8000
ALLOWED_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
SENSITIVE_VALUE = re.compile(
    r"((?:authorization|password|passwd|token|secret|api[_-]?key|cookie)\s*[:=]\s*)"
    r'(?:"[^"]*"|\'[^\']*\'|(?:Basic|Bearer)\s+[A-Za-z0-9._~+/-]+=*|[^\s,;]+)',
    re.IGNORECASE,
)
AUTH_HEADER = re.compile(r"\b(Basic|Bearer)\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)


def redact_output(value: str) -> str:
    value = SENSITIVE_VALUE.sub(r"\1[REDACTED]", value)
    return AUTH_HEADER.sub(r"\1 [REDACTED]", value)


def truncate_output(value: str) -> tuple[str, bool]:
    redacted = redact_output(value)
    return redacted[:MAX_OUTPUT_LENGTH], len(redacted) > MAX_OUTPUT_LENGTH


def _failure_nodes(test_case: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        child
        for child in test_case
        if child.tag in {"failure", "error", "skipped"}
    ]


def _test_status(test_case: ElementTree.Element) -> str:
    for node in _failure_nodes(test_case):
        if node.tag == "failure":
            return "failed"
        if node.tag == "error":
            return "error"
        if node.tag == "skipped":
            return "skipped"
    return "passed"


def _format_test_output(test_case: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in _failure_nodes(test_case):
        message = node.get("message", "").strip()
        details = (node.text or "").strip()
        if message:
            parts.append(message)
        if details and details != message:
            parts.append(details)
    for tag in ("system-out", "system-err"):
        output = test_case.findtext(tag, default="").strip()
        if output:
            parts.append(f"{tag}:\n{output}")
    return "\n\n".join(parts)


def _failure_reason(test_case: ElementTree.Element, status: str) -> str:
    nodes = _failure_nodes(test_case)
    if nodes:
        message = nodes[0].get("message", "").strip()
        details = (nodes[0].text or "").strip()
        return message or details.splitlines()[0] if details else message
    if status == "passed":
        return ""
    return "Test did not complete successfully."


def build_pytest_events(
    junit_xml: str,
    metadata: dict[str, str],
    *,
    event_time: str | None = None,
) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(junit_xml)
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("The JUnit report contains no test cases.")

    timestamp = event_time or datetime.now(timezone.utc).isoformat()
    events: list[dict[str, Any]] = []
    for case in cases:
        result = _test_status(case)
        output, output_truncated = truncate_output(_format_test_output(case))
        reason = redact_output(_failure_reason(case, result))[:1000]
        failure_node = next(
            (node for node in _failure_nodes(case) if node.tag in {"failure", "error"}),
            None,
        )
        try:
            duration_ms = round(float(case.get("time", "0")) * 1000, 3)
        except ValueError:
            duration_ms = 0

        suite = case.get("classname", "")
        name = case.get("name", "unnamed test")
        level = "info" if result == "passed" else "warn" if result == "skipped" else "error"
        events.append(
            {
                "event_time": timestamp,
                "event_type": "backend_test",
                "level": level,
                "result": result,
                "component": "backend",
                "test_name": name,
                "test_suite": suite,
                "test_file": case.get("file", ""),
                "test_line": int(case.get("line", "0") or "0"),
                "duration_ms": duration_ms,
                "error_type": failure_node.get("type", "") if failure_node is not None else "",
                "failure_reason": reason,
                "test_output": output,
                "output_truncated": output_truncated,
                "commit": metadata.get("CI_COMMIT_SHA", ""),
                "branch": metadata.get("CI_BRANCH", ""),
                "actor": metadata.get("CI_ACTOR", ""),
                "repository": metadata.get("CI_REPOSITORY", ""),
                "run_id": metadata.get("CI_RUN_ID", ""),
                "run_attempt": metadata.get("CI_RUN_ATTEMPT", ""),
                "run_url": metadata.get("CI_RUN_URL", ""),
                "service": "taskboard",
                "log": f"Pytest {result}: {suite}::{name}",
            }
        )
    return events


def build_load_test_event(
    report: dict[str, Any],
    metadata: dict[str, str],
    *,
    event_time: str | None = None,
) -> dict[str, Any]:
    result = report.get("status", "unknown")
    failures = report.get("failures", [])
    reason = report.get("failure_reason", "")
    if not reason and failures:
        reason = "; ".join(
            str(failure.get("failure_reason", failure.get("error_type", "request failed")))
            for failure in failures[:5]
        )
    output, output_truncated = truncate_output(
        json.dumps(report, ensure_ascii=False, sort_keys=True)
    )
    timestamp = event_time or report.get("event_time") or datetime.now(timezone.utc).isoformat()
    return {
        "event_time": timestamp,
        "event_type": "api_load_test",
        "level": "info" if result == "passed" else "error",
        "result": result,
        "component": "load_test",
        "test_name": "API concurrent read/write load test",
        "test_file": "scripts/load_test_api.py",
        "failure_reason": redact_output(str(reason))[:1000],
        "test_output": output,
        "output_truncated": output_truncated,
        "concurrency": report.get("concurrency", 0),
        "requests_per_worker": report.get("requests_per_worker", 0),
        "request_count": report.get("request_count", 0),
        "successful_requests": report.get("successful_requests", 0),
        "failed_requests": report.get("failed_requests", 0),
        "http_5xx": report.get("http_5xx", 0),
        "p95_ms": report.get("p95_ms", 0),
        "p95_limit_ms": report.get("p95_limit_ms", 0),
        "max_ms": report.get("max_ms", 0),
        "requests_per_second": report.get("requests_per_second", 0),
        "commit": metadata.get("CI_COMMIT_SHA", ""),
        "branch": metadata.get("CI_BRANCH", ""),
        "actor": metadata.get("CI_ACTOR", ""),
        "repository": metadata.get("CI_REPOSITORY", ""),
        "run_id": metadata.get("CI_RUN_ID", ""),
        "run_attempt": metadata.get("CI_RUN_ATTEMPT", ""),
        "run_url": metadata.get("CI_RUN_URL", ""),
        "service": "taskboard",
        "log": f"API load test {result}: {report.get('request_count', 0)} requests",
    }


def validate_environment(metadata: dict[str, str]) -> str:
    required = (
        "OPENOBSERVE_URL",
        "OPENOBSERVE_ORG",
        "OPENOBSERVE_STREAM",
        "OPENOBSERVE_AUTHORIZATION",
        "CI_COMMIT_SHA",
        "CI_BRANCH",
        "CI_ACTOR",
        "CI_REPOSITORY",
        "CI_RUN_ID",
        "CI_RUN_ATTEMPT",
        "CI_RUN_URL",
    )
    missing = [key for key in required if not metadata.get(key)]
    if missing:
        raise ValueError(f"Required environment variables are missing: {', '.join(missing)}")

    parsed = urlparse(metadata["OPENOBSERVE_URL"])
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("OPENOBSERVE_URL must be an HTTPS base URL without a path.")
    if not ALLOWED_NAME.fullmatch(metadata["OPENOBSERVE_ORG"]):
        raise ValueError("OPENOBSERVE_ORG contains unsupported characters.")
    if not ALLOWED_NAME.fullmatch(metadata["OPENOBSERVE_STREAM"]):
        raise ValueError("OPENOBSERVE_STREAM contains unsupported characters.")
    if not re.fullmatch(r"Basic\s+[A-Za-z0-9+/=]+", metadata["OPENOBSERVE_AUTHORIZATION"]):
        raise ValueError("OPENOBSERVE_AUTHORIZATION must be a Basic authorization value.")
    return metadata["OPENOBSERVE_URL"].rstrip("/")


def send_events(events: list[dict[str, Any]], metadata: dict[str, str]) -> None:
    base_url = validate_environment(metadata)
    endpoint = (
        f"{base_url}/api/{metadata['OPENOBSERVE_ORG']}/"
        f"{metadata['OPENOBSERVE_STREAM']}/_json"
    )
    for offset in range(0, len(events), 50):
        batch = events[offset : offset + 50]
        request = Request(
            endpoint,
            data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": metadata["OPENOBSERVE_AUTHORIZATION"],
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(
                        f"OpenObserve returned HTTP {response.status}."
                    )
        except HTTPError as exc:
            raise RuntimeError(f"OpenObserve returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise RuntimeError(f"OpenObserve request failed: {exc.reason}.") from exc


def build_events(
    junit_path: Path,
    load_path: Path,
    metadata: dict[str, str],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if junit_path.is_file():
        events.extend(build_pytest_events(junit_path.read_text(encoding="utf-8"), metadata))
    else:
        print(f"JUnit report not found at {junit_path}; backend test events omitted.")

    if load_path.is_file():
        report = json.loads(load_path.read_text(encoding="utf-8"))
        events.append(build_load_test_event(report, metadata))
    else:
        print(f"API load-test report not found at {load_path}; load event omitted.")
    return events


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--load", type=Path, required=True)
    args = parser.parse_args()

    events = build_events(args.junit, args.load, dict(os.environ))
    if not events:
        print("No API test events were available to send.")
        return 0
    send_events(events, dict(os.environ))
    print(f"Sent {len(events)} backend and API load-test events to OpenObserve.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, ElementTree.ParseError) as exc:
        print(f"Could not send API test results: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
