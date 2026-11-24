import { describe, expect, it } from "vitest";
import { canvasScale, MAX_PAGES } from "./original-pages";
import { attemptsNeedConfirmation, extractionBadge, extractionExplanation, UNKNOWN_IS_NOT_ZERO, type ExtractionLike } from "./pdf-extraction";

const base = { pages: 1, empty_pages: [] as number[] };
const native = (status: ExtractionLike["status"]): ExtractionLike => ({ engine: "poppler-text-v1", status, ...base });
const ocr = (status: ExtractionLike["status"]): ExtractionLike => ({ engine: "poppler-tesseract-v1", status, ...base });

describe("extraction states in plain language (spec 078)", () => {
  it("gives every state its own badge, distinguishing text from OCR", () => {
    const labels = [native("ready"), ocr("ready"), native("no_text"), native("unavailable"), native("encrypted"), native("invalid"), native("resource_limit")].map(extractionBadge);
    expect(new Set(labels).size).toBe(labels.length);
    expect(extractionBadge(undefined)).toBe("");
  });
  it("suggests OCR when there is no text, and says the original is kept", () => {
    const text = extractionExplanation(native("no_text"));
    expect(text).toContain("Run OCR");
    expect(text).toContain("original is kept");
  });
  it("says an unavailable parser is offline, the original is kept and what to do", () => {
    const text = extractionExplanation(native("unavailable"));
    expect(text).toContain("offline");
    expect(text).toContain("original is kept");
    expect(text).toContain("pdf-worker start");
    expect(text).toContain("Re-extract");
    expect(text).toContain("adds a version");
  });
  it("says OCR is uncertain, that a line can be missing and that nothing is claimed accurate", () => {
    const text = extractionExplanation(ocr("ready"));
    expect(text).toContain("a line can be missing");
    expect(text).toContain("Unknown");
    expect(text.toLowerCase()).not.toMatch(/accurate|accuracy|verified|confinement/);
  });
  it("never calls an offline or empty state failed or lost", () => {
    for (const status of ["unavailable", "no_text"] as const) {
      expect(extractionExplanation(native(status)).toLowerCase()).not.toMatch(/\bfailed\b|\bis lost\b|(?<!nothing )\bwas lost\b/);
    }
  });
  it("guards repeated attempts only while the reader is unavailable, never hiding the state", () => {
    expect(attemptsNeedConfirmation(native("unavailable"))).toBe(true);
    expect(attemptsNeedConfirmation(ocr("unavailable"))).toBe(true);
    expect(attemptsNeedConfirmation(native("ready"))).toBe(false);
    expect(attemptsNeedConfirmation(native("no_text"))).toBe(false);
    expect(attemptsNeedConfirmation(undefined)).toBe(false);
  });
  it("states that Unknown is not zero", () => {
    expect(UNKNOWN_IS_NOT_ZERO).toContain("Unknown is not zero");
    expect(UNKNOWN_IS_NOT_ZERO).toContain("never treated as 0.00");
  });
  it("caps the pages drawn at 3 and bounds the canvas size however large the page claims to be", () => {
    expect(MAX_PAGES).toBe(3);
    const scale = canvasScale(100000, 100000, 600, 2);
    expect(100000 * scale * 100000 * scale).toBeLessThanOrEqual(4_000_000 + 1);
    expect(canvasScale(612, 792, 600, 1)).toBeGreaterThan(0.9);
  });
});
