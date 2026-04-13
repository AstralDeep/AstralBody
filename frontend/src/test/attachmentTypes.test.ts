/**
 * extensionOf / categoryOf parsing — defends against odd filenames the
 * file picker may hand us (trailing whitespace, NBSP, mixed case, etc.).
 */
import { describe, it, expect } from "vitest";
import { extensionOf, categoryOf, ACCEPT_ATTRIBUTE } from "../lib/attachmentTypes";

describe("extensionOf", () => {
  it.each([
    ["notes.txt", "txt"],
    ["NOTES.TXT", "txt"],
    ["report.PDF", "pdf"],
    ["a.b.c.docx", "docx"],
    ["0 ACCESS WEBSITE IN CHROME.txt", "txt"],
    ["screenshot.png", "png"],
    // Trailing whitespace / NBSP variants from quirky file systems
    ["weird.txt ", "txt"],
    ["weird.txt\u00A0", "txt"],
    ["  spaced.json  ", "json"],
  ])("parses %j → %j", (name, expected) => {
    expect(extensionOf(name)).toBe(expected);
  });

  it("returns '' for files with no extension", () => {
    expect(extensionOf("README")).toBe("");
    expect(extensionOf("")).toBe("");
    expect(extensionOf("trailing.")).toBe("");
  });
});

describe("categoryOf", () => {
  it.each([
    ["notes.txt", "text"],
    ["report.pdf", "document"],
    ["data.xlsx", "spreadsheet"],
    ["slides.pptx", "presentation"],
    ["pic.jpg", "image"],
    ["script.py", "text"],
  ])("classifies %j → %j", (name, cat) => {
    expect(categoryOf(name)).toBe(cat);
  });

  it("returns null for unsupported extensions", () => {
    expect(categoryOf("blueprint.dwg")).toBeNull();
    expect(categoryOf("unknown")).toBeNull();
  });
});

describe("ACCEPT_ATTRIBUTE", () => {
  it("includes every category and the original four legacy types", () => {
    expect(ACCEPT_ATTRIBUTE).toContain(".txt");
    expect(ACCEPT_ATTRIBUTE).toContain(".csv");
    expect(ACCEPT_ATTRIBUTE).toContain(".pdf");
    expect(ACCEPT_ATTRIBUTE).toContain(".docx");
    expect(ACCEPT_ATTRIBUTE).toContain(".xlsx");
    expect(ACCEPT_ATTRIBUTE).toContain(".pptx");
    expect(ACCEPT_ATTRIBUTE).toContain(".png");
    expect(ACCEPT_ATTRIBUTE).toContain(".jpg");
    expect(ACCEPT_ATTRIBUTE).toContain(".py");
  });

  it("contains only dotted extensions (no MIME globs)", () => {
    for (const part of ACCEPT_ATTRIBUTE.split(",")) {
      expect(part.startsWith(".")).toBe(true);
      expect(part).not.toContain("/");
    }
  });
});
