import { useEffect, useRef, useState } from "react";
import type { Session } from "./api";
import { OperationsError, readWorkStatus, workNotObserved, type WorkState, type WorkStatus } from "./operations-api";

const queueLabels = { approved_jobs: "Approved jobs", reminders: "Reminders", notifications: "Notifications", filing: "Filing" } as const;
const unobservedLabels: Record<typeof workNotObserved[number], string> = { calendar_sync: "Calendar sync", routines: "Routines", work: "Work" };
const NOT_HEALTH = "This is not a worker-health check: it does not say whether a worker is deployed, running or healthy.";
// Exact wording from spec 073 §1.8. Notification overdue never promises a send.
export function stateCopy(key: keyof typeof queueLabels, state: WorkState): string {
  if (state === "none_observed") return "No overdue or stalled work was observed. This is not a worker health check.";
  if (state === "stalled") return "An attempt or lease expired and was not taken over.";
  return key === "notifications"
    ? "Notification queue work (queuing, processing or reconciling a delivery) has waited longer than the grace period. This does not mean a notification will be sent: a queued delivery may still be paused, deferred or cancelled."
    : "Eligible work has waited longer than the grace period. This does not show why, or what the outcome will be.";
}
const IDLE = "Load work status to see whether eligible queue work is overdue or stalled.";
const EXPIRED = "Work status expired. Load it again explicitly.";
export default function WorkStatusSection({ session, onUnauthorized }: { session: Session; onUnauthorized: () => void }) {
  const [status, setStatus] = useState<WorkStatus | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState(IDLE);
  const generation = useRef(0), pending = useRef<AbortController | null>(null), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function cancel() { ++generation.current; pending.current?.abort(); clearTimeout(timer.current); }
  function clear(note: string) { cancel(); setStatus(null); setBusy(false); setMessage(note); }
  async function load() {
    clear("");
    if (document.hidden || !session.user.scopes.includes("technical_admin")) { clear("Work status unavailable while hidden or ungranted."); return; }
    const controller = new AbortController(), id = ++generation.current, started = Date.now();
    pending.current = controller; setBusy(true);
    timer.current = setTimeout(() => clear(EXPIRED), 60000);
    try {
      const value = await readWorkStatus(session, controller.signal);
      if (controller.signal.aborted || id !== generation.current || document.hidden) return;
      const end = Math.min(started + 60000, Date.parse(value.valid_until));
      if (Date.now() >= end) { clear(EXPIRED); return; }
      clearTimeout(timer.current);
      timer.current = setTimeout(() => clear(EXPIRED), end - Date.now());
      setStatus(value); setMessage("Work status loaded. Queue states only; not a worker-health check.");
    } catch (error) {
      if (controller.signal.aborted || id !== generation.current) return;
      clear(error instanceof OperationsError ? error.message.replace("Operations observations", "Work status") : "Work status is unavailable or invalid. Load it again explicitly; no state is inferred.");
      if (error instanceof OperationsError && error.status === 401) onUnauthorized();
    } finally { if (!controller.signal.aborted && id === generation.current) setBusy(false); }
  }
  const membership = session.user.scopes.join("\0");
  useEffect(() => {
    clear(IDLE);
    const hidden = () => { if (document.hidden) clear("Work status hidden. Load it again when you return."); };
    document.addEventListener("visibilitychange", hidden);
    return () => { cancel(); document.removeEventListener("visibilitychange", hidden); };
  }, [session.user.id, session.csrfToken, membership]);
  if (!session.user.scopes.includes("technical_admin")) return null;
  return <section aria-label="Work status" className="memory-detail">
    <h3>Work status (overdue and stalled queues)</h3>
    <p>One state per queue for approved jobs, reminders, notifications and filing. Even these queue-level states, taken over all household members, are sensitive operational metadata about other members' private activity, so no counts, ages, people, scopes or items are shown. Each load is recorded in the audit log.</p>
    <button disabled={busy} onClick={() => void load()}>Load work status</button>
    <p role="status">{message}</p>
    {status && <>
      <p>Checked {status.checked_at}. Valid no later than {status.valid_until}. Overdue means eligible work has waited longer than the grace period; stalled means an attempt or lease expired and was not taken over.</p>
      <ul aria-label="Queue states">{status.queues.map(row => <li key={row.key}><strong>{queueLabels[row.key]}</strong>: {stateCopy(row.key, row.state)}{row.state === "none_observed" ? "" : " " + NOT_HEALTH}</li>)}</ul>
      <ul aria-label="Not observed queues">{status.not_observed.map(key => <li key={key}><strong>{unobservedLabels[key]}</strong>: Not observed by this view.</li>)}</ul>
      <p>Not a worker-health check for any queue. Timing assumes the server clock does not move backwards; after a clock correction a state can appear early. Queues whose workers are not deployed in this stack can show overdue.</p>
    </>}
  </section>;
}
