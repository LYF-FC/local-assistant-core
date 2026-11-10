import { useEffect, useRef, useState } from "react";
import type { Session } from "./api";
import { jobStates, OperationsError, readOperations, type Snapshot } from "./operations-api";

const labels = {
  api: "API request", database: "Database transaction", archive: "Document archive", pdf_parser: "PDF parser", local_answers: "Local answers", workers: "Worker heartbeat / overdue work", storage_capacity: "Disk and NAS headroom", backup_restore: "Backup age and independent restore", certificates: "Certificate validity and renewal", independent_observer: "Independent failure observer", remote_hardware: "Remote hardware / NOMAD",
};
const stateLabels = { observed: "Observed for this request", configured_unverified: "Configured; availability unverified", disabled: "Disabled by environment", unknown: "Unknown — no observation" };
export default function OperationsPanel({ session, onUnauthorized }: { session: Session; onUnauthorized: () => void }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState("Reload to inspect current observations.");
  const generation = useRef(0), pending = useRef<AbortController | null>(null), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function cancel() { ++generation.current; pending.current?.abort(); clearTimeout(timer.current); }
  function clear(note: string) { cancel(); setSnapshot(null); setBusy(false); setMessage(note); }
  async function reload() {
    clear("");
    if (document.hidden || !session.user.scopes.includes("technical_admin")) { clear("Operations access unavailable while hidden or ungranted."); return; }
    const controller = new AbortController(), id = ++generation.current, started = Date.now();
    pending.current = controller; setBusy(true);
    timer.current = setTimeout(() => clear("Operations observations expired. Reload explicitly."), 60000);
    try {
      const value = await readOperations(session, controller.signal);
      if (controller.signal.aborted || id !== generation.current || document.hidden) return;
      const end = Math.min(started + 60000, Date.parse(value.valid_until));
      if (Date.now() >= end) { clear("Operations observations expired. Reload explicitly."); return; }
      clearTimeout(timer.current);
      timer.current = setTimeout(() => clear("Operations observations expired. Reload explicitly."), end - Date.now());
      setSnapshot(value); setMessage("Current bounded observations loaded. Unknown does not mean healthy.");
    } catch (error) {
      if (controller.signal.aborted || id !== generation.current) return;
      clear(error instanceof OperationsError ? error.message : "Operations observations unavailable or invalid. Reload explicitly; no health is inferred.");
      if (error instanceof OperationsError && error.status === 401) onUnauthorized();
    } finally { if (!controller.signal.aborted && id === generation.current) setBusy(false); }
  }
  const membership = session.user.scopes.join("\0");
  useEffect(() => {
    clear("Reload to inspect current observations.");
    const hidden = () => { if (document.hidden) clear("Operations view hidden. Reload when you return."); };
    document.addEventListener("visibilitychange", hidden);
    return () => { cancel(); document.removeEventListener("visibilitychange", hidden); };
  }, [session.user.id, session.csrfToken, membership]);
  return <section className="memory-panel operations-panel" aria-label="Operations overview">
    <h2>Operations overview</h2>
    <p>Technical administration only. This request observes the API and its database transaction; it does not certify system health or authorize activation.</p>
    <p role="status">{message}</p>
    {session.user.scopes.includes("technical_admin") && <button disabled={busy} onClick={() => void reload()}>Reload operations observations</button>}
    <p>Observations clear within 60 seconds of the request, on hidden tab or when you leave. No polling or automatic action.</p>
    {snapshot && <>
      <p>Checked {snapshot.checked_at}. Valid no later than {snapshot.valid_until}.</p>
      <section aria-label="Service observations"><h3>Service observations</h3><ul>{snapshot.components.map(row => <li key={row.key}><strong>{labels[row.key]}</strong>: {stateLabels[row.state]}</li>)}</ul>
        <p>Configuration is not reachability or integrity. Job rows do not prove a worker is running. Database/API success cannot detect an application outage; independent alerts and actual host/recovery checks remain required.</p>
      </section>
      <section aria-label="Runtime software inventory"><h3>Runtime software inventory</h3><ul>{snapshot.software.map(row => <li key={row.key}><strong>{row.key}</strong>: {row.version ?? "Unknown version"} ({row.source === "declared_build" ? "declared build" : "runtime package metadata"})</li>)}</ul>
        <p>Installed or declared versions are not approved/stable versions. License, support, advisories, compatibility and exception expiry are not assessed. Container images, database server and model versions are not inventoried here.</p>
      </section>
      <section aria-label="Own technical activity"><h3>Your recent technical jobs</h3>
        <p>Only your technical_admin activity from {snapshot.window_start} to {snapshot.window_end}. Latest 25 jobs; no household, financial or Work activity, other administrators or payloads. Not global totals or a scheduled audit.</p>
        <h4>Audit review unavailable</h4><p>The application cannot read the audit log. No audit events or access-change totals are inferred. A separately reviewed scoped audit projection and periodic reports remain open.</p>
        <h4>Job sample</h4><p>{snapshot.jobs.sampled} shown. {snapshot.jobs.has_more ? "Additional jobs exist in this window." : "No additional jobs in this sample window."} Overdue work, leases and consumer heartbeat are not assessed.</p>
        <ul>{jobStates.map(key => <li key={key}>{key}: {snapshot.jobs.counts[key]}</li>)}</ul>
      </section>
    </>}
  </section>;
}
