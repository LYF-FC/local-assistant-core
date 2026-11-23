import { describe, expect, it } from "vitest";
import { filingExplanation } from "./filing-reasons";

describe("plain-language filing explanations (spec 077)", () => {
  it("never calls an unknown or waiting filing failed, lost or filed", () => {
    for (const f of [{ state: "unknown", reason: "ambiguous_outcome", attempts: 1 }, { state: "unknown", reason: null, attempts: 1 }, { state: "pending", reason: null, attempts: 0 }, { state: "pending", reason: "transient_error", attempts: 1 }]) {
      const text = filingExplanation(f).toLowerCase();
      expect(text).not.toMatch(/\bfailed\b|\bis lost\b|\bhas been lost\b|\bwas filed\b/);
    }
  });
  it("states that an unknown outcome loses nothing and is never written a second time blindly", () => {
    const text = filingExplanation({ state: "unknown", reason: "ambiguous_outcome", attempts: 1 });
    expect(text).toContain("Nothing was lost");
    expect(text).toContain("will not write a second time blindly");
  });
  it("says honestly that three unsuccessful attempts are final even if the destination was only unreachable", () => {
    const text = filingExplanation({ state: "failed", reason: "attempts_exhausted", attempts: 3 });
    expect(text).toContain("final");
    expect(text).toContain("only unreachable");
    expect(text).toContain("nothing was filed");
  });
  it("says a new request needs a new plan revision after a final result, never just 'make a new request'", () => {
    for (const [state, reason] of [["failed", "attempts_exhausted"], ["failed", "collision"], ["failed", null], ["cancelled", "cancelled_by_owner"]] as const) {
      const text = filingExplanation({ state, reason, attempts: 3 });
      expect(text).toContain("new plan revision");
    }
  });
  it("covers every spec 069 cancellation and failure reason without leaking a code", () => {
    for (const reason of ["collision", "plan_changed", "source_changed", "cancelled_by_owner", "owner_unavailable", "scope_unavailable", "reconciled_absent", "transient_error"]) {
      const text = filingExplanation({ state: "cancelled", reason, attempts: 0 });
      expect(text.length).toBeGreaterThan(20);
      expect(text).not.toContain("_");
    }
    expect(filingExplanation({ state: "filed", reason: null, attempts: 1 })).toContain("once");
  });
});
