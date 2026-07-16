import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "@playwright/test";

import { convertPlaywrightV8Entry } from "../coverage-conversion.mjs";

test("real Chromium V8 coverage excludes comment padding around an uncalled line", async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const source =
      Array.from({ length: 9 }, (_, index) => `// padding ${index + 1}\n`).join("") +
      "function uncalled(){ neverCalled(); }\n" +
      "//# sourceURL=https://candidate.invalid/static/client.js\n";
    await page.coverage.startJSCoverage({ resetOnNavigation: false });
    await page.addScriptTag({ content: source });
    const raw = await page.coverage.stopJSCoverage();
    const observed = raw.find(
      (candidate) =>
        candidate.url === "https://candidate.invalid/static/client.js",
    );
    assert.ok(observed, "Chromium did not return the sourceURL coverage entry");

    const converted = await convertPlaywrightV8Entry(observed, {
      sourcePath: "backend/webrender/static/client.js",
    });
    assert.deepEqual(Object.values(converted.statementMap), [
      {
        start: { line: 10, column: 0 },
        end: { line: 10, column: 32 },
      },
    ]);
    assert.deepEqual(converted.s, { 0: 0 });
  } finally {
    await browser.close();
  }
});
