import type { DigestReview } from "./discovery-digest-api";
import { DigestError } from "./discovery-digest-api";
import { choices, isIdea } from "./discovery-api";
import { markdownText } from "./work-meeting-markdown";
import { memoryScopes } from "./memory-api";

export function digestTitle(value: string): string {
  const title = value.trim();
  if (!title || title.length > 120 || /[\x00-\x1f\x7f]/.test(value)) throw new DigestError("Use a single-line digest title of 1–120 characters.");
  return title;
}
/** Keep manually reported URLs inert even when they contain Markdown delimiters. */
export function literalCode(value: string): string {
  const longest = Math.max(0, ...[...value.matchAll(/`+/g)].map(match => match[0].length));
  const fence = "`".repeat(longest + 1);
  return `${fence} ${value} ${fence}`;
}
const labels = { benefit: "Expected benefit", privacy: "Privacy", maturity_license: "Maturity and license", hardware_cost: "Hardware and cost", alternatives_dependencies: "Alternatives and dependencies", experiment: "Proposed experiment" } as const;
export function digestMarkdown(review: DigestReview, annotation: string): { text: string; bytes: number; filename: string } {
  const title = digestTitle(annotation), b = review.bundle, items = b.items;
  const lines = ["# Selected Discovery review digest", "", `Title: ${markdownText(title)}`, `Private access: ${markdownText(memoryScopes[b.scope])}`, `Prepared: ${b.prepared_at}`, `Export reference: \`${b.export_id}\``, `Review reference: \`${review.review_id}\``, `Coverage: ${items.length} explicitly selected records; this is not a complete inbox snapshot.`, `Copy expiry: ${b.retain_until ?? "No expiry stated - manage this copy yourself"}`, "", "The title is your browser annotation, not a signed business record. Sources are manually reported and have not been independently verified. No source is fetched, and interest does not authorize any action.", "This is a separate unmanaged copy. Butler cannot recall it after forgetting, expiry or revocation. The receipt records preparation, not file saving or deletion.", "", "## Selected overview", "", `Ideas without evidence: ${items.filter(isIdea).length}`, `Manually reported proposals: ${items.filter(item => !isIdea(item)).length}`, `Records with unassessed fields: ${items.filter(item => Object.keys(labels).some(key => ["Not assessed", "Not proposed"].includes(item.content[key as keyof typeof labels]))).length}`, ""];
  items.forEach((item, index) => {
    lines.push(`## [D${index+1}] ${markdownText(item.title)}`, "", `Stage: ${isIdea(item) ? "Idea - no evidence" : "Manually reported proposal"}`, `Topic: ${markdownText(item.content.topic)}`, `Interest: ${item.content.feedback?.choice ? markdownText(choices[item.content.feedback.choice]) : "No current interest recorded"}`, `Record assessment: ${item.assessment} (not source verification)`, "", markdownText(item.content.summary), "", "### Manually reported evidence", "");
    if (!item.content.evidence.length) lines.push("No evidence supplied. Observed date Unknown.", "");
    item.content.evidence.forEach((source, i) => lines.push(`- [D${index+1}-S${i+1}] ${markdownText(source.title)}`, `  - Reference: ${literalCode(source.url)}`, `  - Observed: ${source.observed_at}`, ""));
    for (const [key, label] of Object.entries(labels)) lines.push(`- ${label}: ${markdownText(item.content[key as keyof typeof labels])}`);
    if (item.content.feedback) lines.push(`- Feedback note: ${markdownText(item.content.feedback.note) || "None"}`, `- Feedback recorded: ${item.content.feedback.recorded_at}`);
    lines.push("", `Provenance [D${index+1}]: note \`${item.id}\`, revision ${item.revision}; owner \`${item.owner_id}\`.`, `Created: ${item.created_at}; updated: ${item.updated_at}`, `Source metadata: ${item.source_type} - ${markdownText(item.source_reference)}`, `Record expiry: ${item.expires_at ?? "No expiry stated"}`, "");
  });
  const text = lines.join("\n"), bytes = new TextEncoder().encode(text).length;
  if (bytes > 131072) throw new DigestError("This digest is too large. Select fewer records.");
  return { text, bytes, filename: `butler-discovery-${b.export_id}.md` };
}
