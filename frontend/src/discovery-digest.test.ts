import { expect, it } from "vitest";
import { digestMarkdown, digestTitle, literalCode } from "./discovery-digest";
import { parseDigest } from "./discovery-digest-api";
import { fixture, owner, record } from "./test-support/discovery-digest";
it("preserves current selected citations, unknowns, evidence/provenance and copy limits", () => {
  const { payload, request } = fixture(), value = parseDigest(payload, request, owner), result = digestMarkdown(value, " Sample digest ");
  expect(result.text).toContain("Title: Sample digest"); expect(result.text).toContain("[D1-S1]"); expect(result.text).toContain(`note \`${payload.bundle.items[0].id}\`, revision 1`); expect(result.text).toContain("Ideas without evidence: 1"); expect(result.text).toContain("Observed date Unknown"); expect(result.text).toContain("No expiry stated"); expect(result.text).toContain("not a complete inbox snapshot"); expect(result.text).toContain("No source is fetched"); expect(result.filename).toBe(`butler-discovery-${payload.bundle.export_id}.md`); expect(result.bytes).toBe(new TextEncoder().encode(result.text).length);
});
it("escapes dynamic Markdown/HTML and keeps references inside robust literal code spans", () => {
  const source = "https://example.org/``danger`<img>(x)", row = record(); row.content.evidence[0].url = source; row.title = "<script>_Synthetic_</script>";
  const { payload, request } = fixture([row]), result = digestMarkdown(parseDigest(payload, request, owner), "[Sample] _digest_");
  expect(result.text).toContain("Title: \\[Sample\\] \\_digest\\_"); expect(result.text).toContain("\\<script\\>"); expect(result.text).toContain("Reference: ``` " + source + " ```"); expect(result.text).not.toContain("](" + source); expect(literalCode("https://example.org/a")).toBe("` https://example.org/a `");
});
it.each(["", "x".repeat(121), "line\nline", "\tTitle"])("rejects invalid local annotations %s", title => { expect(() => digestTitle(title)).toThrow(); });
it("refuses oversized Markdown without truncating sources", () => {
  const { payload, request } = fixture(), value = parseDigest(payload, request, owner); value.bundle.items = Array.from({ length: 10 }, (_, n) => { const row = record(n + 1); row.content.summary = "_".repeat(1000); row.content.evidence = Array.from({ length: 5 }, () => ({ title: "_".repeat(160), url: "https://example.org/" + "`".repeat(450), observed_at: "2026-01-01T00:00:00Z" })); for (const key of ["benefit", "privacy", "maturity_license", "hardware_cost", "alternatives_dependencies"] as const) row.content[key] = "_".repeat(512); row.content.experiment = "_".repeat(1000); return row; }); expect(() => digestMarkdown(value, "Sample")).toThrow("too large");
});
