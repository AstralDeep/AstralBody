/**
 * AttachmentLibrary — panel listing the calling user's uploaded attachments
 * across all of their chats. From here the user can re-attach a file to the
 * current chat or delete it permanently.
 *
 * Feature: 002-file-uploads (FR-009 cross-chat).
 */
import { useCallback, useEffect, useState } from "react";
import { FileText, Image as ImageIcon, Sheet, Presentation, FileCode, Stethoscope, Trash2, Paperclip, Loader2 } from "lucide-react";
import type { AttachmentCategory } from "../lib/attachmentTypes";
import type { UseAttachmentsAPI, UploadedAttachment } from "../hooks/useAttachments";

const CATEGORY_LABEL: Record<AttachmentCategory, string> = {
  document: "Documents",
  spreadsheet: "Spreadsheets",
  presentation: "Presentations",
  text: "Text & Code",
  image: "Images",
  medical: "Medical imaging",
};

function CategoryIcon({ category }: { category: AttachmentCategory }) {
  switch (category) {
    case "document": return <FileText size={16} />;
    case "spreadsheet": return <Sheet size={16} />;
    case "presentation": return <Presentation size={16} />;
    case "image": return <ImageIcon size={16} />;
    case "text": return <FileCode size={16} />;
    case "medical": return <Stethoscope size={16} />;
  }
}

export interface AttachmentLibraryProps {
  api: UseAttachmentsAPI;
  /** Whether the panel is currently open. Drives the initial load. */
  open: boolean;
  /** Called after the user clicks "attach" on a row. */
  onAttach?: (attachment: UploadedAttachment) => void;
}

export default function AttachmentLibrary({
  api,
  open,
  onAttach,
}: AttachmentLibraryProps) {
  const [items, setItems] = useState<UploadedAttachment[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    const next = await api.listLibrary();
    setItems(next);
    setLoading(false);
  }, [api]);

  useEffect(() => {
    if (open) {
      void refresh();
    }
  }, [open, refresh]);

  const handleAttach = useCallback(
    (att: UploadedAttachment) => {
      api.attachExisting(att);
      onAttach?.(att);
    },
    [api, onAttach],
  );

  const handleDelete = useCallback(
    async (att: UploadedAttachment) => {
      const ok = await api.deleteServerSide(att.attachment_id);
      if (ok) {
        setItems((cur) => cur.filter((a) => a.attachment_id !== att.attachment_id));
      }
    },
    [api],
  );

  if (!open) return null;

  // Group by category in a stable order.
  const byCategory: Record<AttachmentCategory, UploadedAttachment[]> = {
    document: [], spreadsheet: [], presentation: [], text: [], image: [], medical: [],
  };
  for (const a of items) {
    byCategory[a.category]?.push(a);
  }
  const orderedCategories: AttachmentCategory[] = [
    "document", "spreadsheet", "presentation", "text", "image", "medical",
  ];

  return (
    <div className="border border-white/10 rounded-xl bg-astral-surface/60 p-3 max-h-[60vh] overflow-y-auto">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-white">Your files</h3>
        {loading && <Loader2 size={16} className="animate-spin text-astral-muted" />}
      </div>

      {!loading && items.length === 0 && (
        <p className="text-xs text-astral-muted">
          You haven't uploaded any files yet. Use the paperclip to attach one.
        </p>
      )}

      {orderedCategories.map((cat) => {
        const list = byCategory[cat];
        if (!list.length) return null;
        return (
          <section key={cat} className="mb-3">
            <h4 className="text-xs uppercase tracking-wide text-astral-muted mb-1">
              {CATEGORY_LABEL[cat]}
            </h4>
            <ul className="space-y-1">
              {list.map((att) => (
                <li
                  key={att.attachment_id}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/5 text-sm"
                >
                  <span className="text-astral-muted">
                    <CategoryIcon category={att.category} />
                  </span>
                  <span className="flex-1 truncate text-white" title={att.filename}>
                    {att.filename}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleAttach(att)}
                    className="p-1 rounded-md hover:bg-white/10 text-astral-primary"
                    title="Attach to current chat"
                  >
                    <Paperclip size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(att)}
                    className="p-1 rounded-md hover:bg-red-500/15 text-red-400"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
