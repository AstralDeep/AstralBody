/**
 * Tests for the AttachmentLibrary panel.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import AttachmentLibrary from "../components/AttachmentLibrary";
import type { UseAttachmentsAPI, UploadedAttachment } from "../hooks/useAttachments";

function makeApi(items: UploadedAttachment[]): UseAttachmentsAPI {
  return {
    pending: [],
    upload: vi.fn(),
    remove: vi.fn(),
    retry: vi.fn(),
    attachExisting: vi.fn(),
    clear: vi.fn(),
    deleteServerSide: vi.fn(async () => true),
    listLibrary: vi.fn(async () => items),
  };
}

const sampleA: UploadedAttachment = {
  attachment_id: "a", filename: "report.pdf", category: "document",
  extension: "pdf", content_type: "application/pdf",
  size_bytes: 1024, sha256: "h", created_at: "2026-04-13T00:00:00Z",
};
const sampleB: UploadedAttachment = {
  attachment_id: "b", filename: "data.csv", category: "spreadsheet",
  extension: "csv", content_type: "text/csv",
  size_bytes: 200, sha256: "h", created_at: "2026-04-13T00:00:00Z",
};

describe("AttachmentLibrary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when closed", () => {
    const api = makeApi([sampleA]);
    render(<AttachmentLibrary api={api} open={false} />);
    expect(api.listLibrary).not.toHaveBeenCalled();
    expect(screen.queryByText("Your files")).toBeNull();
  });

  it("loads and lists the user's attachments grouped by category", async () => {
    const api = makeApi([sampleA, sampleB]);
    render(<AttachmentLibrary api={api} open={true} />);
    await waitFor(() => expect(api.listLibrary).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByText("data.csv")).toBeInTheDocument();
    expect(screen.getByText("Documents")).toBeInTheDocument();
    expect(screen.getByText("Spreadsheets")).toBeInTheDocument();
  });

  it("attaches a file to the current chat when the paperclip is clicked", async () => {
    const api = makeApi([sampleA]);
    const onAttach = vi.fn();
    render(<AttachmentLibrary api={api} open={true} onAttach={onAttach} />);
    await screen.findByText("report.pdf");
    const attachBtn = screen.getByTitle("Attach to current chat");
    fireEvent.click(attachBtn);
    expect(api.attachExisting).toHaveBeenCalledWith(sampleA);
    expect(onAttach).toHaveBeenCalledWith(sampleA);
  });

  it("deletes a file when the trash button is clicked", async () => {
    const api = makeApi([sampleA]);
    render(<AttachmentLibrary api={api} open={true} />);
    await screen.findByText("report.pdf");
    fireEvent.click(screen.getByTitle("Delete"));
    await waitFor(() => expect(api.deleteServerSide).toHaveBeenCalledWith("a"));
    await waitFor(() => expect(screen.queryByText("report.pdf")).toBeNull());
  });
});
