import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Session } from "./api";
import { taskScopes, type TaskScope } from "./tasks-api";
import { readSearchSource, SearchDenied, searchPage, searchRecords, targetOf, validQuery, type CurrentSource, type SearchKind, type SearchResult, type SearchSelection, type SearchSection, type SourceTarget } from "./record-search";

export default function RecordSearchPanel({ session, onUnauthorized, onOpen }: { session: Session; onUnauthorized: () => void; onOpen: (target: SourceTarget) => void }) {
  const scopes = session.user.scopes.filter((scope): scope is TaskScope => Object.hasOwn(taskScopes, scope));
  const [scope, setScope] = useState<TaskScope>(scopes[0] ?? "household_shared"), [query, setQuery] = useState(""), [data, setData] = useState<SearchResult | null>(null), [source, setSource] = useState<CurrentSource | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState("Choose one granted scope and enter keywords."), [until, setUntil] = useState<number | null>(null);
  const pending = useRef<AbortController | null>(null), generation = useRef(0), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function cancel() { ++generation.current; pending.current?.abort(); clearTimeout(timer.current); setBusy(false); }
  function clear(note: string, eraseQuery = false) { cancel(); setData(null); setSource(null); setUntil(null); if (eraseQuery) setQuery(""); setMessage(note); }
  function arm(end: number) { clearTimeout(timer.current); setUntil(end); timer.current = setTimeout(() => clear("Search expired. Enter keywords and search again.", true), Math.max(0, end - Date.now())); }
  async function run<T>(end: number, operation: (signal: AbortSignal) => Promise<T>, accept: (value: T) => void) {
    cancel(); setMessage("");
    if (document.hidden || !scopes.includes(scope) || Date.now() >= end) { clear("Search unavailable or expired. Search again explicitly.", true); return; }
    const controller = new AbortController(), id = ++generation.current; pending.current = controller; setBusy(true); arm(end);
    try {
      const value = await operation(controller.signal);
      if (controller.signal.aborted || id !== generation.current || document.hidden || Date.now() >= end) return;
      accept(value);
    } catch (error) {
      if (controller.signal.aborted || id !== generation.current) return;
      clear(error instanceof SearchDenied ? error.message : "Search source unavailable or invalid. Search again explicitly.", error instanceof SearchDenied);
      if (!(error instanceof SearchDenied)) arm(end);
      if (error instanceof SearchDenied && error.status === 401) onUnauthorized();
    } finally { if (!controller.signal.aborted && id === generation.current) setBusy(false); }
  }
  function submit(event: FormEvent) {
    event.preventDefault(); clear("");
    if (!validQuery(query)) { setMessage("Enter printable keywords, at most 160 characters."); arm(Date.now() + 60000); return; }
    const selection: SearchSelection = { scope, query: query.trim() }, end = Date.now() + 60000;
    void run(end, signal => searchRecords(session, selection, signal), value => { setData(value); setMessage("Search checked separately in each library. Select a result to read its current source."); });
  }
  function next(kind: SearchKind) {
    if (!data || !until) return;
    const key = kind === "task" ? "tasks" : "documents", section = data[key];
    if (section.state !== "available" || section.page.nextCursor === null) return;
    const saved = data; setSource(null); setData({ ...saved, [key]: { state: "unavailable" } });
    void run(until, async signal => { try { return { state: "available", page: await searchPage(session, saved.selection, kind, section.page.nextCursor, signal) } as SearchSection; } catch (error) { if (error instanceof SearchDenied || signal.aborted) throw error; return { state: "unavailable" } as SearchSection; } }, value => { setData({ ...saved, [key]: value }); setMessage("Only the selected library page changed. The original search deadline still applies."); });
  }
  function read(target: SourceTarget) { if (!data || !until) return; setSource(null); void run(until, signal => readSearchSource(session, target, signal), value => { setSource(value); setMessage("Current source reread. A changed record can differ from the earlier match."); }); }
  function open() { if (!source || !until || Date.now() >= until || document.hidden) { clear("Search expired. Search again.", true); return; } const target = targetOf(source); clear("", true); onOpen(target); }
  const membership = session.user.scopes.join("\0");
  useEffect(() => {
    clear("Choose one granted scope and enter keywords.", true); setScope(scopes[0] ?? "household_shared");
    const hidden = () => { if (document.hidden) clear("Search hidden. Search again when you return.", true); };
    document.addEventListener("visibilitychange", hidden);
    return () => { ++generation.current; pending.current?.abort(); clearTimeout(timer.current); document.removeEventListener("visibilitychange", hidden); };
  }, [session.user.id, session.csrfToken, membership]);
  function results(kind: SearchKind, section: SearchSection) {
    const label = kind === "task" ? "Task" : "Document";
    return <section aria-label={`${label} search results`}><h3>{label} results — one page</h3>{section.state === "unavailable" ? <p>{label} search unavailable. This is not an empty result.</p> : <><p>{section.page.items.length} shown, at most 25. {section.page.nextCursor ? "More matching records exist; request the next page explicitly." : "No additional page reported for this library query."} Checked {section.page.checkedAt}.</p><ul>{section.page.items.map(hit => <li key={hit.target.id}><button disabled={busy} onClick={() => read(hit.target)}>Read current {kind}: {hit.title}</button><p>{hit.status} · revision {hit.target.revision} · {hit.source}</p></li>)}</ul>{section.page.nextCursor && <button disabled={busy} onClick={() => next(kind)}>Next {kind} search page</button>}</>}</section>;
  }
  return <section className="memory-panel record-search-panel" aria-label="Scoped record search"><h2>Search tasks and documents</h2><p>Search one granted scope at a time. Tasks match title/details across all statuses; documents match title/extracted text, including unreviewed text. This is literal keyword search, with separate library pages and no combined rank or global count.</p><p>Memory, finance, Work, approvals and other libraries are not searched here. No model, automatic action or source-link fetch.</p><p role="status">{message}</p>
    {!scopes.length ? <p>No supported search scope is currently granted.</p> : <><form onSubmit={submit}><label>Search scope<select aria-label="Search scope" value={scope} onChange={e => { clear("Scope changed. Enter keywords again.", true); setScope(e.target.value as TaskScope); }}>{scopes.map(s => <option key={s} value={s}>{taskScopes[s]}</option>)}</select></label><label>Keywords<input aria-label="Search keywords" maxLength={320} value={query} onChange={e => { clear("Query changed. Search explicitly."); setQuery(e.target.value); arm(Date.now() + 60000); }} required/></label><button disabled={busy}>Search records</button></form><p>Queries, results and current-source previews clear within 60 seconds, on hidden tab or when you leave. Paging and source reads do not extend the original deadline. {until ? `Privacy deadline: ${new Date(until).toLocaleTimeString()}.` : ""}</p></>}
    {data && <><p>Checked query: {data.selection.query} · {taskScopes[data.selection.scope]}. A failed library and later pages are not included in shown counts.</p>{results("task", data.tasks)}{results("document", data.documents)}</>}
    {source && <article className="memory-detail" aria-label="Current search source"><h3>{source.record.title}</h3><p>{source.kind} · revision {source.record.revision} · {source.record.id} · {taskScopes[source.record.scope]}</p><p>Source: {source.record.source_reference}</p>{source.kind === "task" ? <><p>Status: {source.record.status} · Due: {source.record.due_at ?? "Unknown"}</p><p>{source.record.details}</p></> : <><p>{source.record.reviewed ? "Reviewed text" : "Text review needed"} · {source.record.filename}</p><p>Original hash: {source.record.sha256}. Text origin: {source.record.text_origin}. Extracted lines: {source.record.line_count}.</p>{source.record.extraction && <p>Extraction: {source.record.extraction.status}.</p>}<p>Original and extracted bodies are not retained in this preview. Open the document to inspect authorized lines.</p></>}<p>{source.record.can_edit ? "You own this record; edits remain in its source view." : "Read-only shared record; creator review is required."}</p><button disabled={busy} onClick={open}>Open full {source.kind} record</button></article>}
  </section>;
}
