/**
 * useAttachments — chat composer state for uploaded files.
 *
 * Owns:
 *  - the list of attachments staged on the next message ("pending"),
 *  - upload + remove actions against the server's /api/upload + /api/attachments,
 *  - validation against the shared client allow-list and 30 MB cap,
 *  - per-attachment retryable error state.
 *
 * Feature: 002-file-uploads (US1 + US2 + US4).
 */
import { useCallback, useState } from "react";
import { BFF_URL } from "../config";
import {
  ACCEPTED_EXTENSIONS,
  MAX_FILE_BYTES,
  extensionOf,
  rejectionMessage,
} from "../lib/attachmentTypes";
import type { AttachmentCategory, AttachmentError } from "../lib/attachmentTypes";

/** Server-side response shape for `POST /api/upload`. */
export interface UploadedAttachment {
  attachment_id: string;
  filename: string;
  category: AttachmentCategory;
  extension: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

/** Local pending-attachment state used by the composer. */
export interface PendingAttachment {
  /** Stable client id for this composer slot (separate from attachment_id). */
  localId: string;
  filename: string;
  status: "uploading" | "ready" | "error";
  /** Set once the server responds 201. */
  attachment: UploadedAttachment | null;
  /** Set on validation or upload failure. */
  error: AttachmentError | null;
  /** Original File reference, retained so retry can re-POST. */
  source: File | null;
}

export interface UseAttachmentsAPI {
  pending: PendingAttachment[];
  /** Validate, upload, and stage one or more files. */
  upload: (files: File[] | FileList) => Promise<void>;
  /** Remove a pending slot (does NOT delete the server-side attachment). */
  remove: (localId: string) => void;
  /** Re-attempt a previously failed upload. */
  retry: (localId: string) => Promise<void>;
  /** Stage an existing server-side attachment (e.g., from the AttachmentLibrary). */
  attachExisting: (a: UploadedAttachment) => void;
  /** Clear all pending slots (call after the message is sent). */
  clear: () => void;
  /** Hard-delete an attachment server-side via DELETE /api/attachments/{id}. */
  deleteServerSide: (attachmentId: string) => Promise<boolean>;
  /** Fetch the user's attachment library. */
  listLibrary: (category?: AttachmentCategory) => Promise<UploadedAttachment[]>;
}

function newLocalId(): string {
  // crypto.randomUUID is available in modern browsers; small fallback for tests.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `local-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function authHeaders(token?: string): HeadersInit {
  const h: Record<string, string> = {};
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

/** Validate a single file before sending it across the wire. */
function validate(file: File): AttachmentError | null {
  const ext = extensionOf(file.name);
  if (!ACCEPTED_EXTENSIONS[ext]) {
    return rejectionMessage(file.name, "unsupported");
  }
  if (file.size > MAX_FILE_BYTES) {
    return rejectionMessage(
      file.name,
      "oversize",
      `${(file.size / (1024 * 1024)).toFixed(1)} MB`,
    );
  }
  return null;
}

/**
 * Hook factory. The returned API is referentially stable per render — callers
 * should treat it as a snapshot and re-read on each render to see fresh state.
 */
export function useAttachments(opts: { accessToken?: string }): UseAttachmentsAPI {
  const { accessToken } = opts;
  const [pending, setPending] = useState<PendingAttachment[]>([]);

  /** Patch a single slot by localId. */
  const patch = useCallback(
    (localId: string, patcher: (p: PendingAttachment) => PendingAttachment) => {
      setPending((cur) => cur.map((p) => (p.localId === localId ? patcher(p) : p)));
    },
    [],
  );

  const performUpload = useCallback(
    async (slot: PendingAttachment): Promise<void> => {
      if (!slot.source) return;
      const fd = new FormData();
      fd.append("file", slot.source);
      try {
        const res = await fetch(`${BFF_URL}/api/upload`, {
          method: "POST",
          headers: authHeaders(accessToken),
          body: fd,
        });
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            if (body && body.detail) detail = String(body.detail);
          } catch {
            /* ignore */
          }
          const code =
            res.status === 413 ? "oversize" :
            res.status === 415 ? "unsupported" :
            "network";
          patch(slot.localId, (p) => ({
            ...p,
            status: "error",
            attachment: null,
            error: rejectionMessage(slot.filename, code, detail),
          }));
          return;
        }
        const body: UploadedAttachment = await res.json();
        patch(slot.localId, (p) => ({
          ...p,
          status: "ready",
          attachment: body,
          error: null,
        }));
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        patch(slot.localId, (p) => ({
          ...p,
          status: "error",
          attachment: null,
          error: rejectionMessage(slot.filename, "network", msg),
        }));
      }
    },
    [accessToken, patch],
  );

  const upload = useCallback(
    async (files: File[] | FileList): Promise<void> => {
      const fileArray = Array.from(files);
      const slots: PendingAttachment[] = fileArray.map((file) => {
        const validationErr = validate(file);
        return {
          localId: newLocalId(),
          filename: file.name,
          status: validationErr ? "error" : "uploading",
          attachment: null,
          error: validationErr,
          source: validationErr ? null : file,
        };
      });
      setPending((cur) => [...cur, ...slots]);
      await Promise.all(
        slots
          .filter((s) => s.status === "uploading")
          .map((s) => performUpload(s)),
      );
    },
    [performUpload],
  );

  const remove = useCallback((localId: string) => {
    setPending((cur) => cur.filter((p) => p.localId !== localId));
  }, []);

  const retry = useCallback(
    async (localId: string): Promise<void> => {
      const target = pending.find((p) => p.localId === localId);
      if (!target || !target.source) return;
      patch(localId, (p) => ({ ...p, status: "uploading", error: null }));
      await performUpload({ ...target, status: "uploading", error: null });
    },
    [pending, patch, performUpload],
  );

  const attachExisting = useCallback((a: UploadedAttachment) => {
    setPending((cur) => [
      ...cur,
      {
        localId: newLocalId(),
        filename: a.filename,
        status: "ready",
        attachment: a,
        error: null,
        source: null,
      },
    ]);
  }, []);

  const clear = useCallback(() => setPending([]), []);

  const deleteServerSide = useCallback(
    async (attachmentId: string): Promise<boolean> => {
      try {
        const res = await fetch(`${BFF_URL}/api/attachments/${attachmentId}`, {
          method: "DELETE",
          headers: authHeaders(accessToken),
        });
        return res.ok;
      } catch {
        return false;
      }
    },
    [accessToken],
  );

  const listLibrary = useCallback(
    async (category?: AttachmentCategory): Promise<UploadedAttachment[]> => {
      const url = new URL(`${BFF_URL}/api/attachments`);
      if (category) url.searchParams.set("category", category);
      try {
        const res = await fetch(url.toString(), { headers: authHeaders(accessToken) });
        if (!res.ok) return [];
        const body = await res.json();
        return Array.isArray(body.attachments) ? body.attachments : [];
      } catch {
        return [];
      }
    },
    [accessToken],
  );

  return {
    pending,
    upload,
    remove,
    retry,
    attachExisting,
    clear,
    deleteServerSide,
    listLibrary,
  };
}

/**
 * Build the bracketed reference string the agent will see in the user message
 * for each ready attachment. Format kept stable across versions:
 *
 *   [Attachment: filename.pdf (document) — id=<uuid>]
 *
 * The orchestrator/agent does not parse this strictly; it's a hint the LLM uses
 * to call `read_document` etc. with the right `attachment_id`.
 */
export function formatAttachmentRefs(pending: PendingAttachment[]): string {
  const lines: string[] = [];
  for (const p of pending) {
    if (p.status === "ready" && p.attachment) {
      lines.push(
        `[Attachment: ${p.attachment.filename} (${p.attachment.category}) — id=${p.attachment.attachment_id}]`,
      );
    }
  }
  return lines.join("\n");
}
