import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Session } from "./api";
import ReminderControls from "./ReminderControls";
import { createTask, listTasks, taskAction, TaskError, taskHistory, taskScopes } from "./tasks-api";
import type { ActiveTask, TaskFilters, TaskHistory, TaskPage, TaskScope, TaskStatus, TaskValues } from "./tasks-api";

const dateLabel = (value: string | null) => value ? new Date(value).toLocaleString() : "Unknown";
function localDate(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function Editor({ entry, busy, conflict, onSave, onCancel }: { entry: ActiveTask | null; busy: boolean; conflict: boolean; onSave: (v: TaskValues) => void; onCancel: () => void }) {
  const [title, setTitle] = useState(entry?.title ?? "");
  const [details, setDetails] = useState(entry?.details ?? "");
  const [source, setSource] = useState(entry?.source_reference ?? "Manually entered");
  const [due, setDue] = useState(localDate(entry?.due_at ?? null));
  const [assignment, setAssignment] = useState<"unknown" | "me">(entry?.assignee_id ? "me" : "unknown");
  function save(e: FormEvent) { e.preventDefault(); if (!busy && !conflict) onSave({ title: title.trim(), details, source_reference: source.trim(), due_at: entry && due === localDate(entry.due_at) ? entry.due_at : due ? new Date(due).toISOString() : null, assignment }); }
  return <form className="memory-editor" aria-label={entry ? "Edit task" : "New task"} onSubmit={save}><h3>{entry ? "Edit task details" : "New task"}</h3><fieldset disabled={busy || conflict}>
    <label>Task title<input aria-label="Task title" value={title} onChange={e => setTitle(e.target.value)} required maxLength={160} /></label>
    <label>Task details<textarea aria-label="Task details" value={details} onChange={e => setDetails(e.target.value)} rows={4} maxLength={4000} /></label>
    <label>Assigned to<select aria-label="Assigned to" value={assignment} onChange={e => setAssignment(e.target.value as "unknown" | "me")}><option value="unknown">Unknown / unassigned</option><option value="me">Me</option></select></label>
    <label>Due at (your local time)<input aria-label="Due at (your local time)" type="datetime-local" value={due} onChange={e => setDue(e.target.value)} /></label><p className="hint">Leave blank when unknown. Dates organize your agenda. Set an independent private in-app reminder after saving the task.</p>
    <label>Task source or reference<input aria-label="Task source or reference" value={source} onChange={e => setSource(e.target.value)} required maxLength={512} /></label><button type="submit">{busy ? "Saving…" : "Save task"}</button></fieldset>
    {conflict && <p>Your draft is kept until you discard it.</p>}<button type="button" disabled={busy} onClick={onCancel}>{conflict ? "Discard draft and reload" : "Cancel editing"}</button></form>;
}
export default function TasksPanel({ session, onUnauthorized }: { session: Session; onUnauthorized: () => void }) {
  const scopes = session.user.scopes.filter((s): s is TaskScope => Object.hasOwn(taskScopes, s));
  const initial: TaskFilters = { scope: scopes[0] ?? "household_shared", status: "open", due: "all", search: "", after: null };
  const [filters, setFilters] = useState(initial);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState<TaskPage | null>(null);
  const [selected, setSelected] = useState<ActiveTask | null>(null);
  const [editor, setEditor] = useState<"new" | "edit" | null>(null);
  const [history, setHistory] = useState<TaskHistory | null>(null);
  const [forget, setForget] = useState(false);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState("");
  const active = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  function clearContent() { setPage(null); setSelected(null); setEditor(null); setHistory(null); setForget(false); setAck(false); setConflict(false); setNotice(""); }
  async function run<T>(operation: (signal: AbortSignal) => Promise<T>, accept: (value: T) => void) {
    active.current?.abort(); const controller = new AbortController(); active.current = controller; const generation = ++epoch.current;
    setBusy(true); setError(""); setNotice("");
    try { const result = await operation(controller.signal); if (!controller.signal.aborted && generation === epoch.current) accept(result); }
    catch (e) {
      if (controller.signal.aborted || generation !== epoch.current) return;
      if (e instanceof TaskError && [401,403,404,410].includes(e.status)) { clearContent(); setSearch(""); if (e.status === 401) onUnauthorized(); }
      else if (e instanceof TaskError && e.status === 409) { setConflict(true); setHistory(null); setForget(false); }
      else { setPage(null); setHistory(null); setAck(false); }
      setError(e instanceof TaskError ? e.message : "Tasks are unavailable. Reload before repeating a change.");
    } finally { if (!controller.signal.aborted && generation === epoch.current) setBusy(false); }
  }
  function refresh() { active.current?.abort(); epoch.current++; clearContent(); setFilters(v => ({ ...v, after: null })); }
  useEffect(() => {
    clearContent();
    if (scopes.length) void run(signal => listTasks(filters, session.csrfToken, signal), setPage);
    return () => { active.current?.abort(); epoch.current++; };
    // Session changes remount the parent workspace; filters represent one current scope/page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);
  function chooseFilters(changes: Partial<TaskFilters>) { active.current?.abort(); epoch.current++; clearContent(); setFilters(v => ({ ...v, ...changes, after: null })); }
  function open(task: ActiveTask) { setSelected(null); setEditor(null); setHistory(null); setForget(false); setConflict(false); setAck(false); void run(signal => taskAction(task,"read",session.csrfToken,signal), result => { if (result.state === "active") setSelected(result); }); }
  function save(values: TaskValues) {
    void run(signal => editor === "edit" && selected ? taskAction(selected,"correct",session.csrfToken,signal,values) : createTask(values, filters.scope,session.csrfToken,signal), () => { refresh(); setNotice("Task saved. Current list reloaded."); });
  }
  function transition(status: TaskStatus) {
    if (selected) void run(signal => taskAction(selected,"transition",session.csrfToken,signal,{status}), () => { refresh(); });
  }
  function loadHistory(after = 0) {
    if (selected) void run(signal => taskHistory(selected,after,session.csrfToken,signal), result => { if (result.state === "forgotten") { refresh(); return; } setEditor(null); setHistory(previous => after && previous ? { ...result, items: [...previous.items,...result.items] } : result); });
  }
  function download() {
    if (!ack) return;
    void run(signal => listTasks(filters,session.csrfToken,signal,true), result => {
      const blob = new Blob([JSON.stringify(result,null,2)],{type:"application/json"}); const url=URL.createObjectURL(blob); const link=document.createElement("a"); link.href=url; link.download="butler-tasks-v1.json"; link.click(); URL.revokeObjectURL(url); setAck(false); setNotice(`Downloaded ${result.items.length} current records. This is a live page, not the whole task collection.`);
    });
  }
  if (!scopes.length) return <section className="memory-panel" aria-label="Tasks and agenda"><h2>Tasks and agenda</h2><p>No supported task scope is available for this account.</p></section>;
  return <section className="memory-panel" aria-label="Tasks and agenda"><h2>Tasks and agenda</h2><p>Manual tasks work without AI. Shared tasks are visible to household members; only their creator can change them or read history.</p>
    <div className="memory-filters"><label>Task access<select aria-label="Task access" value={filters.scope} onChange={e => { setSearch(""); chooseFilters({scope:e.target.value as TaskScope,search:""}); }}>{scopes.map(s=><option key={s} value={s}>{taskScopes[s]}</option>)}</select></label>
    <label>Task status<select aria-label="Task status" disabled={busy} value={filters.status} onChange={e=>chooseFilters({status:e.target.value as TaskFilters["status"]})}><option value="open">Open</option><option value="done">Done</option><option value="cancelled">Cancelled</option><option value="all">All statuses</option></select></label>
    <label>Agenda view<select aria-label="Agenda view" disabled={busy} value={filters.due} onChange={e=>chooseFilters({due:e.target.value as TaskFilters["due"]})}><option value="all">Any due date</option><option value="overdue">Overdue · open only</option><option value="next_seven_days">Next seven days · open only</option><option value="unknown">Unknown due date</option></select></label>
    <form onSubmit={e=>{e.preventDefault();chooseFilters({search});}}><label>Find tasks<input aria-label="Find tasks" value={search} onChange={e=>setSearch(e.target.value)} maxLength={160} /></label><button disabled={busy}>Find tasks</button></form></div>
    <div className="memory-actions"><button disabled={busy} onClick={()=>{setSelected(null);setHistory(null);setForget(false);setConflict(false);setEditor("new");setAck(false);setError("");}}>Add task</button><button onClick={()=>{setSearch(filters.search);refresh();}}>Discard drafts and reload tasks</button></div>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}{busy && <p role="status">Loading tasks…</p>}
    {page && <><p className="hint">{page.items.length} on this page · checked {dateLabel(page.checked_at)}. Live pages use stable ID order. No total is inferred.</p>{page.items.length===0?<p>No tasks match this view. Unknown due dates and closed tasks may be in other views.</p>:<ul className="memory-list">{page.items.map(task=><li key={task.id}><button disabled={busy} onClick={()=>open(task)}>{task.title}</button><p>{task.status} · Due: {dateLabel(task.due_at)} · Assigned: {task.assignee_id ? task.can_edit ? "Me" : "Creator" : "Unknown / unassigned"}{!task.can_edit && " · Read only"}</p></li>)}</ul>}
    {page.next_cursor && <button disabled={busy} onClick={()=>setFilters(v=>({...v,after:page.next_cursor}))}>Next task page</button>}{filters.after && <button disabled={busy} onClick={()=>chooseFilters({})}>First task page</button>}
    <details><summary>Download this task page</summary><p>Download rechecks the current page and may differ from the screen. It contains up to 25 tasks, not a complete backup.</p><label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)} disabled={busy}/>I understand downloaded copies and older backups can retain content after forgetting.</label><button disabled={busy || !ack} onClick={download}>Download current task page (JSON)</button></details></>}
    {selected && <article aria-label="Selected task" className="memory-detail"><h3>{selected.title}</h3><p>{taskScopes[selected.scope]} · {selected.status} · Revision {selected.revision}</p><p className="task-details">{selected.details || "No details recorded."}</p><dl><dt>Assignee</dt><dd>{selected.assignee_id ? selected.can_edit ? "Me" : "Creator" : "Unknown / unassigned"}</dd><dt>Due</dt><dd>{dateLabel(selected.due_at)}</dd><dt>Source</dt><dd>{selected.source_reference}</dd><dt>Created</dt><dd>{dateLabel(selected.created_at)}</dd><dt>Updated</dt><dd>{dateLabel(selected.updated_at)}</dd>{selected.completed_at && <><dt>Completed</dt><dd>{dateLabel(selected.completed_at)}</dd></>}{selected.cancelled_at && <><dt>Cancelled</dt><dd>{dateLabel(selected.cancelled_at)}</dd></>}</dl>
    {selected.can_edit ? <><div className="memory-actions"><button disabled={busy || conflict || !!editor} onClick={()=>{setHistory(null);setForget(false);setEditor("edit");}}>Edit task</button>{selected.status==="open"?<><button disabled={busy || conflict || !!editor} onClick={()=>transition("done")}>Mark done</button><button disabled={busy || conflict || !!editor} onClick={()=>transition("cancelled")}>Cancel task</button></>:<button disabled={busy || conflict || !!editor} onClick={()=>transition("open")}>Reopen task</button>}<button disabled={busy || conflict || !!editor} onClick={()=>loadHistory()}>Task history</button><button disabled={busy || conflict || !!editor} onClick={()=>{setHistory(null);setForget(true);}}>Forget task…</button></div>
    {forget && <div role="group" aria-label="Forget task confirmation"><p>Remove this task and every saved revision from live records? Existing downloads and older backups can retain copies.</p><button disabled={busy} onClick={()=>setForget(false)}>Keep task</button><button className="danger" disabled={busy} onClick={()=>void run(signal=>taskAction(selected,"forget",session.csrfToken,signal),()=>refresh())}>Forget task permanently</button></div>}
    {history && <section aria-label="Task revision history"><h4>Task revision history</h4><p>Historical snapshots are not current task status. Checked through revision {history.current_revision}.</p><ol>{history.items.map(item=><li key={item.revision}><p>Revision {item.revision} · {item.operation} · {dateLabel(item.created_at)}</p>{item.snapshot?.state==="active"?<><p>{item.snapshot.title} · {item.snapshot.status}</p><p className="task-details">{item.snapshot.details}</p><p>Due: {dateLabel(item.snapshot.due_at)} · Source: {item.snapshot.source_reference}</p></>:<p>Content forgotten.</p>}</li>)}</ol>{history.next_cursor && <button disabled={busy} onClick={()=>loadHistory(history.next_cursor!)}>More task history</button>}</section>}</>:<p>Read only. Only the creator can change this task or read its history.</p>}{selected.can_edit && !editor && !forget && <ReminderControls key={`${selected.id}:${selected.revision}`} task={selected} session={session} onUnauthorized={onUnauthorized} onUnavailable={refresh}/>}</article>}
    {editor && <Editor key={editor==="new"?"new":`${selected?.id}:${selected?.revision}`} entry={editor==="edit"?selected:null} busy={busy} conflict={conflict} onSave={save} onCancel={refresh}/>}
  </section>;
}
