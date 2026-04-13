/**
 * Tests for useAttachments hook (feature 002-file-uploads).
 *
 * Covers: validation, multi-file upload, error states, retry, remove,
 * and library / cross-chat reuse.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useAttachments } from "../hooks/useAttachments";

const mockFetch = window.fetch as unknown as ReturnType<typeof vi.fn>;

function fakeFile(name: string, size = 100, type = "text/plain"): File {
  const file = new File(["x".repeat(size)], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("useAttachments", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("rejects unsupported extensions before sending any request", async () => {
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    await act(async () => {
      await result.current.upload([fakeFile("blueprint.dwg")]);
    });
    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.pending).toHaveLength(1);
    expect(result.current.pending[0].status).toBe("error");
    expect(result.current.pending[0].error?.code).toBe("unsupported");
  });

  it("rejects oversize files before sending any request", async () => {
    const big = fakeFile("huge.pdf", 40 * 1024 * 1024);
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    await act(async () => {
      await result.current.upload([big]);
    });
    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.pending[0].error?.code).toBe("oversize");
  });

  it("uploads a valid file and stages the resulting attachment", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({
      attachment_id: "id-1",
      filename: "notes.md",
      category: "text",
      extension: "md",
      content_type: "text/markdown",
      size_bytes: 5,
      sha256: "abc",
      created_at: "2026-04-13T12:00:00Z",
    }, 201));
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    await act(async () => {
      await result.current.upload([fakeFile("notes.md")]);
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(result.current.pending[0].status).toBe("ready");
    expect(result.current.pending[0].attachment?.attachment_id).toBe("id-1");
  });

  it("uploads multiple files in one call and stages each result", async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse({
        attachment_id: "id-A", filename: "a.txt", category: "text",
        extension: "txt", content_type: "text/plain", size_bytes: 3,
        sha256: "h", created_at: "x",
      }, 201))
      .mockResolvedValueOnce(jsonResponse({
        attachment_id: "id-B", filename: "b.csv", category: "spreadsheet",
        extension: "csv", content_type: "text/csv", size_bytes: 4,
        sha256: "h", created_at: "x",
      }, 201));
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    await act(async () => {
      await result.current.upload([fakeFile("a.txt"), fakeFile("b.csv")]);
    });
    expect(result.current.pending).toHaveLength(2);
    expect(result.current.pending.every((p) => p.status === "ready")).toBe(true);
  });

  it("surfaces a 413 response as an oversize error message", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: "too big" }, 413));
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    await act(async () => {
      await result.current.upload([fakeFile("a.txt")]);
    });
    expect(result.current.pending[0].status).toBe("error");
    expect(result.current.pending[0].error?.code).toBe("oversize");
  });

  it("surfaces network failures and supports retry", async () => {
    mockFetch.mockRejectedValueOnce(new Error("offline"));
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    await act(async () => {
      await result.current.upload([fakeFile("a.txt")]);
    });
    expect(result.current.pending[0].status).toBe("error");
    expect(result.current.pending[0].error?.code).toBe("network");

    // Retry — the next attempt succeeds.
    mockFetch.mockResolvedValueOnce(jsonResponse({
      attachment_id: "id-retry", filename: "a.txt", category: "text",
      extension: "txt", content_type: "text/plain", size_bytes: 3,
      sha256: "h", created_at: "x",
    }, 201));
    const localId = result.current.pending[0].localId;
    await act(async () => {
      await result.current.retry(localId);
    });
    await waitFor(() => expect(result.current.pending[0].status).toBe("ready"));
  });

  it("removes a slot without affecting other slots", async () => {
    mockFetch.mockResolvedValue(jsonResponse({
      attachment_id: "x", filename: "a.txt", category: "text", extension: "txt",
      content_type: "text/plain", size_bytes: 1, sha256: "h", created_at: "x",
    }, 201));
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    await act(async () => {
      await result.current.upload([fakeFile("a.txt"), fakeFile("b.txt")]);
    });
    const idToRemove = result.current.pending[0].localId;
    act(() => result.current.remove(idToRemove));
    expect(result.current.pending).toHaveLength(1);
    expect(result.current.pending[0].filename).toBe("b.txt");
  });

  it("listLibrary returns the user's attachments", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({
      attachments: [{
        attachment_id: "lib-1", filename: "old.pdf", category: "document",
        extension: "pdf", content_type: "application/pdf",
        size_bytes: 100, sha256: "h", created_at: "x",
      }],
      next_cursor: null,
    }));
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    let items: Awaited<ReturnType<typeof result.current.listLibrary>> = [];
    await act(async () => {
      items = await result.current.listLibrary();
    });
    expect(items).toHaveLength(1);
    expect(items[0].filename).toBe("old.pdf");
  });

  it("attachExisting stages a server-side attachment without re-upload", async () => {
    const { result } = renderHook(() => useAttachments({ accessToken: "tok" }));
    act(() =>
      result.current.attachExisting({
        attachment_id: "lib-1", filename: "old.pdf", category: "document",
        extension: "pdf", content_type: "application/pdf",
        size_bytes: 100, sha256: "h", created_at: "x",
      }),
    );
    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.pending[0].status).toBe("ready");
  });
});
