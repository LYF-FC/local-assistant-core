import { useEffect, useRef, useState } from "react";
import type { Session } from "./api";
import { taskScopes, type TaskScope } from "./tasks-api";
import { displayTimezone, documentAttention, eventMarks, limitNotes, loadOverview, localDay, OverviewDenied, sourceNote, type Destination, type Overview, type Selection } from "./daily-overview";

export default function DailyOverviewPanel({ session, onUnauthorized, onOpen }: { session: Session; onUnauthorized: () => void; onOpen: (destination: Destination) => void }) {
  const scopes = session.user.scopes.filter((scope): scope is TaskScope => Object.hasOwn(taskScopes, scope));
  const [selection, setSelection] = useState<Selection>(() => ({ scope: scopes[0] ?? "household_shared", day: localDay(), timezone: displayTimezone() }));
  const [data, setData] = useState<Overview | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState("Choose a scope and day, then refresh the overview.");
  const pending = useRef<AbortController | null>(null), generation = useRef(0), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function clear(note: string) {
    ++generation.current;
    pending.current?.abort();
    clearTimeout(timer.current);
    setData(null); setBusy(false); setMessage(note);
  }
  function edit(patch: Partial<Selection>) {
    clear("Selection changed. Refresh to read current records.");
    setSelection(current => ({ ...current, ...patch }));
  }
  async function refresh() {
    clear("");
    if (!scopes.includes(selection.scope) || document.hidden) return;
    const controller = new AbortController(), id = ++generation.current;
    pending.current = controller;
    setBusy(true);
    const expire = () => clear("This overview expired. Refresh to check current records.");
    timer.current = setTimeout(expire, 60_000);
    try {
      const result = await loadOverview(session, selection, controller.signal);
      if (controller.signal.aborted || id !== generation.current) return;
      const lifetime = Date.parse(result.expiresAt) - Date.now();
      if (lifetime <= 0) { expire(); return; }
      clearTimeout(timer.current); timer.current = setTimeout(expire, lifetime);
      setData(result); setMessage("Overview loaded. Sources were checked separately; open a record for its latest state.");
    } catch (error) {
      if (controller.signal.aborted || id !== generation.current) return;
      clearTimeout(timer.current); setData(null);
      setMessage(error instanceof OverviewDenied ? error.message : "Overview unavailable. Check the selected day/timezone, then explicitly refresh.");
      if (error instanceof OverviewDenied && error.status === 401) onUnauthorized();
    } finally { if (!controller.signal.aborted && id === generation.current) setBusy(false); }
  }
  const membership = session.user.scopes.join("\0");
  useEffect(() => {
    clear("Choose a scope and day, then refresh the overview.");
    setSelection(current => ({ ...current, scope: session.user.scopes.includes(current.scope) ? current.scope : scopes[0] ?? "household_shared" }));
    const hidden = () => { if (document.hidden) clear("Overview hidden. Refresh to check current records when you return."); };
    document.addEventListener("visibilitychange", hidden);
    return () => { ++generation.current; pending.current?.abort(); clearTimeout(timer.current); document.removeEventListener("visibilitychange", hidden); };
  }, [session.csrfToken, session.user.id, membership]);
  function open(destination: Destination) {
    if (!data || Date.parse(data.expiresAt) <= Date.now() || document.hidden || !session.user.scopes.includes(data.selection.scope)) { clear("This overview expired. Refresh before opening records."); return; }
    onOpen(destination);
  }
  const briefing = data?.briefing.state === "available" ? data.briefing.data : null;
  const reminders = data?.reminders.state === "available" ? data.reminders.data : null;
  const documents = data?.documents.state === "available" ? data.documents.data : null;
  const attention = documents?.items.filter(row => documentAttention(row) !== null) ?? [];
  const activeReminders = reminders?.items.filter(row => ["scheduled", "delivered"].includes(row.reminder.state)) ?? [];
  return <section className="memory-panel daily-overview" aria-label="Daily overview">
    <h2>Daily overview</h2><p>One granted scope at a time. In-app records only; live providers, external delivery, global approvals and infrastructure health are not verified here.</p>
    {!scopes.length ? <p>No supported record scope is currently granted.</p> : <>
      <div className="overview-selection"><label>Overview scope<select value={selection.scope} onChange={event => edit({ scope: event.target.value as TaskScope })}>{scopes.map(scope => <option key={scope} value={scope}>{taskScopes[scope]}</option>)}</select></label>
        <label>Overview day<input type="date" value={selection.day} onChange={event => edit({ day: event.target.value })} /></label>
        <label>Overview timezone<input maxLength={64} value={selection.timezone} onChange={event => edit({ timezone: event.target.value })} /></label></div>
      <button disabled={busy} onClick={() => void refresh()}>{busy ? "Loading overview…" : "Refresh overview"}</button>
    </>}
    <p role="status">{message}</p>
    {data && <><p className="hint">Reads started {data.startedAt}. Expires {data.expiresAt}. Refresh to check again. Lists are limited; open a source panel for more records and current actions.</p>
      <div className="overview-grid"><section className="memory-detail" aria-label="Day agenda and tasks"><h3>Day agenda and tasks</h3>
        {!briefing ? <p>Agenda unavailable. No empty-day or task-count claim can be made.</p> : <>
          <p>{briefing.day} · {briefing.timezone}. {briefing.notice}</p>
          {limitNotes(briefing).map(note => <p key={note}>{note} Open the source panels to inspect more records.</p>)}
          {!briefing.calendars.length && <p>No calendar source is shown. This does not establish a free day.</p>}
          <ul>{briefing.calendars.map(row => <li key={row.id}>{row.label}{row.mode === "provider" ? " (synchronized)" : ""}: {sourceNote(row)}</li>)}</ul>
          <h4>Calendar occurrences shown: {briefing.events.length}</h4>
          {!briefing.events.length && <p>No occurrences in this bounded response. Check source coverage and freshness.</p>}
          <ul>{briefing.events.map(row => <li key={row.id}><strong>{row.title}</strong> · {row.kind === "timed" ? `${row.start}–${row.end}` : `${row.start_date}–${row.end_date} (end exclusive)`}. Source: {row.source_label}, revision {row.source_revision}. {row.status === "tentative" ? "Tentative. " : ""}{(() => { const state = row.source_state, last = row.stale || (row.availability !== "ready" && row.availability !== "setup_required"), note = state && state !== "available" ? `Source ${state.replace("_", " ")}. ` : ""; return (last ? `Last-known event: ${row.availability}, ${row.stale ? "stale" : "unverified"}. ` : "") + note + (last || note ? "" : "Snapshot only; not a live provider check. "); })()}{row.possible_conflict ? "Possible calendar overlap. " : ""}{eventMarks(row)}</li>)}</ul>
          <h4>Open due tasks shown: {briefing.tasks.length}</h4><ul>{briefing.tasks.map(row => <li key={row.id}>{row.title} · {row.overdue ? "Overdue before this day" : "Due in this day"} · {row.due_at}. {row.assignee_id ? "Assigned to record owner." : "Assignment unknown."}</li>)}</ul>
          <p>Undated and later tasks are outside this day view. Memory details and job health are not aggregated here.</p>
        </>}
        <div className="memory-actions"><button onClick={() => open({ view: "calendar", selection: data.selection })}>Open calendar and briefing</button><button onClick={() => open({ view: "tasks", scope: data.selection.scope })}>Open scoped task list</button></div>
      </section>
      <section className="memory-detail" aria-label="My in-app reminder overview"><h3>My in-app reminders</h3>
        {!reminders ? <p>Reminders unavailable. Delivery state is unknown.</p> : <>
          <p>First page: {reminders.items.length} records examined; {activeReminders.length} scheduled or delivered on this page. Only your reminders are included, even in a shared scope.</p>
          <p>{reminders.preferences.enabled ? "In-app delivery preference enabled; this does not prove a worker is running." : "In-app delivery paused by your preference."} No external notification is implied.</p>
          {reminders.next_cursor && <p>More reminder records exist. This is not a complete pending count.</p>}
          <ul>{activeReminders.map(({ reminder, task }) => <li key={reminder.id}>{task.state === "active" ? task.title : "Task no longer available"}: {reminder.state === "delivered" ? "Delivered in-app; awaiting acknowledgement" : "Scheduled; delivery not confirmed"}. {reminder.reason ? `Reason: ${reminder.reason}. ` : ""}{reminder.next_attempt_at ? `Next eligible attempt: ${reminder.next_attempt_at}.` : ""}</li>)}</ul>
          {!activeReminders.length && <p>No scheduled/delivered reminder is shown on this page; other pages or current changes may differ.</p>}
        </>}
        <button onClick={() => open({ view: "reminders", scope: data.selection.scope })}>Open my scoped reminder inbox</button>
      </section></div>
      <section className="memory-detail" aria-label="Document review overview"><h3>Documents needing attention</h3>
        {!documents ? <p>Document review unavailable. No complete pending-review count is available.</p> : <>
          <p>First page: {documents.items.length} documents examined; {attention.length} needing attention on this page. This is text/extraction review, not invoice-field or filing approval.</p>
          {documents.next_cursor && <p>More documents exist; later pages may contain additional review work.</p>}
          {!attention.length && <p>No document requiring attention is shown on this page. This does not certify the full library as reviewed.</p>}
          <ul>{attention.map(row => <li key={row.id}><strong>{row.title}</strong> · {documentAttention(row)} · Source: {row.source_reference}. Revision {row.revision}. {row.can_edit ? "Creator review controls available in Documents." : "Read-only; creator review is required."} <button onClick={() => open({ view: "documents", scope: data.selection.scope, document: row })}>Open document: {row.title}</button></li>)}</ul>
        </>}
        <button onClick={() => open({ view: "documents", scope: data.selection.scope })}>Open scoped document library</button>
      </section>
    </>}
  </section>;
}
