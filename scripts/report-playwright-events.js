#!/usr/bin/env node
"use strict";

const fs = require("node:fs");

const MAX_OUTPUT_LENGTH = 8000;
const allowedName = /^[A-Za-z0-9._-]+$/;

function getText(entries = []) {
  return entries
    .map((entry) => {
      if (typeof entry === "string") return entry;
      return entry && typeof entry.text === "string" ? entry.text : "";
    })
    .filter(Boolean)
    .join("\n");
}

function redactOutput(value) {
  return value
    .replace(
      /((?:authorization|password|token|secret)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|(?:Basic|Bearer)\s+[A-Za-z0-9._~+/-]+=*|[^\s,;]+)/gi,
      "$1[REDACTED]",
    )
    .replace(/\b(Basic|Bearer)\s+[A-Za-z0-9._~+/-]+=*/gi, "$1 [REDACTED]");
}

function getStepLines(steps = [], depth = 0) {
  return steps.flatMap((step) => {
    const duration = Number.isFinite(step.duration)
      ? ` (${step.duration} ms)`
      : "";
    const error =
      step.error && step.error.message ? ` - ${step.error.message}` : "";
    return [
      `${"  ".repeat(depth)}${step.category || "step"}: ${step.title || "Untitled"}${duration}${error}`,
      ...getStepLines(step.steps, depth + 1),
    ];
  });
}

function buildEvents(report, metadata = process.env) {
  const events = [];

  function addSuite(suite, parentFile = "") {
    const testFile = suite.file || parentFile;

    for (const spec of suite.specs || []) {
      for (const test of spec.tests || []) {
        const results = test.results || [];
        const attempts = results.length
          ? results
          : [
              {
                status:
                  test.expectedStatus === "skipped" || test.status === "skipped"
                    ? "skipped"
                    : "not_run",
                duration: 0,
                retry: 0,
              },
            ];

        attempts.forEach((attempt, index) => {
          const outputParts = [];
          for (const error of attempt.errors || []) {
            if (error.message) outputParts.push(error.message);
            if (error.stack && error.stack !== error.message) {
              outputParts.push(error.stack);
            }
          }

          const stdout = getText(attempt.stdout);
          const stderr = getText(attempt.stderr);
          const steps = getStepLines(attempt.steps);
          if (steps.length) outputParts.push(`steps:\n${steps.join("\n")}`);
          if (stdout) outputParts.push(`stdout:\n${stdout}`);
          if (stderr) outputParts.push(`stderr:\n${stderr}`);

          const output = redactOutput(outputParts.join("\n\n"));
          const status = attempt.status || "unknown";
          const level =
            status === "passed"
              ? "info"
              : status === "skipped" || status === "not_run"
                ? "warn"
                : "error";
          const eventTime = attempt.startTime || new Date().toISOString();

          events.push({
            event_time: eventTime,
            event_type: "playwright_test",
            level,
            result: status,
            test_status: test.status || "unknown",
            test_name: spec.title,
            test_file: spec.file || testFile,
            test_project: test.projectName || "",
            duration_ms: Number(attempt.duration) || 0,
            retry_index: Number.isInteger(attempt.retry) ? attempt.retry : index,
            final_attempt: index === attempts.length - 1,
            test_output: output.slice(0, MAX_OUTPUT_LENGTH),
            output_truncated: output.length > MAX_OUTPUT_LENGTH,
            commit: metadata.CI_COMMIT_SHA || "",
            branch: metadata.CI_BRANCH || "",
            actor: metadata.CI_ACTOR || "",
            repository: metadata.CI_REPOSITORY || "",
            run_id: metadata.CI_RUN_ID || "",
            run_attempt: metadata.CI_RUN_ATTEMPT || "",
            run_url: metadata.CI_RUN_URL || "",
            service: "taskboard",
            log: `Playwright ${status}: ${spec.title}`,
          });
        });
      }

      for (const childSuite of spec.suites || []) {
        addSuite(childSuite, testFile);
      }
    }

    for (const childSuite of suite.suites || []) {
      addSuite(childSuite, testFile);
    }
  }

  for (const suite of report.suites || []) {
    addSuite(suite);
  }
  return events;
}

function validateEnvironment(metadata) {
  const required = [
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
  ];
  for (const name of required) {
    if (!metadata[name]) throw new Error(`${name} is required.`);
  }

  const baseUrl = new URL(metadata.OPENOBSERVE_URL);
  if (
    baseUrl.protocol !== "https:" ||
    baseUrl.pathname !== "/" ||
    baseUrl.search ||
    baseUrl.hash ||
    baseUrl.username ||
    baseUrl.password
  ) {
    throw new Error("OPENOBSERVE_URL must be an HTTPS base URL without a path.");
  }
  if (
    !allowedName.test(metadata.OPENOBSERVE_ORG) ||
    !allowedName.test(metadata.OPENOBSERVE_STREAM)
  ) {
    throw new Error("OPENOBSERVE_ORG and OPENOBSERVE_STREAM contain unsupported characters.");
  }
  if (!/^Basic\s+[A-Za-z0-9+/=]+$/.test(metadata.OPENOBSERVE_AUTHORIZATION)) {
    throw new Error("OPENOBSERVE_AUTHORIZATION must be a Basic authorization value.");
  }
  return baseUrl;
}

async function sendReport(reportPath, metadata = process.env) {
  if (!fs.existsSync(reportPath)) {
    console.warn(
      `Playwright JSON report not found at ${reportPath}; no per-test events were sent.`,
    );
    return;
  }

  const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
  const events = buildEvents(report, metadata);
  if (events.length === 0) {
    throw new Error("The Playwright JSON report contains no test results.");
  }

  const baseUrl = validateEnvironment(metadata);
  const endpoint = new URL(
    `/api/${metadata.OPENOBSERVE_ORG}/${metadata.OPENOBSERVE_STREAM}/_json`,
    baseUrl,
  );
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: metadata.OPENOBSERVE_AUTHORIZATION,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(events),
    signal: AbortSignal.timeout(20_000),
  });
  const responseBody = await response.text();
  if (!response.ok) {
    throw new Error(`OpenObserve returned HTTP ${response.status}: ${responseBody}`);
  }

  console.log(`Sent ${events.length} Playwright result events to OpenObserve.`);
}

if (require.main === module) {
  const reportPath = process.argv[2];
  if (!reportPath) {
    console.error("Usage: node scripts/report-playwright-events.js <report.json>");
    process.exitCode = 2;
  } else {
    sendReport(reportPath).catch((error) => {
      console.error(`Could not send Playwright results: ${error.message}`);
      process.exitCode = 1;
    });
  }
}

module.exports = { buildEvents, getStepLines, sendReport };
