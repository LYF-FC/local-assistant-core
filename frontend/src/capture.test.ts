import { expect, it } from "vitest";
import { suggestedTitle } from "./capture";
it("uses only the first nonblank line without inferring or changing the original text", () => {
  const input = "\n  Synthetic observation  \nOther details";
  expect(suggestedTitle(input)).toBe("Synthetic observation"); expect(input).toContain("Other details"); expect(suggestedTitle(" \n ")).toBe("");
});
it("bounds an editable title without splitting Unicode code points", () => {
  expect(Array.from(suggestedTitle("😀".repeat(200)))).toHaveLength(80);
  expect(suggestedTitle("x".repeat(161))).toBe("x".repeat(160));
});
