/**
 * T042 — LlmConfigForm smoke render test.
 *
 * The form's stateful behaviour (gating Save until probe passes,
 * surfacing upstream error messages, etc.) is exercised end-to-end
 * by the hook tests (llm_config_hook.test.tsx) which cover the
 * underlying useLlmConfig contract. Here we only assert the
 * component mounts without throwing and renders the expected
 * controls — sufficient to catch a regression in the JSX or imports.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import LlmConfigForm from "../components/llm/LlmConfigForm";

// Mock the specific Lucide icons the form imports — using a Proxy
// previously caused vitest pre-bundling to hang.
vi.mock("lucide-react", () => ({
    Eye: () => <span data-testid="icon-eye" />,
    EyeOff: () => <span data-testid="icon-eye-off" />,
    Loader2: () => <span data-testid="icon-loader" />,
    CheckCircle2: () => <span data-testid="icon-check" />,
    AlertCircle: () => <span data-testid="icon-alert" />,
    Save: () => <span data-testid="icon-save" />,
    Beaker: () => <span data-testid="icon-beaker" />,
}));

describe("LlmConfigForm — smoke render", () => {
    it("renders three inputs and the action buttons", () => {
        window.localStorage.clear();
        render(<LlmConfigForm accessToken="dev-token" />);
        expect(screen.getByPlaceholderText("sk-…")).toBeTruthy();
        expect(screen.getByDisplayValue("https://api.openai.com/v1")).toBeTruthy();
        expect(screen.getByDisplayValue("gpt-4o-mini")).toBeTruthy();
        expect(screen.getByRole("button", { name: /test connection/i })).toBeTruthy();
        expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy();
    });

    it("renders the privacy notice", () => {
        window.localStorage.clear();
        render(<LlmConfigForm accessToken="dev-token" />);
        expect(
            screen.getByText(/Your API key lives only on this device/i),
        ).toBeTruthy();
    });

    it("Test Connection is disabled while a field is empty", () => {
        window.localStorage.clear();
        render(<LlmConfigForm accessToken="dev-token" />);
        // apiKey is empty by default → Test Connection disabled
        const testBtn = screen.getByRole("button", { name: /test connection/i });
        expect((testBtn as HTMLButtonElement).disabled).toBe(true);
    });

    it("Save is disabled by default (no probe has passed)", () => {
        window.localStorage.clear();
        render(<LlmConfigForm accessToken="dev-token" />);
        const saveBtn = screen.getByRole("button", { name: /^save$/i });
        expect((saveBtn as HTMLButtonElement).disabled).toBe(true);
    });

    it("renders Clear button when a config is already saved", () => {
        window.localStorage.setItem(
            "astralbody.llm.config.v1",
            JSON.stringify({
                apiKey: "sk-prior",
                baseUrl: "https://x/v1",
                model: "m",
                connectedAt: null,
                schemaVersion: 1,
            }),
        );
        render(<LlmConfigForm accessToken="dev-token" />);
        expect(screen.getByRole("button", { name: /clear configuration/i })).toBeTruthy();
        window.localStorage.clear();
    });
});
