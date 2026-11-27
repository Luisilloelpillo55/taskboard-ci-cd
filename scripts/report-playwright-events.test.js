"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { buildEvents } = require("./report-playwright-events");

test("builds an event per retry attempt with test metadata and captured logs", () => {
  const events = buildEvents(
    {
      suites: [
        {
          file: "e2e/tasks.spec.js",
          specs: [
            {
              title: "creates a task",
              tests: [
                {
                  projectName: "chromium",
                  status: "flaky",
                  results: [
                    {
                      status: "failed",
                      duration: 21,
                      retry: 0,
                      startTime: "2026-01-01T00:00:00.000Z",
                      errors: [{ message: "assertion failed", stack: "at test.js:1" }],
                      stdout: [{ text: "request completed" }],
                      stderr: [],
                      steps: [
                        {
                          title: "click submit",
                          category: "pw:api",
                          duration: 5,
                          steps: [{ title: "locator.click", duration: 3 }],
                        },
                      ],
                    },
                    {
                      status: "passed",
                      duration: 34,
                      retry: 1,
                      errors: [],
                      stdout: [],
                      stderr: [],
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    },
    {
      CI_COMMIT_SHA: "abc123",
      CI_BRANCH: "main",
      CI_ACTOR: "test-user",
      CI_REPOSITORY: "owner/repo",
      CI_RUN_ID: "42",
      CI_RUN_ATTEMPT: "1",
      CI_RUN_URL: "https://github.com/owner/repo/actions/runs/42",
    },
  );

  assert.equal(events.length, 2);
  assert.deepEqual(
    events.map(({ result, retry_index, final_attempt }) => ({
      result,
      retry_index,
      final_attempt,
    })),
    [
      { result: "failed", retry_index: 0, final_attempt: false },
      { result: "passed", retry_index: 1, final_attempt: true },
    ],
  );
  assert.equal(events[0].test_name, "creates a task");
  assert.equal(events[0].test_file, "e2e/tasks.spec.js");
  assert.equal(events[0].component, "frontend");
  assert.equal(events[0].failure_reason, "assertion failed");
  assert.equal(events[0].test_project, "chromium");
  assert.match(events[0].test_output, /assertion failed/);
  assert.match(events[0].test_output, /click submit/);
  assert.match(events[0].test_output, /locator.click/);
  assert.match(events[0].test_output, /request completed/);
  assert.equal(events[0].run_id, "42");
});

test("classifies Playwright API-suite failures as backend", () => {
  const [event] = buildEvents({
    suites: [
      {
        file: "e2e/users.spec.js",
        suites: [
          {
            title: "User account API",
            specs: [
              {
                title: "users can read their account",
                file: "e2e/users.spec.js",
                line: 12,
                tests: [
                  {
                    status: "unexpected",
                    results: [
                      {
                        status: "failed",
                        duration: 12,
                        errors: [{ message: "expected 200, received 500" }],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  });

  assert.equal(event.component, "backend");
  assert.equal(event.test_suite, "User account API");
  assert.equal(event.failure_reason, "expected 200, received 500");
  assert.equal(event.test_line, 12);
});

test("redacts credentials and marks truncated test output", () => {
  const [event] = buildEvents({
    suites: [
      {
        file: "e2e/auth.spec.js",
        specs: [
          {
            title: "logs sensitive output safely",
            tests: [
              {
                status: "unexpected",
                results: [
                  {
                    status: "failed",
                    duration: 1,
                    errors: [
                      {
                        message: `password=topsecret Authorization: Basic c2VjcmV0 Bearer abc123 ${"x".repeat(9000)}`,
                      },
                    ],
                    stdout: [],
                    stderr: [],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  });

  assert.doesNotMatch(event.test_output, /topsecret/);
  assert.doesNotMatch(event.test_output, /c2VjcmV0|abc123/);
  assert.equal(event.test_output.length, 8000);
  assert.equal(event.output_truncated, true);
});
