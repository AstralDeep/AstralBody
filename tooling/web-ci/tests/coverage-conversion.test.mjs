import assert from "node:assert/strict";
import test from "node:test";

import {
  COVERAGE_PRODUCER,
  convertPlaywrightV8Coverage,
  convertPlaywrightV8Entry,
} from "../coverage-conversion.mjs";

function entry(source, nestedRanges = []) {
  return {
    url: "https://candidate.invalid/static/client.js",
    source,
    functions: [
      { ranges: [{ startOffset: 0, endOffset: source.length, count: 1 }] },
      ...nestedRanges.map((range) => ({ ranges: [range] })),
    ],
  };
}

test("comment padding cannot mask one uncovered executable line", async () => {
  const source =
    Array.from({ length: 9 }, (_, index) => `// padding ${index + 1}\n`).join("") +
    "neverCalled();\n";
  const startOffset = source.indexOf("neverCalled");
  const converted = await convertPlaywrightV8Entry(
    entry(source, [
      {
        startOffset,
        endOffset: source.indexOf("\n", startOffset),
        count: 0,
      },
    ]),
    { sourcePath: "backend/webrender/static/client.js" },
  );

  assert.deepEqual(Object.values(converted.statementMap), [
    {
      start: { line: 10, column: 0 },
      end: { line: 10, column: 11 },
    },
  ]);
  assert.deepEqual(converted.s, { 0: 0 });
});

test("comments, blank lines, sourceURL, and punctuation-only lines are absent", async () => {
  const source =
    "\n// pure comment\nconst hit = 1;\n\nfunction never() {\n" +
    "  return 2;\n}\n//# sourceURL=https://candidate.invalid/static/client.js\n";
  const functionStart = source.indexOf("function never");
  const functionEnd = source.indexOf("}\n", functionStart) + 1;
  const converted = await convertPlaywrightV8Entry(
    entry(source, [
      { startOffset: functionStart, endOffset: functionEnd, count: 0 },
    ]),
    { sourcePath: "backend/webrender/static/client.js" },
  );

  assert.deepEqual(
    Object.values(converted.statementMap).map((statement) => statement.start.line),
    [3, 5, 6],
  );
  assert.deepEqual(converted.s, { 0: 1, 1: 0, 2: 0 });
});

test("a line is covered when any executable token on it is covered", async () => {
  const source = "covered(); missed();\n";
  const missedStart = source.indexOf("missed");
  const converted = await convertPlaywrightV8Entry(
    entry(source, [
      {
        startOffset: missedStart,
        endOffset: source.indexOf(";", missedStart),
        count: 0,
      },
    ]),
    { sourcePath: "tooling/web-ci/probe.mjs" },
  );
  assert.deepEqual(converted.s, { 0: 1 });
});

test("the exact lock-pinned producer envelope is emitted", async () => {
  const source = "const value = 1;\n";
  const converted = await convertPlaywrightV8Coverage(
    [entry(source)],
    () => "backend/webrender/static/client.js",
  );
  assert.deepEqual(
    Object.fromEntries(
      Object.entries(converted).filter(([key]) => key !== "coverage"),
    ),
    COVERAGE_PRODUCER,
  );
  assert.deepEqual(Object.keys(converted.coverage), [
    "backend/webrender/static/client.js",
  ]);
});

test("malformed, ambiguous, duplicate, and comment-only inputs fail closed", async () => {
  const source = "value();\n";
  const ambiguous = entry(source, [
    { startOffset: 0, endOffset: source.length, count: 0 },
  ]);
  await assert.rejects(
    convertPlaywrightV8Entry(ambiguous, {
      sourcePath: "backend/webrender/static/client.js",
    }),
    /ambiguous V8 ranges/u,
  );
  await assert.rejects(
    convertPlaywrightV8Entry(entry("// comment only\n"), {
      sourcePath: "backend/webrender/static/client.js",
    }),
    /no executable tokens/u,
  );
  await assert.rejects(
    convertPlaywrightV8Coverage(
      [entry(source), entry(source)],
      () => "backend/webrender/static/client.js",
    ),
    /duplicate resolved source path/u,
  );
});
