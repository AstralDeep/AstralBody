/**
 * normalizeLlmMarkdown — Preprocess LLM markdown output before passing to ReactMarkdown.
 *
 * Different LLMs produce markdown with different quirks. Gemma in particular:
 *   1. Uses 4-space indentation for "list" items instead of `-` / `*` markers,
 *      which CommonMark parses as indented code blocks (gray monospace boxes).
 *   2. Sometimes echoes raw UI-component JSON (e.g. `[{"type":"card",...}]`)
 *      inline in its narrative, even though the orchestrator already rendered
 *      the structured payload on the canvas.
 *
 * This module runs three passes in order:
 *   A. stripUiComponentJson    — remove leaked component JSON spans
 *   B. bulletizeIndentedBlocks — convert pseudo-indented lists to real bullets
 *   C. normalizeLatexDelimiters — `\[ \]` → `$$ $$`, `\( \)` → `$ $`
 *
 * Pure function, no React/DOM dependencies, safe to unit test.
 */

const CODE_HEURISTIC = /[{};]|=>|^\s*(?:def|class|function|import|const|let|var)\s/;
const FENCE_RE = /^(?:```|~~~)/;
// Matches start of a suspected UI-component JSON span: optional `[`, `{`, then `"type"`.
const JSON_START_RE = /\[\s*\{\s*"type"\s*:|\{\s*"type"\s*:/;

/**
 * Pass A: Strip balanced JSON spans that look like UI-component payloads.
 *
 * Uses a hand-rolled bracket scanner that respects string literals so quoted
 * `]` / `}` characters don't break balancing.
 */
export function stripUiComponentJson(input: string): string {
    let out = "";
    let i = 0;
    while (i < input.length) {
        // Try to match a JSON-component start at position i.
        const rest = input.slice(i);
        const match = rest.match(JSON_START_RE);
        if (!match || match.index !== 0) {
            out += input[i];
            i++;
            continue;
        }

        // Found a candidate at position i. Walk forward, balancing brackets.
        let depth = 0;
        let inString = false;
        let escaped = false;
        let end = -1;
        for (let j = i; j < input.length; j++) {
            const ch = input[j];
            if (inString) {
                if (escaped) {
                    escaped = false;
                } else if (ch === "\\") {
                    escaped = true;
                } else if (ch === '"') {
                    inString = false;
                }
                continue;
            }
            if (ch === '"') {
                inString = true;
                continue;
            }
            if (ch === "{" || ch === "[") {
                depth++;
            } else if (ch === "}" || ch === "]") {
                depth--;
                if (depth === 0) {
                    end = j;
                    break;
                }
                if (depth < 0) {
                    // Unbalanced — bail out, treat as plain text.
                    end = -1;
                    break;
                }
            }
        }

        if (end === -1) {
            // Couldn't balance — leave the original character and move on.
            out += input[i];
            i++;
            continue;
        }

        // Replace the matched span with a single newline so surrounding paragraphs
        // remain separated.
        out += "\n";
        i = end + 1;
    }
    return out;
}

/**
 * Pass B: Convert runs of 4-space-indented lines (which CommonMark would parse
 * as indented code blocks) into bullet list items, unless the content looks
 * like real code or is inside a fenced block.
 */
export function bulletizeIndentedBlocks(input: string): string {
    const lines = input.split("\n");
    const result: string[] = [];
    let inFence = false;
    let prevBlank = true; // Treat start-of-input as if preceded by blank line.

    let i = 0;
    while (i < lines.length) {
        const line = lines[i];

        if (FENCE_RE.test(line)) {
            inFence = !inFence;
            result.push(line);
            prevBlank = false;
            i++;
            continue;
        }

        if (inFence) {
            result.push(line);
            prevBlank = false;
            i++;
            continue;
        }

        // Look for the start of an indented-code-block run: must be preceded by
        // a blank line and the current line must start with 4+ spaces.
        if (prevBlank && /^ {4}/.test(line)) {
            // Collect the run of indented + blank lines.
            const runStart = i;
            const run: string[] = [];
            while (i < lines.length) {
                const l = lines[i];
                if (FENCE_RE.test(l)) break;
                if (l === "" || /^ {4}/.test(l)) {
                    run.push(l);
                    i++;
                } else {
                    break;
                }
            }
            // Trim trailing blanks from the run; they go back into the output as-is.
            let trailingBlanks = 0;
            while (run.length > 0 && run[run.length - 1] === "") {
                run.pop();
                trailingBlanks++;
            }

            const looksLikeCode = run.some(
                (l) => l !== "" && CODE_HEURISTIC.test(l.replace(/^ {4}/, "")),
            );

            if (looksLikeCode || run.length === 0) {
                // Leave the original lines untouched.
                for (let k = runStart; k < runStart + run.length; k++) {
                    result.push(lines[k]);
                }
            } else {
                for (const l of run) {
                    if (l === "") {
                        result.push("");
                    } else {
                        result.push(`- ${l.replace(/^ {4}/, "")}`);
                    }
                }
            }
            for (let k = 0; k < trailingBlanks; k++) {
                result.push("");
            }
            prevBlank = trailingBlanks > 0;
            continue;
        }

        result.push(line);
        prevBlank = line === "";
        i++;
    }

    return result.join("\n");
}

/**
 * Pass C: Translate LaTeX delimiters into the dollar-sign form that
 * remark-math understands natively.
 *
 * Note: in JS replacement strings, `$$` is the escape sequence for a single
 * literal `$`. To produce `$$` in the output we must write `$$$$`. The
 * original inline code in DynamicRenderer had this wrong, which is why
 * display-math `\[ ... \]` was collapsing to inline `$ ... $`.
 */
export function normalizeLatexDelimiters(input: string): string {
    return input
        .replace(/\\\[/g, "$$$$")
        .replace(/\\\]/g, "$$$$")
        .replace(/\\\(/g, "$$")
        .replace(/\\\)/g, "$$");
}

export function normalizeLlmMarkdown(input: string): string {
    if (typeof input !== "string" || input.length === 0) return input ?? "";
    const a = stripUiComponentJson(input);
    const b = bulletizeIndentedBlocks(a);
    const c = normalizeLatexDelimiters(b);
    return c;
}
