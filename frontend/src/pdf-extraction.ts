// Plain-language states for forwarded PDF originals (spec 078). Text only: the server state is unchanged.
// Honesty rules: a PDF with no text suggests OCR; an unavailable parser says it is offline, that the original is kept
// and what to do; OCR says that a line can be missing; nothing here claims OCR accuracy or verified confinement.
export type ExtractionLike = {
  engine: "poppler-text-v1" | "poppler-tesseract-v1";
  status: "ready" | "no_text" | "encrypted" | "invalid" | "resource_limit" | "unavailable";
  pages: number;
  empty_pages: number[];
};

export const UNKNOWN_IS_NOT_ZERO =
  "Unknown is not zero: a field you leave Unknown stays Unknown. It is never treated as 0.00, as unpaid or as a missing invoice, The filing ledger holds only the file's hash, size and logical path, never invoice values.";

export function isOcr(e: ExtractionLike): boolean {
  return e.engine === "poppler-tesseract-v1";
}

/** Short label for the document list. */
export function extractionBadge(e: ExtractionLike | undefined): string {
  if (!e) return "";
  switch (e.status) {
    case "ready": return isOcr(e) ? "OCR text (uncertain)" : "Text extracted";
    case "no_text": return "No text found";
    case "unavailable": return "Extraction unavailable";
    case "encrypted": return "Encrypted PDF";
    case "invalid": return "Unreadable PDF";
    case "resource_limit": return "Too large to read";
  }
}

/** What the owner should understand and do, per state. */
export function extractionExplanation(e: ExtractionLike): string {
  switch (e.status) {
    case "ready":
      return isOcr(e)
        ? "OCR recognition is uncertain. Verify every name, number and date against the original before review. A line can be missing: text that is blurred or faint may be dropped without any warning, and the status still says ready. Compare every name, number and date with the original (use View original pages), and leave a field Unknown if you cannot confirm it."
        : "Extraction can omit images or reading order. Check the original before reviewing.";
    case "no_text":
      return "No text was found in this PDF. It looks like a scan or an image. Run OCR (up to 2 pages), then compare the result with the original. The original is kept either way.";
    case "unavailable":
      return "The PDF reader is offline, so nothing could be read. The original is kept safely and nothing was lost. Start the PDF worker (bash scripts/mvp01-owner.sh pdf-worker start), then use Re-extract PDF text. Each attempt while it is offline adds a version of this document and requires a new review.";
    case "encrypted":
      return "This PDF is encrypted, so it cannot be read here. The original is kept.";
    case "invalid":
      return "This PDF could not be read as a valid document. The original is kept.";
    case "resource_limit":
      return "This PDF is larger than the local reader accepts. The original is kept and nothing was cut off silently.";
  }
}

/** Repeated attempts while the reader is offline each create a version; a UI-only guard asks the owner to confirm first. */
export function attemptsNeedConfirmation(e: ExtractionLike | undefined): boolean {
  return e?.status === "unavailable";
}
