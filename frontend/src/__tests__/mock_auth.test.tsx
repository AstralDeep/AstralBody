/**
 * Guards against drift in the VITE_USE_MOCK_AUTH identity.
 *
 * When mock auth is enabled, the frontend must hand out a user whose
 * identity is `test_user` with roles [admin, user]. This is contract
 * with the backend mock auth path — if the frontend changes the user
 * identity without updating backend/shared/a2a_security.py and
 * backend/orchestrator/auth.py, chats/agents will be silently scoped
 * to a different user than expected.
 */
import { describe, it, expect } from "vitest";
import { render, act } from "@testing-library/react";
import { MockAuthProvider, useMockAuth } from "../contexts/MockAuthContext";

function decodeJwtPayload(token: string): Record<string, unknown> {
  const base64Url = token.split(".")[1];
  let base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
  const pad = 4 - (base64.length % 4);
  if (pad < 4) base64 += "=".repeat(pad);
  return JSON.parse(atob(base64));
}

function Probe({ onReady }: { onReady: (v: ReturnType<typeof useMockAuth>) => void }) {
  const auth = useMockAuth();
  onReady(auth);
  return null;
}

describe("MockAuthProvider identity", () => {
  it("exposes a test_user with admin and user roles", () => {
    let captured: ReturnType<typeof useMockAuth> | null = null;
    act(() => {
      render(
        <MockAuthProvider>
          <Probe onReady={(v) => { captured = v; }} />
        </MockAuthProvider>
      );
    });

    expect(captured).not.toBeNull();
    expect(captured!.isAuthenticated).toBe(true);
    expect(captured!.user).not.toBeNull();
    expect(captured!.user!.user_id).toBe("test_user");
    expect(captured!.user!.profile.preferred_username).toBe("test_user");

    const payload = decodeJwtPayload(captured!.user!.access_token) as {
      sub: string;
      preferred_username: string;
      realm_access: { roles: string[] };
    };
    expect(payload.sub).toBe("test_user");
    expect(payload.preferred_username).toBe("test_user");
    expect(payload.realm_access.roles).toEqual(expect.arrayContaining(["admin", "user"]));
  });
});
