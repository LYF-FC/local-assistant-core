import { useEffect, useRef, useState } from "react";
import type { Session } from "./api";
import { auditCategories, auditOutcomes, auditWindows, OperationsError, readAuditSummary, type AuditSummary, type AuditWindow } from "./operations-api";

const labels: Record<typeof auditCategories[number], string> = {
  sign_in: "Sign-in and sign-out", denied_access: "Denied or rate-limited access", access_change: "Access changes (accounts, passwords, grants)",
  recovery_admin: "Recovery administration", other_admin: "Other administrative actions", operations_read: "Operations views", other_security: "Other security events",
};
const outcomeLabels = { success: "succeeded", denied: "denied", other: "other outcome" };
const IDLE = "Load the audit summary to count recent security and administrative events.";
export default function AuditSummarySection({ session, onUnauthorized }: { session: Session; onUnauthorized: () => void }) {
  const [summary, setSummary] = useState<AuditSummary | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState(IDLE), [window_, setWindow] = useState<AuditWindow>("24h");
  const generation = useRef(0), pending = useRef<AbortController | null>(null), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function cancel() { ++generation.current; pending.current?.abort(); clearTimeout(timer.current); }
  function clear(note: string) { cancel(); setSummary(null); setBusy(false); setMessage(note); }
  async function load() {
    clear("");
    if (document.hidden || !session.user.scopes.includes("technical_admin")) { clear("Audit summary unavailable while hidden or ungranted."); return; }
    const controller = new AbortController(), id = ++generation.current, started = Date.now();
    pending.current = controller; setBusy(true);
    timer.current = setTimeout(() => clear("Audit summary expired. Load it again explicitly."), 60000);
    try {
      const value = await readAuditSummary(session, window_, controller.signal);
      if (controller.signal.aborted || id !== generation.current || document.hidden) return;
      const end = Math.min(started + 60000, Date.parse(value.valid_until));
      if (Date.now() >= end) { clear("Audit summary expired. Load it again explicitly."); return; }
      clearTimeout(timer.current);
      timer.current = setTimeout(() => clear("Audit summary expired. Load it again explicitly."), end - Date.now());
      setSummary(value); setMessage("Audit summary loaded. Zero means no counted events, not that the system is healthy or secure.");
    } catch (error) {
      if (controller.signal.aborted || id !== generation.current) return;
      clear(error instanceof OperationsError ? error.message.replace("Operations observations", "The audit summary") : "The audit summary is unavailable or invalid. Load it again explicitly; no counts are inferred.");
      if (error instanceof OperationsError && error.status === 401) onUnauthorized();
    } finally { if (!controller.signal.aborted && id === generation.current) setBusy(false); }
  }
  const membership = session.user.scopes.join("\0");
  useEffect(() => {
    clear(IDLE);
    const hidden = () => { if (document.hidden) clear("Audit summary hidden. Load it again when you return."); };
    document.addEventListener("visibilitychange", hidden);
    return () => { cancel(); document.removeEventListener("visibilitychange", hidden); };
  }, [session.user.id, session.csrfToken, membership]);
  if (!session.user.scopes.includes("technical_admin")) return null;
  return <section aria-label="Audit summary" className="memory-detail">
    <h3>Audit summary (security and administrative events)</h3>
    <p>Counts only, from a narrow reviewed projection of the audit log. It covers sign-in, denied access, access-change and administrative events; it never shows who, when, which record or any content, and it excludes household, financial, Work, document and task activity. Overdue jobs, capacity trends, scheduled reports and alerting are not provided.</p>
    <label>Window<select aria-label="Audit summary window" value={window_} disabled={busy} onChange={e => { clear(IDLE); setWindow(e.target.value as AuditWindow); }}><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option></select></label>{" "}
    <button disabled={busy} onClick={() => void load()}>Load audit summary</button>
    <p role="status">{message}</p>
    {summary && <>
      <p>Checked {summary.checked_at} for {summary.window_start} to {summary.window_end}. Valid no later than {summary.valid_until}. This request's own audit event is not included.</p>
      <table aria-label="Audit event counts"><thead><tr><th scope="col">Category</th>{auditOutcomes.map(o => <th key={o} scope="col">{outcomeLabels[o]}</th>)}</tr></thead>
        <tbody>{summary.categories.map(row => <tr key={row.key}><th scope="row">{labels[row.key]}</th>{auditOutcomes.map(o => <td key={o}>{row[o]}</td>)}</tr>)}</tbody>
        <tfoot><tr><th scope="row">Total</th>{auditOutcomes.map(o => <td key={o}>{summary.totals[o]}</td>)}</tr></tfoot></table>
      <p>Not a complete security log: an unknown event type is grouped under an "other" category until reviewed, a window older than retained history looks the same as a quiet one, and these counts cannot show that anything is working or attack-free.</p>
    </>}
  </section>;
}
