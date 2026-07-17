import {
  lstatSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  convertPlaywrightV8Coverage,
} from "./coverage-conversion.mjs";

const MAX_REPORTS = 256;
const MAX_REPORT_BYTES = 16 * 1024 * 1024;
const MAX_TOTAL_BYTES = 64 * 1024 * 1024;
const MAX_SOURCE_BYTES = 4 * 1024 * 1024;

function fail(message) {
  throw new TypeError(`invalid Node V8 coverage directory: ${message}`);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function argumentsFrom(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const flag = argv[index];
    const value = argv[index + 1];
    if (
      !["--node-v8-directory", "--repo-root", "--output"].includes(flag) ||
      typeof value !== "string"
    ) {
      fail("expected --node-v8-directory, --repo-root, and --output values");
    }
    if (Object.hasOwn(values, flag)) {
      fail(`duplicate argument ${flag}`);
    }
    values[flag] = value;
  }
  if (Object.keys(values).length !== 3) {
    fail("expected --node-v8-directory, --repo-root, and --output values");
  }
  return values;
}

function isMaintainedSource(path) {
  const parts = path.split("/");
  if (
    parts.some((part) =>
      ["tests", "test", "node_modules", "build", "dist"].includes(
        part.toLowerCase(),
      ),
    )
  ) {
    return false;
  }
  if (path.startsWith("backend/webrender/")) {
    return (
      path.endsWith(".js") &&
      !path.includes("/static/vendor/") &&
      !path.endsWith(".min.js")
    );
  }
  return (
    path.startsWith("tooling/web-ci/") &&
    (path.endsWith(".js") || path.endsWith(".mjs"))
  );
}

function canonicalSource(url, repoRoot) {
  if (typeof url !== "string" || !url.startsWith("file://")) {
    return null;
  }
  let sourcePath;
  try {
    sourcePath = realpathSync(fileURLToPath(url));
  } catch {
    return null;
  }
  const prefix = `${repoRoot}${sep}`;
  if (!sourcePath.startsWith(prefix) || !lstatSync(sourcePath).isFile()) {
    return null;
  }
  const repoPath = relative(repoRoot, sourcePath).split(sep).join("/");
  return isMaintainedSource(repoPath) ? { repoPath, sourcePath } : null;
}

function readSource(sourcePath) {
  const size = statSync(sourcePath).size;
  if (size <= 0 || size > MAX_SOURCE_BYTES) {
    fail(`source has invalid size: ${sourcePath}`);
  }
  return readFileSync(sourcePath, "utf8");
}

function mergeEntry(entries, source, repoPath, rawEntry) {
  if (!Array.isArray(rawEntry.functions)) {
    fail(`source entry lacks functions: ${repoPath}`);
  }
  const record = entries.get(repoPath) ?? { source, ranges: new Map() };
  if (record.source !== source) {
    fail(`source changed between reports: ${repoPath}`);
  }
  for (const functionCoverage of rawEntry.functions) {
    if (!isObject(functionCoverage) || !Array.isArray(functionCoverage.ranges)) {
      fail(`invalid function ranges: ${repoPath}`);
    }
    for (const range of functionCoverage.ranges) {
      if (!isObject(range)) {
        fail(`invalid range: ${repoPath}`);
      }
      const { startOffset, endOffset, count } = range;
      if (
        !Number.isSafeInteger(startOffset) ||
        !Number.isSafeInteger(endOffset) ||
        !Number.isSafeInteger(count) ||
        startOffset < 0 ||
        endOffset <= startOffset ||
        endOffset > source.length ||
        count < 0
      ) {
        fail(`invalid range bounds: ${repoPath}`);
      }
      const key = `${startOffset}:${endOffset}`;
      const merged = (record.ranges.get(key)?.count ?? 0) + count;
      if (!Number.isSafeInteger(merged)) {
        fail(`range count overflow: ${repoPath}`);
      }
      record.ranges.set(key, { startOffset, endOffset, count: merged });
    }
  }
  entries.set(repoPath, record);
}

function readEntries(directory, repoRoot) {
  const names = readdirSync(directory)
    .filter((name) => /^coverage-[0-9]+-[0-9]+-[0-9]+\.json$/u.test(name))
    .sort();
  if (names.length === 0 || names.length > MAX_REPORTS) {
    fail("report count is empty or exceeds the bounded maximum");
  }
  let totalBytes = 0;
  const entries = new Map();
  for (const name of names) {
    const reportPath = resolve(directory, name);
    const size = statSync(reportPath).size;
    totalBytes += size;
    if (size <= 0 || size > MAX_REPORT_BYTES || totalBytes > MAX_TOTAL_BYTES) {
      fail(`report size is invalid: ${name}`);
    }
    let document;
    try {
      document = JSON.parse(readFileSync(reportPath, "utf8"));
    } catch (error) {
      fail(`report is not valid JSON: ${name}: ${error.message}`);
    }
    if (!isObject(document) || !Array.isArray(document.result)) {
      fail(`report lacks a result array: ${name}`);
    }
    for (const rawEntry of document.result) {
      if (!isObject(rawEntry)) {
        fail(`report contains a non-object entry: ${name}`);
      }
      const canonical = canonicalSource(rawEntry.url, repoRoot);
      if (canonical === null) {
        continue;
      }
      const source = readSource(canonical.sourcePath);
      mergeEntry(entries, source, canonical.repoPath, rawEntry);
    }
  }
  if (entries.size === 0) {
    fail("reports contain no maintained repository JavaScript");
  }
  return [...entries.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([repoPath, record]) => ({
      repoPath,
      source: record.source,
      functions: [{ ranges: [...record.ranges.values()] }],
    }));
}

/** Convert a bounded NODE_V8_COVERAGE directory to the canonical envelope. */
export async function convertNodeV8Directory({ directory, repoRoot }) {
  const canonicalRoot = realpathSync(repoRoot);
  const canonicalDirectory = realpathSync(directory);
  const entries = readEntries(canonicalDirectory, canonicalRoot);
  return convertPlaywrightV8Coverage(entries, (entry) => entry.repoPath);
}

function writeAtomically(output, document) {
  const outputPath = resolve(output);
  const temporaryDirectory = mkdtempSync(resolve(dirname(outputPath), ".coverage-"));
  const temporaryPath = resolve(temporaryDirectory, "report.json");
  try {
    writeFileSync(temporaryPath, `${JSON.stringify(document, null, 2)}\n`, {
      encoding: "utf8",
      flag: "wx",
    });
    renameSync(temporaryPath, outputPath);
  } finally {
    rmSync(temporaryDirectory, { recursive: true, force: true });
  }
}

async function main(argv) {
  const values = argumentsFrom(argv);
  const document = await convertNodeV8Directory({
    directory: values["--node-v8-directory"],
    repoRoot: values["--repo-root"],
  });
  writeAtomically(values["--output"], document);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main(process.argv.slice(2));
}
