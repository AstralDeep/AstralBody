/**
 * Client-side allow-list, size caps, and validation messages for file uploads.
 *
 * Mirrors the server-side allow-list in
 * `backend/orchestrator/attachments/content_type.py`. The two MUST stay in
 * sync — drift would either cause the composer to send files the server
 * rejects, or block files the server would have accepted.
 *
 * Feature: 002-file-uploads.
 */

export type AttachmentCategory =
  | "document"
  | "spreadsheet"
  | "presentation"
  | "text"
  | "image"
  | "medical";

export type AttachmentErrorCode = "unsupported" | "oversize" | "network";

export interface AttachmentError {
  code: AttachmentErrorCode;
  message: string;
}

const _COMPOUND_EXTENSIONS = ["nii.gz", "ome.tif", "ome.tiff"] as const;

export const ACCEPTED_EXTENSIONS: Record<string, AttachmentCategory> = {
  // Documents
  pdf: "document",
  docx: "document",
  doc: "document",
  rtf: "document",
  odt: "document",
  // Spreadsheets
  xlsx: "spreadsheet",
  xls: "spreadsheet",
  ods: "spreadsheet",
  tsv: "spreadsheet",
  csv: "spreadsheet",
  // Presentations
  pptx: "presentation",
  ppt: "presentation",
  odp: "presentation",
  // Structured text & config
  txt: "text",
  md: "text",
  json: "text",
  yaml: "text",
  yml: "text",
  xml: "text",
  html: "text",
  htm: "text",
  log: "text",
  // Code
  py: "text",
  js: "text",
  ts: "text",
  tsx: "text",
  jsx: "text",
  sql: "text",
  sh: "text",
  ps1: "text",
  css: "text",
  // Images
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  webp: "image",
  // Medical imaging
  dcm: "medical",
  dicom: "medical",
  nii: "medical",
  "nii.gz": "medical",
  czi: "medical",
  nrrd: "medical",
  mha: "medical",
  mhd: "medical",
  raw: "medical",
  "ome.tif": "medical",
  "ome.tiff": "medical",
  tif: "medical",
  tiff: "medical",
  svs: "medical",
  ndpi: "medical",
};

const MB = 1024 * 1024;
const GB = 1024 * MB;

export const MAX_BYTES_BY_CATEGORY: Record<AttachmentCategory, number> = {
  document: 30 * MB,
  spreadsheet: 30 * MB,
  presentation: 30 * MB,
  text: 30 * MB,
  image: 30 * MB,
  medical: 2 * GB,
};

/** Lower-cased extension for `filename`, no leading dot. Recognises `.nii.gz` etc. */
export function extensionOf(filename: string): string {
  const lower = filename.toLowerCase();
  for (const compound of _COMPOUND_EXTENSIONS) {
    if (lower.endsWith("." + compound)) return compound;
  }
  const dot = lower.lastIndexOf(".");
  return dot === -1 ? "" : lower.slice(dot + 1);
}

/** Category for `filename`, or `undefined` if its extension isn't accepted. */
export function categoryOf(filename: string): AttachmentCategory | undefined {
  return ACCEPTED_EXTENSIONS[extensionOf(filename)];
}

/** Upload-size cap for the file's category, falling back to the strictest known cap. */
export function maxBytesFor(filename: string): number {
  const cat = categoryOf(filename);
  if (cat) return MAX_BYTES_BY_CATEGORY[cat];
  return Math.min(...Object.values(MAX_BYTES_BY_CATEGORY));
}

function formatMb(bytes: number): string {
  if (bytes >= GB) return `${(bytes / GB).toFixed(0)} GB`;
  return `${Math.round(bytes / MB)} MB`;
}

/** Build a user-facing `AttachmentError` for a rejected or failed upload. */
export function rejectionMessage(
  filename: string,
  code: AttachmentErrorCode,
  detail?: string,
): AttachmentError {
  let message: string;
  switch (code) {
    case "unsupported": {
      const ext = extensionOf(filename) || "(no extension)";
      message = `${filename}: .${ext} files aren't supported.`;
      break;
    }
    case "oversize": {
      const cap = formatMb(maxBytesFor(filename));
      message = detail
        ? `${filename}: file is too large (${detail}, max ${cap}).`
        : `${filename}: file is too large (max ${cap}).`;
      break;
    }
    case "network":
    default:
      message = detail
        ? `${filename}: upload failed (${detail}).`
        : `${filename}: upload failed.`;
      break;
  }
  return { code, message };
}

/** Comma-separated `.ext` list suitable for an `<input type="file" accept=...>`. */
export const ACCEPT_ATTRIBUTE: string = Object.keys(ACCEPTED_EXTENSIONS)
  .map((ext) => "." + ext)
  .join(",");
