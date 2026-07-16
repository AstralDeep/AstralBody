import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const TOOLING_ROOT = resolve(import.meta.dirname, "..");
const REPO_ROOT = resolve(TOOLING_ROOT, "../..");
const CLI = resolve(TOOLING_ROOT, "coverage-conversion-cli.mjs");

function run(arguments_, options = {}) {
  const result = spawnSync(process.execPath, arguments_, {
    cwd: TOOLING_ROOT,
    encoding: "utf8",
    ...options,
  });
  assert.equal(
    result.status,
    0,
    `command failed\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
  );
}

test("two-pass Node coverage maps the converter and its CLI", () => {
  const directory = mkdtempSync(resolve(tmpdir(), "astraldeep-node-v8-"));
  const interim = resolve(directory, "interim.json");
  const output = resolve(directory, "canonical.json");
  const coverageEnvironment = {
    ...process.env,
    NODE_V8_COVERAGE: directory,
  };
  // A nested test runner must not inherit its parent's private child marker.
  delete coverageEnvironment.NODE_TEST_CONTEXT;

  run(["--test", "tests/coverage-conversion.test.mjs"], {
    env: coverageEnvironment,
  });
  assert.ok(
    readdirSync(directory).some((name) => name.startsWith("coverage-")),
    `NODE_V8_COVERAGE did not emit a report: ${readdirSync(directory).join(", ")}`,
  );
  // This first conversion flushes coverage for the CLI itself on process exit.
  run(
    [
      CLI,
      "--node-v8-directory",
      directory,
      "--repo-root",
      REPO_ROOT,
      "--output",
      interim,
    ],
    { env: coverageEnvironment },
  );
  // The second conversion sees both the tests' and the first CLI run's reports.
  run([
    CLI,
    "--node-v8-directory",
    directory,
    "--repo-root",
    REPO_ROOT,
    "--output",
    output,
  ]);

  const document = JSON.parse(readFileSync(output, "utf8"));
  assert.deepEqual(Object.keys(document.coverage).sort(), [
    "tooling/web-ci/coverage-conversion-cli.mjs",
    "tooling/web-ci/coverage-conversion.mjs",
  ]);
  for (const record of Object.values(document.coverage)) {
    assert.ok(Object.keys(record.statementMap).length > 0);
    assert.deepEqual(Object.keys(record.statementMap), Object.keys(record.s));
  }
});
