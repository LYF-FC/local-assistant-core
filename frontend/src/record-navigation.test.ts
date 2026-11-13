import { afterEach, describe, expect, it, vi } from "vitest";
import { groups, loadInbox } from "./attention-inbox";
import { readByIdentity, DocumentError, type DocumentIdentity } from "./documents-api";
import { readTaskByIdentity, TaskError } from "./tasks-api";
import { doc, filingPage, filingRow, me, notificationPage, notificationRow, other, scope, session, uid } from "./test-support/attention";
import { task } from "./test-support/tasks";

const signal = () => new AbortController().signal;
afterEach(() => vi.unstubAllGlobals());
const identity: DocumentIdentity = { id: uid(50), owner_id: me, scope, min_revision: 3 };
function respond(body: unknown, status = 200) {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("document identity read (destination reread under current authorization)", () => {
  it("sends only the id and scope, and accepts the current revision when it is at least the minimum", async () => {
    const fetch = respond(doc());
    await expect(readByIdentity(identity, me, "csrf", signal())).resolves.toMatchObject({ id: uid(50), revision: 3 });
    const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe(`/api/v1/documents/${uid(50)}/read`);
    expect(JSON.parse(String(init.body))).toEqual({ scope });
    respond(doc({ revision: 9, created_at: "2030-01-01T00:00:00Z" }));
    await expect(readByIdentity(identity, me, "csrf", signal())).resolves.toMatchObject({ revision: 9 });
  });
  it("rejects an older revision, mismatched id/owner/scope, forgotten and foreign-owned documents", async () => {
    for (const row of [doc({ revision: 2 }), doc({ id: uid(51) }), doc({ owner_id: other, can_edit: false }), doc({ scope: "household_shared" }), doc({ state: "forgotten" } as never), doc({ can_edit: false })]) {
      respond(row);
      await expect(readByIdentity(identity, me, "csrf", signal())).rejects.toThrow();
    }
  });
  it("fails closed for missing and revoked access without using any cached data", async () => {
    for (const status of [401, 403, 404, 410]) {
      respond({}, status);
      await expect(readByIdentity(identity, me, "csrf", signal())).rejects.toMatchObject({ status });
    }
    respond({}, 404);
    await expect(readByIdentity(identity, me, "csrf", signal())).rejects.toBeInstanceOf(DocumentError);
  });
  it("refuses an invalid or other-member private target before any request", async () => {
    const fetch = respond(doc());
    await expect(readByIdentity({ ...identity, owner_id: other }, me, "csrf", signal())).rejects.toThrow();
    await expect(readByIdentity({ ...identity, min_revision: 0 }, me, "csrf", signal())).rejects.toThrow();
    await expect(readByIdentity({ ...identity, id: "x" }, me, "csrf", signal())).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("task identity read for the selected reminder", () => {
  const target = { id: task.id, scope };
  it("sends only the id and scope and requires the actor to own the task", async () => {
    const fetch = respond({ ...task, owner_id: me, scope });
    await expect(readTaskByIdentity(target, me, "csrf", signal())).resolves.toMatchObject({ id: task.id });
    const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe(`/api/v1/tasks/${task.id}/read`);
    expect(JSON.parse(String(init.body))).toEqual({ scope });
    respond({ ...task, owner_id: other, scope, can_edit: false });
    await expect(readTaskByIdentity(target, me, "csrf", signal())).rejects.toThrow();
    respond({ ...task, owner_id: me, scope, id: uid(5) });
    await expect(readTaskByIdentity(target, me, "csrf", signal())).rejects.toThrow();
    respond({ ...task, owner_id: me, scope: "household_shared" });
    await expect(readTaskByIdentity(target, me, "csrf", signal())).rejects.toThrow();
  });
  it("surfaces revoked or missing access as a status", async () => {
    for (const status of [403, 404, 410]) {
      respond({}, status);
      await expect(readTaskByIdentity(target, me, "csrf", signal())).rejects.toBeInstanceOf(TaskError);
    }
  });
});

describe("inbox navigation is read-and-link only", () => {
  it("builds record targets without any request beyond the section queries, and never calls a mutating route", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init: RequestInit) => {
      calls.push(path);
      const state = (JSON.parse(String(init.body)) as { state?: string }).state ?? "";
      const pages: Record<string, unknown> = {
        "/api/v1/filing/query": filingPage(state, state === "failed" ? [filingRow(1, "failed")] : []),
        "/api/v1/notifications/query": notificationPage(state, state === "failed" ? [notificationRow(2, "failed")] : []),
      };
      return new Response(JSON.stringify(pages[path] ?? (path.endsWith("/approvals/query") ? { schema_version: 1, checked_at: new Date().toISOString(), scope, items: [], next_cursor: null } : { items: [] })));
    }));
    await loadInbox(session, scope, signal()).catch(() => undefined);
    const before = calls.length;
    expect(calls.every(path => path.endsWith("/query"))).toBe(true);
    const inbox = await loadInbox(session, scope, signal()).catch(() => null);
    if (inbox) groups(inbox);
    expect(calls.slice(before).every(path => path.endsWith("/query"))).toBe(true);
    expect(calls.some(path => /\/(read|action|schedule|decide|cancel|consume|retry|acknowledge)\b/.test(path))).toBe(false);
  });
});
