/**
 * Feature 013 follow-up — text extraction for assistant component arrays.
 *
 * The chat panel previously fell back to "Processing complete." whenever
 * the LLM returned a payload that didn't include a top-level `type:
 * "text"` entry. Greetings often arrive as a single alert / paragraph,
 * which left users staring at the fallback. The new extractor walks
 * containers recursively and pulls text out of paragraph / heading /
 * alert / note / markdown / code components too.
 *
 * Re-implements the helper inline (it's defined inside the component
 * closure) so we can exercise its rules without rendering the panel.
 */
import { describe, it, expect } from "vitest";

const TEXT_BEARING_TYPES = new Set([
    "text", "paragraph", "heading", "alert", "note", "markdown", "code",
]);

/** Mirrors FloatingChatPanel.extractTextFromComponents. */
function extractTextFromComponents(content: unknown): string {
    if (typeof content === "string") return content;
    if (!Array.isArray(content)) {
        if (content && typeof content === "object") {
            return extractTextFromComponents([content as Record<string, unknown>]);
        }
        return "";
    }
    const pieces: string[] = [];
    const walk = (node: unknown): void => {
        if (typeof node === "string") {
            if (node.trim()) pieces.push(node);
            return;
        }
        if (Array.isArray(node)) {
            for (const child of node) walk(child);
            return;
        }
        if (!node || typeof node !== "object") return;
        const obj = node as Record<string, unknown>;
        const type = typeof obj.type === "string" ? obj.type : undefined;
        if (type && TEXT_BEARING_TYPES.has(type)) {
            if (typeof obj.content === "string" && obj.content.trim()) pieces.push(obj.content);
            else if (typeof obj.message === "string" && obj.message.trim()) pieces.push(obj.message);
            else if (typeof obj.text === "string" && obj.text.trim()) pieces.push(obj.text);
            else if (typeof obj.title === "string" && obj.title.trim()) pieces.push(obj.title);
        }
        if (Array.isArray(obj.content)) walk(obj.content);
        if (Array.isArray(obj.children)) walk(obj.children);
        if (Array.isArray(obj.items)) walk(obj.items);
    };
    walk(content);
    const out = pieces.join("\n\n").trim();
    return out || "(No text content in this response.)";
}

describe("extractTextFromComponents — Feature 013 follow-up", () => {
    it("returns a plain string unchanged", () => {
        expect(extractTextFromComponents("Hello!")).toBe("Hello!");
    });

    it("extracts text from a top-level type: text component (legacy path)", () => {
        const components = [{ type: "text", content: "Hello, world!" }];
        expect(extractTextFromComponents(components)).toBe("Hello, world!");
    });

    it("extracts text from a paragraph component (greeting case that previously fell through)", () => {
        const components = [{ type: "paragraph", content: "Hi! How can I help today?" }];
        expect(extractTextFromComponents(components)).toBe("Hi! How can I help today?");
    });

    it("extracts text from an alert component using the `message` field", () => {
        const components = [{ type: "alert", message: "Heads up — search ran." }];
        expect(extractTextFromComponents(components)).toBe("Heads up — search ran.");
    });

    it("recurses into card.children to find nested text", () => {
        const components = [{
            type: "card",
            children: [
                { type: "heading", content: "Results" },
                { type: "paragraph", content: "Found 3 items." },
            ],
        }];
        const out = extractTextFromComponents(components);
        expect(out).toContain("Results");
        expect(out).toContain("Found 3 items.");
    });

    it("falls back to a friendlier message when no text is found", () => {
        const components = [{ type: "chart", data: { x: [1, 2, 3] } }];
        expect(extractTextFromComponents(components)).toBe("(No text content in this response.)");
    });

    it("handles a single component object (not wrapped in an array)", () => {
        const single = { type: "paragraph", content: "single component reply" };
        expect(extractTextFromComponents(single)).toBe("single component reply");
    });

    it("preserves multiple text pieces with double newlines between them", () => {
        const components = [
            { type: "text", content: "Line A" },
            { type: "paragraph", content: "Line B" },
        ];
        expect(extractTextFromComponents(components)).toBe("Line A\n\nLine B");
    });

    it("ignores empty / whitespace-only payloads when computing the fallback", () => {
        const components = [{ type: "text", content: "   " }];
        expect(extractTextFromComponents(components)).toBe("(No text content in this response.)");
    });
});
