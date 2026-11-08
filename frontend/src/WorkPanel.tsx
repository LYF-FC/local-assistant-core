import { useEffect, useRef, useState } from "react";
import type { Session } from "./api";
import WorkNotesPanel from "./WorkNotesPanel";
import { listWorkspaces, workStatus, WorkError } from "./work-api";
import type { WorkPage, WorkStatus } from "./work-api";

const gateLabels: Record<string, string> = {
  dedicated_content_storage_and_roles: "Dedicated work content storage and database roles",
  workspace_retrieval_context_and_caches: "Isolated search, context, history and caches",
  workspace_jobs_and_credentials: "Workspace-bound jobs and connector credentials",
  work_content_audit_and_observability: "Separate work content audit and observability",
  export_keys_retention_and_isolated_recovery: "Work exports, keys, retention and isolated recovery",
};
export default function WorkPanel(props: { session: Session; onUnauthorized: () => void }) {
  const [page, setPage] = useState<WorkPage | null>(null);
  const [status, setStatus] = useState<WorkStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  function begin() { active.current?.abort(); const controller = new AbortController(); active.current = controller; setStatus(null); setError(""); setBusy(true); return controller; }
  function failure(err: unknown, controller: AbortController) {
    if (controller.signal.aborted) return;
    setPage(null); setStatus(null);
    if (err instanceof WorkError && err.status === 401) props.onUnauthorized();
    else setError(err instanceof WorkError ? err.message : "Work access unavailable. Try again.");
  }
  async function load(after: string | null = null) {
    const controller = begin(); setPage(null);
    try { const result = await listWorkspaces(after, controller.signal); if (!controller.signal.aborted) setPage(result); }
    catch (err) { failure(err, controller); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function inspect(id: string) {
    const controller = begin();
    try { const result = await workStatus(id, controller.signal); if (!controller.signal.aborted) setStatus(result); }
    catch (err) { failure(err, controller); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section aria-label="Work Companion" className="memory-panel">
    <h2>Work Companion</h2>
    <p>Choose an assigned workspace. The optional synthetic note pilot is separate from real work content, models and external actions.</p>
    <p>Family or technical-admin access does not grant work access. Use synthetic workspaces only.</p>
    <button disabled={busy} onClick={() => void load()}>Load assigned workspaces</button>
    {busy && <p role="status">Checking current work access…</p>}
    {error && <p role="alert">{error}</p>}
    {page && <><ul>{page.items.map(item => <li key={item.id}><button disabled={busy} onClick={() => void inspect(item.id)}>{item.slug}</button></li>)}</ul>
      {page.items.length === 0 && <p>No active workspaces are assigned to your account.</p>}
      {page.next_cursor && <button disabled={busy} onClick={() => void load(page.next_cursor)}>Next workspaces</button>}</>}
    {status && <section aria-label="Selected work access"><h3>{status.workspace.slug}</h3>
      <p>Explicit workspace grant confirmed for this check. Ingestion remains disabled.</p>
      <details><summary>Readiness for real work content</summary><h4>Required before work content</h4><ul>{status.pending_gates.map(gate => <li key={gate}>{gateLabels[gate] || "Additional isolation control"}</li>)}</ul>
      </details><p>This status is a snapshot checked at <time dateTime={status.checked_at}>{new Date(status.checked_at).toLocaleString()}</time>. Recheck to verify current membership.</p>
      <button disabled={busy} onClick={() => void inspect(status.workspace.id)}>Recheck current access</button>
      <WorkNotesPanel key={status.workspace.id} workspace={status.workspace.id} session={props.session} onUnauthorized={props.onUnauthorized} />
    </section>}
  </section>;
}
