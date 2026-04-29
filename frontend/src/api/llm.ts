/**
 * REST client for the user-configurable LLM subscription endpoints
 * (feature 006-user-llm-config).
 *
 * Currently a single endpoint:
 *
 *   POST /api/llm/test  →  TestConnectionResponse
 *
 * The user's API key travels in the request body. It is NEVER stored
 * server-side; the orchestrator uses it transiently to construct a
 * one-shot OpenAI client, issues a max_tokens=1 chat-completions probe,
 * and returns the result. See specs/006-user-llm-config/contracts/rest-llm-test.md.
 */
import { API_URL } from "../config";

export interface TestConnectionRequest {
    api_key: string;
    base_url: string;
    model: string;
}

export type LlmTestErrorClass =
    | "auth_failed"
    | "model_not_found"
    | "transport_error"
    | "contract_violation"
    | "other";

export interface TestConnectionResponse {
    ok: boolean;
    model: string;
    probed_at: string;
    latency_ms: number | null;
    error_class: LlmTestErrorClass | null;
    upstream_message: string | null;
}

/**
 * Probe the user's prospective LLM configuration. Always resolves
 * (does not throw on `ok=false` — that's a probe result, not a request
 * failure). Throws only if THIS request itself failed (auth missing,
 * network error to OUR server, malformed body).
 */
export async function testLlmConnection(
    token: string,
    body: TestConnectionRequest,
): Promise<TestConnectionResponse> {
    const response = await fetch(`${API_URL}/api/llm/test`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`Test Connection request failed (${response.status}): ${text}`);
    }
    return await response.json();
}
