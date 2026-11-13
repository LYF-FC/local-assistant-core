import { useEffect, useRef, useState } from "react";
import type { Session } from "./api";
import { EMPTY_TEXT, emptyState, expired, groups, InboxDenied, loadInbox, retrySource, type Card, type Inbox, type Open, type SourceKey } from "./attention-inbox";
import { taskScopes, type TaskScope } from "./tasks-api";

const SOURCE_NAME: Record<SourceKey, string> = {
  approvals: "pending approvals", filing_failed: "failed filing", filing_unknown: "filing with unconfirmed outcome",
  notifications_failed: "failed notifications", notifications_unknown: "notifications with unconfirmed delivery",
  documents: "documents needing review", reminders: "delivered reminders", tasks: "overdue open tasks",
};
const IDLE = "Choose a scope, then refresh the inbox. Nothing is read until you do.";

export default function AttentionInboxPanel({ session, onUnauthorized, onOpen, onSearch }: { session: Session; onUnauthorized: () => void; onOpen: (open: Open) => void; onSearch: () => void }) {
  const scopes = session.user.scopes.filter((scope): scope is TaskScope => Object.hasOwn(taskScopes, scope));
  const [scope, setScope] = useState<TaskScope>(scopes[0] ?? "household_shared");
  const [data, setData] = useState<Inbox | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState(IDLE);
  const pending = useRef<AbortController | null>(null), generation = useRef(0), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function clear(note: string) {
    ++generation.current;
    pending.current?.abort();
    clearTimeout(timer.current);
    setData(null); setBusy(false); setMessage(note);
  }
  function arm(inbox: Inbox) {
    clearTimeout(timer.current);
    const wait = inbox.expiresAt - Date.now();
    if (wait <= 0) { clear("This inbox expired. Refresh to see current items."); return false; }
    timer.current = setTimeout(() => clear("This inbox expired. Refresh to see current items."), wait);
    return true;
  }
  function denied(error: unknown) {
    if (!(error instanceof InboxDenied)) return false;
    clear(error.message);
    if (error.status === 401) onUnauthorized();
    return true;
  }
  async function refresh() {
    clear("");
    if (!scopes.includes(scope) || document.hidden) return;
    const controller = new AbortController(), id = ++generation.current;
    pending.current = controller;
    setBusy(true);
    timer.current = setTimeout(() => clear("This inbox expired. Refresh to see current items."), 60_000);
    try {
      const result = await loadInbox(session, scope, controller.signal);
      if (controller.signal.aborted || id !== generation.current) return;
      if (!arm(result)) return;
      setData(result); setMessage("Inbox loaded. Sources were read separately and are not one consistent snapshot.");
    } catch (error) {
      if (controller.signal.aborted || id !== generation.current) return;
      clearTimeout(timer.current); setData(null);
      if (!denied(error)) setMessage("Inbox unavailable. Refresh to try again.");
    } finally { if (!controller.signal.aborted && id === generation.current) setBusy(false); }
  }
  async function retry(key: SourceKey) {
    if (!data || expired(data)) { clear("This inbox expired. Refresh to see current items."); return; }
    const controller = new AbortController(), id = generation.current;
    pending.current = controller;
    setBusy(true);
    try {
      const result = await retrySource(data, key, session, controller.signal);
      if (controller.signal.aborted || id !== generation.current) return;
      if (!arm(result)) return;
      setData(result); setMessage(`Re-read ${SOURCE_NAME[key]} only. Other sources were not refreshed.`);
    } catch (error) {
      if (controller.signal.aborted || id !== generation.current) return;
      if (!denied(error)) setMessage(`Could not re-read ${SOURCE_NAME[key]}.`);
    } finally { if (!controller.signal.aborted && id === generation.current) setBusy(false); }
  }
  const membership = session.user.scopes.join("\0");
  useEffect(() => {
    clear(IDLE);
    setScope(current => (session.user.scopes.includes(current) ? current : scopes[0] ?? "household_shared"));
    const hidden = () => { if (document.hidden) clear("Inbox hidden. Refresh when you return."); };
    document.addEventListener("visibilitychange", hidden);
    return () => { ++generation.current; pending.current?.abort(); clearTimeout(timer.current); document.removeEventListener("visibilitychange", hidden); };
  }, [session.csrfToken, session.user.id, membership]);
  function open(target: Open) {
    if (!data || expired(data) || document.hidden || !session.user.scopes.includes(data.scope)) { clear("This inbox expired. Refresh before opening records."); return; }
    onOpen(target);
  }
  const grouped = data ? groups(data) : [];
  const empty = data ? emptyState(data) : null;
  return <section className="memory-panel attention-inbox" aria-label="Attention inbox">
    <h2>Attention inbox</h2>
    <p>One granted scope at a time. This view only reads and links: it cannot approve, reject, cancel, consume, retry, acknowledge, file, send or complete anything. In-app records only; no live provider, external delivery or infrastructure health is checked here.</p>
    {!scopes.length ? <p>No supported record scope is currently granted.</p> : <>
      <div className="overview-selection"><label>Inbox scope<select value={scope} onChange={event => { clear("Scope changed. Refresh to read current records."); setScope(event.target.value as TaskScope); }}>{scopes.map(value => <option key={value} value={value}>{taskScopes[value]}</option>)}</select></label></div>
      <div className="memory-actions"><button disabled={busy} onClick={() => void refresh()}>{busy ? "Loading inbox…" : "Refresh inbox"}</button><button onClick={onSearch}>Search records</button></div>
    </>}
    <p role="status">{message}</p>
    {data && <>
      <p className="hint">Reads started {new Date(data.startedAt).toISOString()}. Expires {new Date(data.expiresAt).toISOString()}. Each section shows its own read time; the sections are not one consistent snapshot. First pages only: this is not a complete count.</p>
      {empty && <p role="status">{EMPTY_TEXT[empty]}</p>}
      {grouped.map(group => <section key={group.id} className="memory-detail" aria-label={group.title}>
        <h3>{group.title}</h3>
        {group.unavailable.map(key => <p key={key}>Unavailable: {SOURCE_NAME[key]}. This is not an empty result. <button disabled={busy} onClick={() => void retry(key)}>Retry {SOURCE_NAME[key]}</button></p>)}
        {group.notices.map(note => <p key={note} className="hint">{note}</p>)}
        {group.more && <p>More records exist than this first page shows; open the source for the rest.</p>}
        {!group.unavailable.length && !group.cards.length && <p>None in this first page.</p>}
        {group.id === "approvals" && group.cards.length > 0 && <p className="hint">Approvals are shown for awareness only. No approvals screen is available in this release; nothing here can approve, reject, cancel or consume a request.</p>}
        <ul>{group.cards.map(item => <Item key={item.key} item={item} onOpen={open} />)}</ul>
      </section>)}
    </>}
  </section>;
}

function Item({ item, onOpen }: { item: Card; onOpen: (open: Open) => void }) {
  return <li><strong>{item.title}</strong> · {item.status}{item.labels.length > 0 && <> · {item.labels.join(" · ")}</>}
    <br />{item.evidence.join(" · ")} · Read {item.readAt}.
    {item.uncertainty.map(note => <span key={note}><br />{note}</span>)}
    {item.changedDuringRefresh && <><br />Changed while this inbox was loading.</>}
    {item.open ? <> <button onClick={() => onOpen(item.open!)}>Open {item.kind}: {item.title}</button></> : item.openNote ? <><br /><em>{item.openNote}</em></> : null}
  </li>;
}
