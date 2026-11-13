import { afterEach, describe, expect, it, vi } from "vitest";
import { AttentionError, parseApprovalPage, parseFilingPage, parseNotificationPage } from "./attention-api";
import { deadline, documentLabels, EMPTY_TEXT, emptyState, expired, groups, InboxDenied, LINK_NOTE, loadInbox, merge, MORE_TEXT, moreApprovals, retrySource, SOURCES, VIEW_LIFETIME_MS, type Card, type Inbox } from "./attention-inbox";
import { task } from "./test-support/tasks";
import { approval, approvalPage, doc, documentPage, filingPage, filingRow, me, notificationPage, notificationRow, now, other, reminderPage, reminderRow, scope, SECRET, session, soon, stamp, taskPage, uid } from "./test-support/attention";

const mkCard = (kind: Card["kind"], id: string, over: Partial<Card> = {}): Card => ({ kind, id, key: `${kind}:${id}`, scope, revision: 1, title: "t", status: "s", labels: [], evidence: [], uncertainty: [], readAt: stamp, open: null, openNote: null, expiresAt: null, changedDuringRefresh: false, ...over });
type Bodies = Record<string, object>;
function route(path: string, body: Bodies[string], overrides: Record<string, () => Response>): Response {
  const key = `${path}:${(body as { state?: string }).state ?? ""}`;
  if (overrides[key]) return overrides[key]();
  if (overrides[path]) return overrides[path]();
  const state = (body as { state?: string }).state ?? "";
  const pages: Record<string, unknown> = {
    "/api/v1/approvals/query": approvalPage(),
    "/api/v1/filing/query": filingPage(state),
    "/api/v1/notifications/query": notificationPage(state),
    "/api/v1/documents/query": documentPage([doc()]),
    "/api/v1/reminders/query": reminderPage([reminderRow()]),
    "/api/v1/tasks/query": taskPage([{ ...task, owner_id: me, scope, due_at: stamp }]),
  };
  return new Response(JSON.stringify(pages[path]));
}
function mock(overrides: Record<string, () => Response> = {}) {
  const fetch = vi.fn(async (path: string, init: RequestInit) => route(path, JSON.parse(String(init.body)), overrides));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const signal = () => new AbortController().signal;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("reads", () => {
  it("issues exactly eight protected read queries and nothing else", async () => {
    const fetch = mock();
    const inbox = await loadInbox(session, scope, signal());
    expect(fetch).toHaveBeenCalledTimes(8);
    const seen = fetch.mock.calls.map(([path, init]) => `${path}|${init.method}|${init.body}`).sort();
    expect(seen).toEqual([
      `/api/v1/approvals/query|POST|{"scope":"${scope}"}`,
      `/api/v1/documents/query|POST|{"scope":"${scope}","reviewed_only":false,"search":"","after":null}`,
      `/api/v1/filing/query|POST|{"scope":"${scope}","state":"failed","document_id":null,"after":null}`,
      `/api/v1/filing/query|POST|{"scope":"${scope}","state":"unknown","document_id":null,"after":null}`,
      `/api/v1/notifications/query|POST|{"scope":"${scope}","state":"failed","after":null}`,
      `/api/v1/notifications/query|POST|{"scope":"${scope}","state":"unknown","after":null}`,
      `/api/v1/reminders/query|POST|{"scope":"${scope}","state":"delivered","after":null}`,
      `/api/v1/tasks/query|POST|{"scope":"${scope}","status":"open","due":"overdue","search":"","after":null}`,
    ].sort());
    for (const [path, init] of fetch.mock.calls) {
      expect(path).toMatch(/^\/api\/v1\/[a-z]+\/query$/);
      expect(path).not.toContain("?");
      expect(init).toMatchObject({ credentials: "same-origin", cache: "no-store", redirect: "error" });
      expect(init.headers).toMatchObject({ "X-CSRF-Token": "synthetic-csrf" });
    }
    expect(SOURCES.every(key => inbox.sources[key].state === "available")).toBe(true);
  });

  it("never requests an approval operation route or any state-changing method", async () => {
    const fetch = mock();
    const inbox = await loadInbox(session, scope, signal());
    await retrySource(inbox, "approvals", session, signal());
    for (const [path, init] of fetch.mock.calls) {
      expect(init.method).toBe("POST");
      expect(path).not.toMatch(/\/(decide|cancel|consume|acknowledge|action|schedule|transition|forget|review|send|retry)\b/);
      expect(path).not.toMatch(/\/approvals\/[0-9a-f-]{36}/);
    }
  });

  it("refuses an ungranted or unsupported scope before any request", async () => {
    const fetch = mock();
    await expect(loadInbox({ ...session, user: { ...session.user, scopes: ["technical_admin"] } }, scope, signal())).rejects.toMatchObject({ status: 403 });
    await expect(loadInbox(session, "technical_admin" as never, signal())).rejects.toBeInstanceOf(InboxDenied);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects an aborted generation even if transport resolves", async () => {
    mock();
    const controller = new AbortController();
    const pending = loadInbox(session, scope, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("approvals are evidence-only", () => {
  it("shows only the minimal metadata, the requester label, and no way to open or act", async () => {
    mock(); const inbox = await loadInbox(session, scope, signal());
    const approvals = groups(inbox)[0];
    expect(approvals.id).toBe("approvals");
    const [mine] = approvals.cards;
    expect(mine).toMatchObject({ kind: "approval", status: "Awaiting a decision", labels: ["Requested by you"], open: null });
    expect(mine.openNote).toMatch(/No approvals screen is available/);
    expect(JSON.stringify(mine)).not.toMatch(/payload|policy|approved_by|requested_by"/i);
  });
  it("labels another member's request without implying a self-approval rule", async () => {
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(approvalPage([approval(2)]))) });
    const [card] = groups(await loadInbox(session, scope, signal()))[0].cards;
    expect(card.labels).toEqual(["Requested by another member of this scope"]);
    expect(JSON.stringify(card)).not.toMatch(/self|prohibit|cannot approve your own/i);
  });
  it.each([
    ["payload", { request_payload: { note: SECRET } }],
    ["hash", { payload_hash: "a".repeat(64) }],
    ["policy", { policy_version: "v1" }],
    ["approver", { approved_by: me }],
    ["requester id", { requested_by: other }],
  ])("withholds the whole source when an item carries %s", async (_name, extra) => {
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(approvalPage([approval(1, extra)]))) });
    const inbox = await loadInbox(session, scope, signal());
    expect(inbox.sources.approvals).toEqual({ state: "unavailable" });
    expect(JSON.stringify(inbox)).not.toContain(SECRET);
  });
  it.each([
    ["wrong status", approvalPage([approval(1, { status: "approved" })])],
    ["wrong scope", approvalPage([approval(1, { scope: "household_shared" })])],
    ["duplicate", approvalPage([approval(1), approval(1)])],
    ["unordered", approvalPage([approval(2), approval(1)])],
    ["extra envelope key", approvalPage([approval(1)], { total: 9 })],
    ["bad cursor", approvalPage([approval(1)], { next_cursor: uid(1) })],
    ["bad boolean", approvalPage([approval(1, { requested_by_you: "yes" })])],
  ])("treats %s as unavailable, never empty", async (_name, body) => {
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(body)) });
    expect((await loadInbox(session, scope, signal())).sources.approvals).toEqual({ state: "unavailable" });
  });
});

describe("partial failure and denial", () => {
  it.each(SOURCES.map((key, i) => [key, i] as const))("an ordinary failure of %s marks only that source unavailable", async key => {
    const failing = { approvals: "/api/v1/approvals/query:", documents: "/api/v1/documents/query:", reminders: "/api/v1/reminders/query:delivered", tasks: "/api/v1/tasks/query:", filing_failed: "/api/v1/filing/query:failed", filing_unknown: "/api/v1/filing/query:unknown", notifications_failed: "/api/v1/notifications/query:failed", notifications_unknown: "/api/v1/notifications/query:unknown" }[key];
    mock({ [failing]: () => new Response("secret provider traceback", { status: 503 }) });
    const inbox = await loadInbox(session, scope, signal());
    for (const other of SOURCES) expect(inbox.sources[other].state).toBe(other === key ? "unavailable" : "available");
    expect(JSON.stringify(inbox)).not.toContain("traceback");
  });
  it.each([401, 403, 404, 410])("clears everything on authority denial %s from any one source", async status => {
    for (const path of ["/api/v1/approvals/query", "/api/v1/tasks/query", "/api/v1/notifications/query"]) {
      mock({ [path]: () => new Response("private", { status }) });
      await expect(loadInbox(session, scope, signal())).rejects.toMatchObject({ name: "Error", status });
    }
  });
  it("malformed filing and notification pages are unavailable; foreign owners are refused", async () => {
    mock({ "/api/v1/filing/query": () => new Response(JSON.stringify({ ...filingPage("failed", [filingRow(1, "failed", { owner_id: other })]) })), "/api/v1/notifications/query": () => new Response("{}") });
    const inbox = await loadInbox(session, scope, signal());
    expect(inbox.sources.filing_failed).toEqual({ state: "unavailable" });
    expect(inbox.sources.notifications_unknown).toEqual({ state: "unavailable" });
  });
  it("never reports an empty inbox while any source is unavailable", async () => {
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(approvalPage([]))), "/api/v1/documents/query": () => new Response(JSON.stringify(documentPage([]))), "/api/v1/reminders/query": () => new Response(JSON.stringify(reminderPage([]))), "/api/v1/tasks/query": () => new Response(JSON.stringify(taskPage([]))), "/api/v1/filing/query:unknown": () => new Response("x", { status: 503 }) });
    const inbox = await loadInbox(session, scope, signal());
    expect(emptyState(inbox)).toBe("unavailable");
    expect(EMPTY_TEXT.unavailable).toMatch(/does not mean nothing needs attention/);
  });
  it("says nothing needs attention only when every source loaded and none matched", async () => {
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(approvalPage([]))), "/api/v1/documents/query": () => new Response(JSON.stringify(documentPage([]))), "/api/v1/reminders/query": () => new Response(JSON.stringify(reminderPage([]))), "/api/v1/tasks/query": () => new Response(JSON.stringify(taskPage([]))) });
    expect(emptyState(await loadInbox(session, scope, signal()))).toBe("none");
    expect(EMPTY_TEXT.none).toBe("Nothing needs attention in the sources that loaded.");
  });
  it("source error types carry their status", () => { expect(new AttentionError(503).status).toBe(503); });
});

describe("expiry", () => {
  it("expires at 60 seconds from the start of the read", async () => {
    mock(); const start = Date.parse("2026-11-13T12:00:00Z");
    const inbox = await loadInbox(session, scope, signal(), () => start);
    expect(inbox.expiresAt).toBeLessThanOrEqual(start + VIEW_LIFETIME_MS);
    expect(expired(inbox, inbox.expiresAt - 1)).toBe(false);
    expect(expired(inbox, inbox.expiresAt)).toBe(true);
  });
  it("expires earlier at the soonest displayed approval expiry", async () => {
    const start = Date.now(), early = new Date(start + 20_000).toISOString();
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(approvalPage([approval(1, { expires_at: soon() }), approval(2, { expires_at: early })]))) });
    const inbox = await loadInbox(session, scope, signal(), () => start);
    expect(inbox.expiresAt).toBe(Date.parse(early));
  });
  it("a retry can shorten but never extend the deadline", async () => {
    mock(); const inbox = await loadInbox(session, scope, signal(), () => Date.now());
    const later = await retrySource({ ...inbox, expiresAt: inbox.expiresAt - 30_000 }, "tasks", session, signal());
    expect(later.expiresAt).toBe(inbox.expiresAt - 30_000);
    const early = new Date(Date.now() + 10_000).toISOString();
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(approvalPage([approval(1, { expires_at: early })]))) });
    expect((await retrySource(inbox, "approvals", session, signal())).expiresAt).toBe(Date.parse(early));
    expect(deadline(inbox.startedAt, inbox.sources)).toBeLessThanOrEqual(inbox.startedAt + VIEW_LIFETIME_MS);
  });
  it("retry re-reads exactly one source and keeps the others", async () => {
    const fetch = mock({ "/api/v1/filing/query:unknown": () => new Response("x", { status: 503 }) });
    const inbox = await loadInbox(session, scope, signal());
    expect(inbox.sources.filing_unknown.state).toBe("unavailable");
    fetch.mockClear(); mock();
    const next = await retrySource(inbox, "filing_unknown", session, signal());
    expect(next.sources.filing_unknown.state).toBe("available");
    expect(next.sources.tasks).toBe(inbox.sources.tasks);
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
  });
  it("a denied retry clears the inbox", async () => {
    mock(); const inbox = await loadInbox(session, scope, signal());
    mock({ "/api/v1/tasks/query": () => new Response("x", { status: 403 }) });
    await expect(retrySource(inbox, "tasks", session, signal())).rejects.toMatchObject({ status: 403 });
  });
});

describe("cards, navigation and duplicates", () => {
  it("opens tasks and documents with minimal source coordinates only", async () => {
    mock(); const inbox = await loadInbox(session, scope, signal());
    const [taskCard] = groups(inbox).find(g => g.id === "tasks")!.cards;
    expect(taskCard.open).toEqual({ type: "source", target: { kind: "task", id: task.id, owner_id: me, scope, revision: task.revision, created_at: task.created_at } });
    const [documentCard] = groups(inbox).find(g => g.id === "documents")!.cards;
    expect(documentCard.open).toEqual({ type: "source", target: { kind: "document", id: uid(50), owner_id: me, scope, revision: 3, created_at: stamp } });
    expect(JSON.stringify(inbox)).not.toContain(SECRET);
  });
  it("links failures to existing scope-level views, and drops the link for a scrubbed filing", async () => {
    mock({ "/api/v1/filing/query:failed": () => new Response(JSON.stringify(filingPage("failed", [filingRow(1, "failed"), filingRow(2, "failed", { scrubbed: true, document_id: null })]))), "/api/v1/notifications/query:unknown": () => new Response(JSON.stringify(notificationPage("unknown", [notificationRow(3, "unknown")]))) });
    const all = groups(await loadInbox(session, scope, signal()));
    const [linked, scrubbed] = all.find(g => g.id === "filing")!.cards;
    expect(linked.open).toEqual({ type: "destination", destination: { view: "documents", scope } });
    expect(scrubbed.open).toBeNull();
    expect(scrubbed.openNote).toMatch(/no longer linked/);
    const [notification] = all.find(g => g.id === "notifications")!.cards;
    expect(notification.open).toEqual({ type: "destination", destination: { view: "reminders", scope } });
    expect(notification.uncertainty.join(" ")).toMatch(/not confirmed/);
    expect(all.find(g => g.id === "filing")!.notices[0]).toMatch(/Synthetic destination only/);
  });
  it("puts a document with two reasons in one card with two labels", () => {
    const row = doc({ extraction: { engine: "poppler-text-v1", version: "1", status: "no_text", pages: 1, page_spans: [], empty_pages: [] } });
    expect(documentLabels(row)).toEqual(["No text extracted", "Text review needed"]);
    expect(documentLabels(doc({ reviewed: true }))).toEqual([]);
    expect(documentLabels(doc({ state: "forgotten" }))).toEqual([]);
  });
  it("excludes reviewed documents and keeps private-scope ownership strict", async () => {
    mock({ "/api/v1/documents/query": () => new Response(JSON.stringify(documentPage([doc({ reviewed: true })]))) });
    expect(groups(await loadInbox(session, scope, signal())).find(g => g.id === "documents")!.cards).toEqual([]);
    mock({ "/api/v1/documents/query": () => new Response(JSON.stringify(documentPage([doc({ owner_id: other })]))), "/api/v1/tasks/query": () => new Response(JSON.stringify(taskPage([{ ...task, owner_id: other, scope, due_at: stamp, assignee_id: null }]))) });
    const inbox = await loadInbox(session, scope, signal());
    expect(inbox.sources.documents).toEqual({ state: "unavailable" });
    expect(inbox.sources.tasks).toEqual({ state: "unavailable" });
  });
  it("renders a record read in both the failed and unknown queries once, higher revision first", () => {
    const failed = mkCard("notification", uid(7), { revision: 2, status: "Delivery failed" });
    const unknown = mkCard("notification", uid(7), { revision: 3, status: "Delivery not confirmed" });
    const merged = merge([failed], [unknown]);
    expect(merged).toHaveLength(1);
    expect(merged[0]).toMatchObject({ status: "Delivery not confirmed", changedDuringRefresh: true });
    expect(merge([failed], [{ ...failed }])[0].changedDuringRefresh).toBe(true);
    expect(merge([unknown], [failed])[0]).toMatchObject({ status: "Delivery not confirmed", revision: 3 });
  });
  it("revision tiebreak: higher wins, lower never replaces, an equal revision takes the later read", () => {
    const base = mkCard("filing", uid(8), { revision: 2, status: "first" });
    expect(merge([base], [{ ...base, revision: 3, status: "higher" }])[0]).toMatchObject({ status: "higher", revision: 3 });
    expect(merge([{ ...base, revision: 3, status: "held" }], [{ ...base, revision: 2, status: "lower" }])[0]).toMatchObject({ status: "held", revision: 3 });
    expect(merge([base], [{ ...base, status: "later" }])[0]).toMatchObject({ status: "later", revision: 2, changedDuringRefresh: true });
    expect(merge([{ ...base, status: "later" }], [base])[0].status).toBe("first");
    expect(merge([base], [mkCard("filing", uid(10))])).toHaveLength(2);
  });
  it("never merges different record kinds that share an id", () => {
    expect(merge([mkCard("filing", uid(9))], [mkCard("document", uid(9))])).toHaveLength(2);
  });
  it("renders first pages with an explicit more-records notice and no totals", async () => {
    const rows = Array.from({ length: 25 }, (_, i) => approval(i + 1));
    mock({ "/api/v1/approvals/query": () => new Response(JSON.stringify(approvalPage(rows, { next_cursor: rows[24].id }))) });
    const group = groups(await loadInbox(session, scope, signal()))[0];
    expect(group.cards).toHaveLength(25);
    expect(group.more).toBe(true);
    expect(Object.keys(group)).not.toContain("total");
  });
});

describe("strict parsers", () => {
  it("pin allow-listed shapes", () => {
    expect(parseApprovalPage(approvalPage(), scope).items).toHaveLength(1);
    expect(parseFilingPage(filingPage("failed", [filingRow(1, "failed")]), scope, "failed", session).items[0]).not.toHaveProperty("destination");
    expect(parseNotificationPage(notificationPage("unknown", [notificationRow(1, "unknown")]), scope, "unknown", session).items[0]).not.toHaveProperty("owner_id");
    expect(() => parseFilingPage(filingPage("failed", [filingRow(1, "unknown")]), scope, "failed", session)).toThrow();
    expect(() => parseFilingPage(filingPage("failed", [filingRow(1, "failed", { scrubbed: true })]), scope, "failed", session)).toThrow();
    expect(() => parseNotificationPage({ ...notificationPage("failed"), owner_id: other }, scope, "failed", session)).toThrow();
  });
});

function emptyInbox(): Inbox {
  const sources = Object.fromEntries(SOURCES.map(key => [key, { state: "available", readAt: stamp, cards: [], more: false, notice: null }])) as unknown as Inbox["sources"];
  return { scope, startedAt: 0, expiresAt: 1, sources };
}
it("an empty available inbox groups six sections in the specified order", () => {
  expect(groups(emptyInbox()).map(group => group.id)).toEqual(["approvals", "filing", "notifications", "documents", "reminders", "tasks"]);
});

describe("approvals paging and honest section wording", () => {
  const ids = (from: number, n: number) => Array.from({ length: n }, (_, i) => approval(from + i));
  it("reads the next approvals page only on request, appends it, and never extends the deadline", async () => {
    const calls: unknown[] = [];
    const fetch = vi.fn(async (path: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      if (path === "/api/v1/approvals/query") { calls.push(body); return new Response(JSON.stringify(body.after ? approvalPage(ids(26, 2)) : approvalPage(ids(1, 25), { next_cursor: uid(25) }))); }
      return route(path, body, {});
    });
    vi.stubGlobal("fetch", fetch);
    const inbox = await loadInbox(session, scope, signal());
    const first = groups(inbox)[0];
    expect(first).toMatchObject({ more: true, pageable: true });
    expect(first.cards).toHaveLength(25);
    expect(calls).toEqual([{ scope }]);
    const paged = await moreApprovals(inbox, session, signal());
    expect(calls).toEqual([{ scope }, { scope, after: uid(25) }]);
    const group = groups(paged)[0];
    expect(group.cards).toHaveLength(27);
    expect(group).toMatchObject({ more: false, pageable: false });
    expect(paged.expiresAt).toBeLessThanOrEqual(inbox.expiresAt);
    expect(paged.startedAt).toBe(inbox.startedAt);
    // Nothing but the read query was sent: no approval operation route and no GET.
    for (const [path, init] of fetch.mock.calls) { expect(path).not.toMatch(/\/approvals\/[0-9a-f-]{36}|decide|cancel|consume/); expect((init as RequestInit).method).toBe("POST"); }
    expect(JSON.stringify(paged)).not.toContain(SECRET);
  });
  it("does nothing without a cursor, and a failed or out-of-order page keeps the held cards", async () => {
    mock();
    const inbox = await loadInbox(session, scope, signal());
    expect(await moreApprovals(inbox, session, signal())).toBe(inbox);
    vi.stubGlobal("fetch", vi.fn(async (path: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      if (path === "/api/v1/approvals/query") return new Response(JSON.stringify(body.after ? approvalPage(ids(3, 1)) : approvalPage(ids(1, 25), { next_cursor: uid(25) })));
      return route(path, body, {});
    }));
    const paged = await loadInbox(session, scope, signal());
    await expect(moreApprovals(paged, session, signal())).rejects.toThrow();
    expect(groups(paged)[0].cards).toHaveLength(25);
  });
  it("denial while paging clears via InboxDenied", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      if (path === "/api/v1/approvals/query" && body.after) return new Response("{}", { status: 403 });
      if (path === "/api/v1/approvals/query") return new Response(JSON.stringify(approvalPage(ids(1, 25), { next_cursor: uid(25) })));
      return route(path, body, {});
    }));
    await expect(moreApprovals(await loadInbox(session, scope, signal()), session, signal())).rejects.toBeInstanceOf(InboxDenied);
  });
  it("never offers paging for sources that cannot show more, and says so plainly", async () => {
    mock({ "/api/v1/filing/query:failed": () => new Response(JSON.stringify({ ...filingPage("failed", [filingRow(1, "failed")]), next_cursor: uid(1) })) });
    const failed = await loadInbox(session, scope, signal());
    const filing = groups(failed).find(g => g.id === "filing")!;
    expect(filing).toMatchObject({ more: false });
    mock({ "/api/v1/filing/query:failed": () => new Response(JSON.stringify({ ...filingPage("failed", Array.from({ length: 25 }, (_, i) => filingRow(i + 1, "failed"))), next_cursor: uid(25) })) });
    const inbox = await loadInbox(session, scope, signal());
    const section = groups(inbox).find(g => g.id === "filing")!;
    expect(section).toMatchObject({ more: true, pageable: false });
    expect(MORE_TEXT.filing).toMatch(/cannot be viewed from here/);
    expect(MORE_TEXT.notifications).toMatch(/cannot be viewed from here/);
    expect(MORE_TEXT.filing).not.toMatch(/open the source/i);
    expect(LINK_NOTE.filing).toMatch(/does not show this filing request/);
    expect(LINK_NOTE.notification).toMatch(/does not show this delivery record/);
  });
  it("an unavailable approvals source is never described as empty or paged", async () => {
    mock({ "/api/v1/approvals/query": () => new Response("{}", { status: 500 }) });
    const inbox = await loadInbox(session, scope, signal());
    expect(groups(inbox)[0]).toMatchObject({ unavailable: ["approvals"], more: false, pageable: false, cards: [] });
    expect(await moreApprovals(inbox, session, signal())).toBe(inbox);
  });
});
