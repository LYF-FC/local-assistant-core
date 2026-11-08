/** A visible editable excerpt, never an inferred summary or assessment. */
export function suggestedTitle(text: string): string {
  const first = text.split(/\r?\n/).find(line => line.trim().length)?.trim() ?? "";
  let title = "";
  for (const character of first) { if (title.length + character.length > 160) break; title += character; }
  return title;
}
