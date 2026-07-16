#!/usr/bin/env node
/** Launch the feature-060 browser proof only inside the pinned Playwright image. */

import { existsSync, readFileSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { spawnSync } from "node:child_process";


const TOOL_ROOT = import.meta.dirname;
const PIN_PATH = resolve(TOOL_ROOT, "playwright-image.txt");
const LOCK_PATH = resolve(TOOL_ROOT, "package-lock.json");
const PACKAGE_PATH = resolve(TOOL_ROOT, "package.json");
const PLAYWRIGHT_CLI = resolve(TOOL_ROOT, "node_modules/@playwright/test/cli.js");
const GIT_SHA = /^[0-9a-f]{40}$/u;
const SEMVER = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/u;
const RELEASE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$/u;


function reject(message) {
  process.stderr.write(`browser release runner rejected: ${message}\n`);
  process.exit(2);
}


function parseArguments(argv) {
  const allowed = new Set([
    "base-url",
    "candidate-sha",
    "coverage-output",
    "image-ref",
    "output",
    "release-id",
    "release-version",
    "staging-file",
  ]);
  const parsed = {};
  for (let index = 0; index < argv.length; index += 2) {
    const option = argv[index];
    const value = argv[index + 1];
    if (!option?.startsWith("--") || value === undefined || value.startsWith("--")) {
      reject(`arguments must be --name value pairs (received ${option ?? "end of input"})`);
    }
    const name = option.slice(2);
    if (!allowed.has(name) || Object.hasOwn(parsed, name)) {
      reject(`unknown or duplicate option --${name}`);
    }
    parsed[name] = value;
  }
  return parsed;
}


function required(value, name) {
  if (typeof value !== "string" || value.length === 0) reject(`${name} is required`);
  return value;
}


function validateUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    reject("base-url is not a valid URL");
  }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== "https:" || parsed.username || parsed.password
      || parsed.search || parsed.hash || ["localhost", "127.0.0.1", "::1"].includes(host)) {
    reject("base-url must be non-loopback HTTPS without userinfo, query, or fragment");
  }
  return value.replace(/\/+$/u, "");
}


function validateOutputPath(value, name) {
  if (!isAbsolute(value)) reject(`${name} must be an absolute container path`);
  return value;
}


const args = parseArguments(process.argv.slice(2));
const imageRef = required(args["image-ref"] ?? process.env.ASTRAL_PLAYWRIGHT_IMAGE, "image-ref");
const pinnedImage = readFileSync(PIN_PATH, "utf8").trim();
if (imageRef !== pinnedImage || !/@sha256:[0-9a-f]{64}$/u.test(imageRef)) {
  reject("the executing Playwright image does not equal playwright-image.txt");
}
if (!existsSync("/ms-playwright") || process.platform !== "linux") {
  reject("qualifying execution requires the official Linux Playwright container");
}

const packageJson = JSON.parse(readFileSync(PACKAGE_PATH, "utf8"));
const packageLock = JSON.parse(readFileSync(LOCK_PATH, "utf8"));
const packageVersion = packageJson.devDependencies?.["@playwright/test"];
const lockedVersion = packageLock.packages?.["node_modules/@playwright/test"]?.version;
const coreVersion = packageLock.packages?.["node_modules/playwright-core"]?.version;
const imageVersion = /playwright:v([0-9]+\.[0-9]+\.[0-9]+)-/u.exec(pinnedImage)?.[1];
if (!packageVersion || packageVersion !== lockedVersion || lockedVersion !== coreVersion
    || coreVersion !== imageVersion) {
  reject("package, lock, playwright-core, and image versions are not identical");
}
if (process.versions.node.split(".")[0] !== "24") {
  reject(`Node 24 is required (received ${process.versions.node})`);
}
const npmVersion = /(?:^| )npm\/([^ ]+)/u.exec(process.env.npm_config_user_agent ?? "")?.[1];
if (npmVersion !== "11.16.0") reject(`npm 11.16.0 via Corepack is required (received ${npmVersion ?? "unknown"})`);
if (!existsSync(PLAYWRIGHT_CLI)) reject("npm ci did not install the lock-pinned Playwright CLI");

const baseUrl = validateUrl(required(args["base-url"] ?? process.env.STAGING_URL, "base-url"));
const candidateSha = required(args["candidate-sha"] ?? process.env.SHA, "candidate-sha");
if (!GIT_SHA.test(candidateSha)) reject("candidate-sha must be one lowercase 40-character Git SHA");
const releaseId = required(args["release-id"] ?? process.env.ASTRAL_RELEASE_ID, "release-id");
if (!RELEASE_ID.test(releaseId)) reject("release-id is malformed");
const releaseVersion = required(
  args["release-version"] ?? process.env.ASTRAL_RELEASE_VERSION,
  "release-version",
);
if (!SEMVER.test(releaseVersion) || /\s/u.test(releaseVersion)) reject("release-version is malformed");
const stagingFile = validateOutputPath(
  required(args["staging-file"] ?? process.env.ASTRAL_RELEASE_STAGING_FILE, "staging-file"),
  "staging-file",
);
if (!existsSync(stagingFile)) reject("staging-file does not exist");
const output = validateOutputPath(required(args.output, "output"), "output");
const coverageOutput = validateOutputPath(
  required(args["coverage-output"], "coverage-output"),
  "coverage-output",
);
for (const secretName of ["ASTRAL_RELEASE_USERNAME", "ASTRAL_RELEASE_PASSWORD"]) {
  required(process.env[secretName], secretName);
}
for (const identityName of [
  "GITHUB_JOB",
  "GITHUB_RUN_ATTEMPT",
  "GITHUB_RUN_ID",
  "GITHUB_WORKFLOW",
  "RUNNER_ARCH",
  "RUNNER_NAME",
  "RUNNER_OS",
  "ASTRAL_RUNNER_ENVIRONMENT",
]) {
  required(process.env[identityName], identityName);
}

const environment = {
  ...process.env,
  ASTRAL_PLAYWRIGHT_IMAGE: pinnedImage,
  ASTRAL_RELEASE_BASE_URL: baseUrl,
  ASTRAL_RELEASE_CANDIDATE_SHA: candidateSha,
  ASTRAL_RELEASE_COVERAGE_OUTPUT: coverageOutput,
  ASTRAL_RELEASE_ID: releaseId,
  ASTRAL_RELEASE_OUTPUT: output,
  ASTRAL_RELEASE_STAGING_FILE: stagingFile,
  ASTRAL_RELEASE_VERSION: releaseVersion,
};
const completed = spawnSync(
  process.execPath,
  [
    PLAYWRIGHT_CLI,
    "test",
    "tests/release-060.spec.js",
    "--browser=chromium",
    "--workers=1",
    "--reporter=line",
  ],
  { cwd: TOOL_ROOT, env: environment, stdio: "inherit" },
);
if (completed.error) reject(`Playwright could not start: ${completed.error.message}`);
process.exit(completed.status ?? 2);
