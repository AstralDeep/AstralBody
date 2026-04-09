import { describe, it, expect } from "vitest";
import {
    normalizeLlmMarkdown,
    stripUiComponentJson,
    bulletizeIndentedBlocks,
    normalizeLatexDelimiters,
} from "./normalizeLlmMarkdown";

describe("bulletizeIndentedBlocks (Bug 1: Gemma indented pseudo-lists)", () => {
    it("converts an indented `name: description` block into bullet items", () => {
        const input = [
            "**Data Analysis**",
            "",
            "    analyze_csv: Analyzes CSV files.",
            "    modify_data: Performs CRUD operations.",
            "",
            "Next paragraph.",
        ].join("\n");

        const out = bulletizeIndentedBlocks(input);

        expect(out).toContain("- analyze_csv: Analyzes CSV files.");
        expect(out).toContain("- modify_data: Performs CRUD operations.");
        expect(out).not.toMatch(/^ {4}analyze_csv/m);
    });

    it("leaves real indented code blocks alone", () => {
        const input = [
            "Here is some code:",
            "",
            "    function foo() {",
            "        return 42;",
            "    }",
            "",
            "Done.",
        ].join("\n");

        const out = bulletizeIndentedBlocks(input);

        expect(out).toContain("    function foo() {");
        expect(out).toContain("        return 42;");
        expect(out).not.toContain("- function foo");
    });

    it("leaves fenced code blocks alone even if they contain 4-space-indented lines", () => {
        const input = [
            "```",
            "    not_a_list: this should stay in the fence",
            "    other_thing: also stays",
            "```",
        ].join("\n");

        const out = bulletizeIndentedBlocks(input);

        expect(out).toBe(input);
    });

    it("leaves an already-well-formed bullet list unchanged", () => {
        const input = [
            "Here is a list:",
            "",
            "- one",
            "- two",
            "- three",
        ].join("\n");

        expect(bulletizeIndentedBlocks(input)).toBe(input);
    });

    it("is idempotent", () => {
        const input = [
            "**Section**",
            "",
            "    foo: bar",
            "    baz: qux",
        ].join("\n");

        const once = bulletizeIndentedBlocks(input);
        const twice = bulletizeIndentedBlocks(once);
        expect(twice).toBe(once);
    });
});

describe("stripUiComponentJson (Bug 2: leaked UI-component payloads)", () => {
    it("removes a standalone array of component objects between paragraphs", () => {
        const input = [
            "I've created a chart for you.",
            "",
            '[{"type": "card", "id": "memory-pie-chart", "title": "Memory"}]',
            "",
            "Anything else?",
        ].join("\n");

        const out = stripUiComponentJson(input);

        expect(out).toContain("I've created a chart for you.");
        expect(out).toContain("Anything else?");
        expect(out).not.toContain('"type"');
        expect(out).not.toContain("memory-pie-chart");
    });

    it("removes a bare component object (no array wrapper)", () => {
        const input = 'before {"type": "chart", "data": [1, 2, 3]} after';
        const out = stripUiComponentJson(input);
        expect(out).toContain("before");
        expect(out).toContain("after");
        expect(out).not.toContain('"type"');
    });

    it("balances brackets even when ] appears inside a string value", () => {
        const input = 'pre {"type": "card", "label": "x[0]"} post';
        const out = stripUiComponentJson(input);
        expect(out).toContain("pre");
        expect(out).toContain("post");
        expect(out).not.toContain('"label"');
    });

    it("does not strip plain objects that lack a leading \"type\" key", () => {
        const input = 'config: {"foo": 1, "bar": 2}';
        expect(stripUiComponentJson(input)).toBe(input);
    });

    it("leaves truncated/malformed JSON alone (no crash, no removal)", () => {
        const input = 'broken: {"type": "card", "label": "x';
        const out = stripUiComponentJson(input);
        expect(out).toBe(input);
    });

    it("handles a deeply nested component payload", () => {
        const input = [
            "Result:",
            "",
            '[{"type": "card", "content": [{"type": "chart", "data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]}]}]',
            "",
            "Done.",
        ].join("\n");

        const out = stripUiComponentJson(input);
        expect(out).toContain("Result:");
        expect(out).toContain("Done.");
        expect(out).not.toContain('"type"');
        expect(out).not.toContain('"chart"');
    });
});

describe("normalizeLatexDelimiters (Bug 3: LaTeX → remark-math)", () => {
    it("converts \\[ ... \\] to $$ ... $$", () => {
        expect(normalizeLatexDelimiters("\\[x^2\\]")).toBe("$$x^2$$");
    });

    it("converts \\( ... \\) to $ ... $", () => {
        expect(normalizeLatexDelimiters("\\(y\\)")).toBe("$y$");
    });
});

describe("normalizeLlmMarkdown (top-level)", () => {
    it("returns empty string for empty input", () => {
        expect(normalizeLlmMarkdown("")).toBe("");
    });

    it("is safe against non-string input (defensive)", () => {
        // @ts-expect-error — testing runtime safety
        expect(normalizeLlmMarkdown(null)).toBe("");
        // @ts-expect-error — testing runtime safety
        expect(normalizeLlmMarkdown(undefined)).toBe("");
    });

    it("is idempotent across all passes", () => {
        const input = [
            "**Tools**",
            "",
            "    foo: does foo",
            "    bar: does bar",
            "",
            'Look: [{"type": "card", "id": "x"}]',
            "",
            "Math: \\(a^2 + b^2\\)",
        ].join("\n");

        const once = normalizeLlmMarkdown(input);
        const twice = normalizeLlmMarkdown(once);
        expect(twice).toBe(once);
    });

    it("handles a realistic Gemma response end-to-end", () => {
        const input = [
            "I've created a pie chart showing your current system memory allocation.",
            "",
            '[{"type": "card", "id": "memory-pie-chart", "title": "System Memory"}]',
            "",
            "It shows about 14.8% used.",
            "",
            "**Other tools available:**",
            "",
            "    analyze_csv: Analyzes CSV files.",
            "    modify_data: CRUD operations.",
        ].join("\n");

        const out = normalizeLlmMarkdown(input);

        // JSON gone
        expect(out).not.toContain("memory-pie-chart");
        expect(out).not.toContain('"type"');
        // Narrative preserved
        expect(out).toContain("I've created a pie chart");
        expect(out).toContain("14.8%");
        // Bullets created
        expect(out).toContain("- analyze_csv: Analyzes CSV files.");
        expect(out).toContain("- modify_data: CRUD operations.");
    });
});
