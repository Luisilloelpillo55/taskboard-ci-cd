#!/usr/bin/env python3
"""Focused tests for CI test-result reporting."""

import unittest

from report_test_events import build_load_test_event, build_pytest_events


METADATA = {
    "CI_COMMIT_SHA": "abc123",
    "CI_BRANCH": "main",
    "CI_ACTOR": "ci-user",
    "CI_REPOSITORY": "owner/repo",
    "CI_RUN_ID": "42",
    "CI_RUN_ATTEMPT": "1",
    "CI_RUN_URL": "https://github.com/owner/repo/actions/runs/42",
}


class ReportTestEventsTests(unittest.TestCase):
    def test_junit_failure_includes_backend_cause_without_input_values(self):
        xml = """\
<testsuites><testsuite name="pytest" tests="2">
  <testcase classname="tests.test_api" name="test_login" file="tests/test_api.py" line="12" time="0.125">
    <failure message="assert 500 == 200" type="AssertionError">Traceback details password=secret-pass</failure>
    <system-err>database is locked</system-err>
  </testcase>
  <testcase classname="tests.test_api" name="test_health" file="tests/test_api.py" line="4" time="0.010"/>
</testsuite></testsuites>
"""

        events = build_pytest_events(
            xml,
            METADATA,
            event_time="2026-01-01T00:00:00+00:00",
        )

        self.assertEqual(len(events), 2)
        failure = events[0]
        self.assertEqual(failure["component"], "backend")
        self.assertEqual(failure["event_type"], "backend_test")
        self.assertEqual(failure["result"], "failed")
        self.assertEqual(failure["failure_reason"], "assert 500 == 200")
        self.assertIn("database is locked", failure["test_output"])
        self.assertNotIn("secret-pass", failure["test_output"])
        self.assertEqual(events[1]["result"], "passed")

    def test_load_test_event_includes_failure_and_performance_metrics(self):
        event = build_load_test_event(
            {
                "event_time": "2026-01-01T00:00:00+00:00",
                "status": "failed",
                "concurrency": 20,
                "requests_per_worker": 50,
                "request_count": 1000,
                "successful_requests": 999,
                "failed_requests": 1,
                "http_5xx": 1,
                "p95_ms": 180.5,
                "p95_limit_ms": 2000,
                "max_ms": 2200,
                "requests_per_second": 250.0,
                "failure_reason": "POST /api/tasks returned HTTP 500",
            },
            METADATA,
        )

        self.assertEqual(event["event_time"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(event["event_type"], "api_load_test")
        self.assertEqual(event["component"], "load_test")
        self.assertEqual(event["result"], "failed")
        self.assertEqual(event["failed_requests"], 1)
        self.assertEqual(event["p95_ms"], 180.5)
        self.assertEqual(event["max_ms"], 2200)
        self.assertIn("HTTP 500", event["failure_reason"])


if __name__ == "__main__":
    unittest.main()
