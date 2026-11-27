#!/usr/bin/env python3
"""Run bounded concurrent API checks against an isolated local Taskboard server."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from uuid import uuid4

import httpx


DEFAULT_CONCURRENCY = 20
DEFAULT_REQUESTS_PER_WORKER = 50
DEFAULT_P95_LIMIT_MS = 2000.0
MAX_CONCURRENCY = 100
MAX_REQUESTS = 10000
OPERATIONS = ("health", "current_user", "list_tasks", "create_task")


def choose_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _server_log_text(log_file: Any) -> str:
    log_file.flush()
    log_file.seek(0)
    return log_file.read()[-4000:]


def wait_for_server(process: subprocess.Popen[Any], port: int, log_file: Any) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            details = _server_log_text(log_file)
            raise RuntimeError(
                f"Local API server exited with code {process.returncode}. {details}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(
        f"Local API server did not start within 30 seconds. {_server_log_text(log_file)}"
    )


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3)


async def execute_load(
    base_url: str,
    concurrency: int,
    requests_per_worker: int,
) -> dict[str, Any]:
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    timeout = httpx.Timeout(10.0)
    request_latencies: list[float] = []
    failures: list[dict[str, str]] = []
    endpoint_counts = {operation: 0 for operation in OPERATIONS}
    endpoint_failures = {operation: 0 for operation in OPERATIONS}
    successful_requests = 0
    started_at = time.perf_counter()
    expected_task_creates = sum(
        1
        for worker in range(concurrency)
        for request_index in range(requests_per_worker)
        if (worker * requests_per_worker + request_index) % len(OPERATIONS) == 3
    )

    async with httpx.AsyncClient(
        base_url=base_url,
        limits=limits,
        timeout=timeout,
        trust_env=False,
    ) as client:
        registration = await client.post(
            "/api/auth/register",
            json={
                "email": f"load-{uuid4()}@example.com",
                "password": secrets.token_urlsafe(24),
            },
        )
        if registration.status_code != 201:
            return {
                "event_time": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "failure_reason": (
                    "Could not create an isolated load-test account "
                    f"(HTTP {registration.status_code})."
                ),
                "concurrency": concurrency,
                "requests_per_worker": requests_per_worker,
                "request_count": 0,
                "successful_requests": 0,
                "failed_requests": 1,
                "http_5xx": int(registration.status_code >= 500),
                "p95_ms": 0,
                "requests_per_second": 0,
                "failures": [],
                "endpoint_counts": endpoint_counts,
            }

        initial_task = await client.post(
            "/api/tasks",
            json={"title": "Load-test baseline task"},
        )
        if initial_task.status_code != 201:
            return {
                "event_time": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "failure_reason": (
                    "Could not create the load-test baseline task "
                    f"(HTTP {initial_task.status_code})."
                ),
                "concurrency": concurrency,
                "requests_per_worker": requests_per_worker,
                "request_count": 0,
                "successful_requests": 0,
                "failed_requests": 1,
                "http_5xx": int(initial_task.status_code >= 500),
                "p95_ms": 0,
                "requests_per_second": 0,
                "failures": [],
                "endpoint_counts": endpoint_counts,
            }

        async def worker(worker_index: int) -> list[float]:
            nonlocal successful_requests
            latencies: list[float] = []
            for request_index in range(requests_per_worker):
                operation = OPERATIONS[
                    (worker_index * requests_per_worker + request_index)
                    % len(OPERATIONS)
                ]
                endpoint_counts[operation] += 1
                method = "POST" if operation == "create_task" else "GET"
                path = {
                    "health": "/api/health",
                    "current_user": "/api/auth/me",
                    "list_tasks": "/api/tasks",
                    "create_task": "/api/tasks",
                }[operation]
                payload = (
                    {
                        "title": f"load-{worker_index}-{request_index}",
                        "description": "isolated concurrent API test",
                    }
                    if operation == "create_task"
                    else None
                )
                request_started = time.perf_counter()
                try:
                    response = await client.request(method, path, json=payload)
                except httpx.HTTPError as exc:
                    endpoint_failures[operation] += 1
                    failures.append(
                        {
                            "endpoint": path,
                            "error_type": type(exc).__name__,
                            "failure_reason": str(exc)[:300],
                        }
                    )
                    continue

                latency_ms = (time.perf_counter() - request_started) * 1000
                latencies.append(latency_ms)
                if response.status_code != (
                    201 if operation == "create_task" else 200
                ):
                    endpoint_failures[operation] += 1
                    try:
                        reason = response.json().get("detail", "")
                    except (ValueError, AttributeError):
                        reason = response.text[:300]
                    failures.append(
                        {
                            "endpoint": path,
                            "error_type": "HTTPStatusError",
                            "status_code": str(response.status_code),
                            "failure_reason": str(reason)[:300],
                        }
                    )
                else:
                    successful_requests += 1
            return latencies

        worker_latencies = await asyncio.gather(
            *(worker(index) for index in range(concurrency))
        )
        request_latencies.extend(
            latency for latencies in worker_latencies for latency in latencies
        )

        verification = await client.get("/api/tasks")
        expected_total_tasks = expected_task_creates + 1
        actual_task_count = None
        try:
            tasks = verification.json()
            if isinstance(tasks, list):
                actual_task_count = len(tasks)
        except ValueError:
            pass
        if verification.status_code != 200 or actual_task_count != expected_total_tasks:
            failures.append(
                {
                    "endpoint": "/api/tasks",
                    "error_type": "PersistenceVerificationError",
                    "failure_reason": (
                        "Concurrent task writes were not all persisted "
                        f"(expected {expected_total_tasks}, found "
                        f"{actual_task_count if actual_task_count is not None else 'invalid response'})."
                    ),
                }
            )

    elapsed_seconds = time.perf_counter() - started_at
    request_count = concurrency * requests_per_worker
    failed_requests = request_count - successful_requests
    http_5xx = sum(
        int(failure.get("status_code", "0").isdigit())
        and int(failure.get("status_code", "0")) >= 500
        for failure in failures
    )
    p95_ms = percentile_95(request_latencies)
    failure_reasons = []
    if failed_requests:
        failure_reasons.append(f"{failed_requests} of {request_count} requests failed.")
    if failures and failures[0].get("failure_reason"):
        failure_reasons.append(failures[0]["failure_reason"])
    if p95_ms > DEFAULT_P95_LIMIT_MS:
        failure_reasons.append(
            f"p95 latency {p95_ms:.3f} ms exceeded "
            f"{DEFAULT_P95_LIMIT_MS:.0f} ms."
        )

    return {
        "event_time": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if failure_reasons else "passed",
        "failure_reason": " ".join(failure_reasons),
        "concurrency": concurrency,
        "requests_per_worker": requests_per_worker,
        "request_count": request_count,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "http_5xx": http_5xx,
        "p95_ms": p95_ms,
        "max_ms": round(max(request_latencies, default=0), 3),
        "requests_per_second": round(request_count / elapsed_seconds, 3)
        if elapsed_seconds
        else 0,
        "p95_limit_ms": DEFAULT_P95_LIMIT_MS,
        "endpoint_counts": endpoint_counts,
        "endpoint_failures": endpoint_failures,
        "verification": {
            "expected_task_count": expected_total_tasks,
            "actual_task_count": actual_task_count,
        },
        "failures": failures[:20],
    }


def stop_server(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--requests-per-worker",
        type=int,
        default=DEFAULT_REQUESTS_PER_WORKER,
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("api-load-test.json"),
    )
    args = parser.parse_args()
    if not 1 <= args.concurrency <= MAX_CONCURRENCY:
        parser.error(f"--concurrency must be between 1 and {MAX_CONCURRENCY}.")
    if args.requests_per_worker <= 0:
        parser.error("--requests-per-worker must be greater than zero.")
    if args.concurrency * args.requests_per_worker > MAX_REQUESTS:
        parser.error(f"The total request count cannot exceed {MAX_REQUESTS}.")

    root = Path(__file__).resolve().parents[1]
    port = choose_port()
    report: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="taskboard-load-test-") as temp_dir:
        environment = os.environ.copy()
        environment["TASKS_DB_PATH"] = str(Path(temp_dir) / "load-test.db")
        environment["COOKIE_SECURE"] = "false"
        environment.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        environment.pop("OTEL_EXPORTER_OTLP_HEADERS", None)
        with (Path(temp_dir) / "uvicorn.log").open(
            "w+", encoding="utf-8"
        ) as server_log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=root,
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_for_server(process, port, server_log)
                report = asyncio.run(
                    execute_load(
                        f"http://127.0.0.1:{port}",
                        args.concurrency,
                        args.requests_per_worker,
                    )
                )
            except (RuntimeError, httpx.HTTPError) as exc:
                report = {
                    "event_time": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "failure_reason": str(exc),
                    "concurrency": args.concurrency,
                    "requests_per_worker": args.requests_per_worker,
                    "request_count": 0,
                    "successful_requests": 0,
                    "failed_requests": 1,
                    "http_5xx": 0,
                    "p95_ms": 0,
                    "requests_per_second": 0,
                    "failures": [],
                }
            finally:
                stop_server(process)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "API load test "
        f"{report['status']}: {report['successful_requests']}/"
        f"{report['request_count']} requests passed; "
        f"concurrency={report['concurrency']}; "
        f"p95={report['p95_ms']} ms; "
        f"report={args.report}"
    )
    if report["failure_reason"]:
        print(f"Failure reason: {report['failure_reason']}", file=sys.stderr)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
