import { parse } from "espree";
import v8ToIstanbul from "v8-to-istanbul";

export const COVERAGE_PRODUCER = Object.freeze({
  schema_version: 1,
  producer: "astraldeep-playwright-executable-lines",
  producer_version: 1,
  v8_to_istanbul_version: "9.3.0",
  espree_version: "11.2.0",
});

function fail(message) {
  throw new TypeError(`invalid Playwright V8 coverage: ${message}`);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseTokens(source) {
  const options = {
    ecmaVersion: "latest",
    loc: true,
    range: true,
    tokens: true,
  };
  try {
    return parse(source, { ...options, sourceType: "module" }).tokens;
  } catch (moduleError) {
    try {
      return parse(source, { ...options, sourceType: "script" }).tokens;
    } catch (scriptError) {
      throw new SyntaxError(
        "JavaScript source is neither a valid module nor script: " +
          `module: ${moduleError.message}; script: ${scriptError.message}`,
        { cause: scriptError },
      );
    }
  }
}

function validatedRanges(entry, sourceLength) {
  if (!isObject(entry) || typeof entry.source !== "string") {
    fail("entry must contain its exact source text");
  }
  if (!Array.isArray(entry.functions) || entry.functions.length === 0) {
    fail("entry must contain non-empty function coverage");
  }
  const ranges = [];
  for (const functionCoverage of entry.functions) {
    if (!isObject(functionCoverage) || !Array.isArray(functionCoverage.ranges)) {
      fail("function coverage must contain ranges");
    }
    for (const range of functionCoverage.ranges) {
      if (!isObject(range)) {
        fail("range must be an object");
      }
      const { startOffset, endOffset, count } = range;
      if (
        !Number.isSafeInteger(startOffset) ||
        !Number.isSafeInteger(endOffset) ||
        !Number.isSafeInteger(count) ||
        startOffset < 0 ||
        endOffset <= startOffset ||
        endOffset > sourceLength ||
        count < 0
      ) {
        fail("range offsets and count must be bounded non-negative integers");
      }
      ranges.push({ startOffset, endOffset, count });
    }
  }
  if (ranges.length === 0) {
    fail("entry has no coverage ranges");
  }
  return ranges;
}

function effectiveCount(token, ranges) {
  const covering = ranges.filter(
    (range) =>
      range.startOffset <= token.range[0] && range.endOffset >= token.range[1],
  );
  if (covering.length === 0) {
    fail(`no V8 range covers token at offset ${token.range[0]}`);
  }
  const smallestSpan = Math.min(
    ...covering.map((range) => range.endOffset - range.startOffset),
  );
  const mostSpecific = covering.filter(
    (range) => range.endOffset - range.startOffset === smallestSpan,
  );
  const identities = new Set(
    mostSpecific.map(
      (range) => `${range.startOffset}:${range.endOffset}:${range.count}`,
    ),
  );
  if (identities.size !== 1) {
    fail(`ambiguous V8 ranges cover token at offset ${token.range[0]}`);
  }
  return mostSpecific[0].count;
}

function tokenLineSegments(token) {
  const finalLine =
    token.loc.end.line > token.loc.start.line && token.loc.end.column === 0
      ? token.loc.end.line - 1
      : token.loc.end.line;
  const segments = [];
  for (let line = token.loc.start.line; line <= finalLine; line += 1) {
    segments.push({
      line,
      startColumn: line === token.loc.start.line ? token.loc.start.column : 0,
      endColumn:
        line === token.loc.end.line
          ? token.loc.end.column
          : Number.MAX_SAFE_INTEGER,
    });
  }
  return segments;
}

async function validatePinnedConverter(entry, sourcePath) {
  const converter = v8ToIstanbul(sourcePath, 0, { source: entry.source });
  await converter.load();
  converter.applyCoverage(entry.functions);
  const unfiltered = converter.toIstanbul();
  if (!isObject(unfiltered) || Object.keys(unfiltered).length === 0) {
    fail("v8-to-istanbul produced no source record");
  }
}

function validateSourcePath(sourcePath) {
  if (
    typeof sourcePath !== "string" ||
    sourcePath.startsWith("/") ||
    sourcePath.includes("\\") ||
    sourcePath.split("/").includes("..") ||
    !sourcePath.match(/^(backend\/webrender|tooling\/web-ci)\/.+\.(?:js|mjs)$/u)
  ) {
    fail("sourcePath must be a canonical maintained repository-relative JS path");
  }
}

/** Convert one Playwright V8 source entry into one executable-line record. */
export async function convertPlaywrightV8Entry(entry, { sourcePath } = {}) {
  validateSourcePath(sourcePath);
  const source = isObject(entry) ? entry.source : undefined;
  if (typeof source !== "string") {
    fail("entry must contain its exact source text");
  }
  const ranges = validatedRanges(entry, source.length);
  const tokens = parseTokens(source).filter((token) => token.type !== "Punctuator");
  if (tokens.length === 0) {
    fail("source has no executable tokens");
  }

  await validatePinnedConverter(entry, sourcePath);

  const lines = new Map();
  for (const token of tokens) {
    const count = effectiveCount(token, ranges);
    for (const segment of tokenLineSegments(token)) {
      const line = lines.get(segment.line) ?? {
        startColumn: segment.startColumn,
        endColumn: segment.endColumn,
        covered: false,
      };
      line.startColumn = Math.min(line.startColumn, segment.startColumn);
      line.endColumn = Math.max(line.endColumn, segment.endColumn);
      // A physical line is covered when any executable token on it is covered.
      line.covered ||= count > 0;
      lines.set(segment.line, line);
    }
  }

  const statementMap = {};
  const hits = {};
  for (const [index, [lineNumber, line]] of [...lines.entries()]
    .sort(([left], [right]) => left - right)
    .entries()) {
    const id = String(index);
    const endColumn = Number.isSafeInteger(line.endColumn) ? line.endColumn : 0;
    statementMap[id] = {
      start: { line: lineNumber, column: line.startColumn },
      end: { line: lineNumber, column: endColumn },
    };
    hits[id] = line.covered ? 1 : 0;
  }
  return { path: sourcePath, statementMap, s: hits };
}

/** Convert multiple entries and add the exact collector producer envelope. */
export async function convertPlaywrightV8Coverage(entries, resolveSourcePath) {
  if (!Array.isArray(entries) || entries.length === 0) {
    fail("coverage must contain at least one source entry");
  }
  if (typeof resolveSourcePath !== "function") {
    fail("a source-path resolver is required");
  }
  const coverage = {};
  for (const entry of entries) {
    const sourcePath = resolveSourcePath(entry);
    if (Object.hasOwn(coverage, sourcePath)) {
      fail(`duplicate resolved source path ${sourcePath}`);
    }
    coverage[sourcePath] = await convertPlaywrightV8Entry(entry, { sourcePath });
  }
  return { ...COVERAGE_PRODUCER, coverage };
}
