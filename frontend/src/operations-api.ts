import type { Session } from "./api";

export const componentKeys = ["api", "database", "archive", "pdf_parser", "local_answers", "workers", "storage_capacity", "backup_restore", "certificates", "independent_observer", "remote_hardware"] as const;
export const softwareKeys = ["api_build", "python", "fastapi", "sqlalchemy", "psycopg", "pydantic"] as const;
const states = ["observed", "configured_unverified", "disabled", "unknown"] as const;
export const jobStates = ["queued", "running", "succeeded", "dead_letter", "other"] as const;
export type Snapshot = {
  schema_version: 1; scope: "technical_admin"; actor_id: string;
  checked_at: string; valid_until: string; window_start: string; window_end: string;
  components: { key: typeof componentKeys[number]; state: typeof states[number] }[];
  software: { key: typeof softwareKeys[number]; version: string | null; source: "declared_build" | "runtime_metadata"; assessment: "not_assessed" }[];
  activity: { state: "not_available" };
  jobs: { sampled: number; has_more: boolean; counts: { [K in typeof jobStates[number]]: number } };
};
export class OperationsError extends Error {
  constructor(public status: number) { super([401,403,404,410].includes(status) ? "Operations access is no longer available. Refresh your session." : "Operations observations unavailable. Reload explicitly; no system health is inferred."); }
}
function fail(): never { throw new Error("Invalid operations observations"); }
function obj(value: unknown): { [key: string]: unknown } { if (!value || typeof value !== "object" || Array.isArray(value)) return fail(); return value as { [key: string]: unknown }; }
function exact(value: { [key: string]: unknown }, keys: readonly string[]) { if (Object.keys(value).sort().join() !== [...keys].sort().join()) fail(); }
function choice<T extends string>(value: unknown, options: readonly T[]): T { if (typeof value !== "string" || !options.includes(value as T)) return fail(); return value as T; }
function stamp(value: unknown): string { if (typeof value !== "string" || value.length > 40 || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value) || !Number.isFinite(Date.parse(value))) return fail(); return value; }
function count(value: unknown): number { if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > 25) return fail(); return value; }
function more(value: unknown, length: number): boolean { if (typeof value !== "boolean" || (value && length !== 25)) return fail(); return value; }
function array(value: unknown, max: number): unknown[] { if (!Array.isArray(value) || value.length > max) return fail(); return value; }
export function parseSnapshot(value: unknown, session: Session): Snapshot {
  const v = obj(value);
  exact(v, ["schema_version", "scope", "actor_id", "checked_at", "valid_until", "window_start", "window_end", "components", "software", "activity", "jobs"]);
  if (v.schema_version !== 1 || v.scope !== "technical_admin" || v.actor_id !== session.user.id || !session.user.scopes.includes("technical_admin")) fail();
  const checked_at = stamp(v.checked_at), valid_until = stamp(v.valid_until), window_start = stamp(v.window_start), window_end = stamp(v.window_end);
  const checked = Date.parse(checked_at), until = Date.parse(valid_until);
  if (checked > Date.now() + 5000 || until <= Date.now() || until !== checked + 60000 || Date.parse(window_end) !== checked || Date.parse(window_start) !== checked - 86400000) fail();
  const components = array(v.components, componentKeys.length).map((item, i) => {
    const r = obj(item); exact(r, ["key", "state"]);
    const key = choice(r.key, componentKeys), state = choice(r.state, states);
    if (key !== componentKeys[i]) fail();
    if (key === "api" || key === "database") { if (state !== "observed") fail(); }
    else if (key === "local_answers") { if (!["configured_unverified", "disabled"].includes(state)) fail(); }
    else if (key === "archive" || key === "pdf_parser") { if (!["configured_unverified", "unknown"].includes(state)) fail(); }
    else if (state !== "unknown") fail();
    return { key, state };
  });
  if (components.length !== componentKeys.length) fail();
  const software = array(v.software, softwareKeys.length).map((item, i) => {
    const r = obj(item); exact(r, ["key", "version", "source", "assessment"]);
    const key = choice(r.key, softwareKeys), source = choice(r.source, ["declared_build", "runtime_metadata"] as const);
    if (key !== softwareKeys[i] || source !== (key === "api_build" ? "declared_build" : "runtime_metadata") || r.assessment !== "not_assessed") fail();
    const version = r.version;
    if (version !== null && (typeof version !== "string" || !/^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$/.test(version))) fail();
    return { key, version: version as string | null, source, assessment: "not_assessed" as const };
  });
  if (software.length !== softwareKeys.length) fail();
  const activity = obj(v.activity); exact(activity, ["state"]);
  if (activity.state !== "not_available") fail();
  const jobs = obj(v.jobs); exact(jobs, ["sampled", "has_more", "counts"]);
  const sampled = count(jobs.sampled), rawCounts = obj(jobs.counts); exact(rawCounts, jobStates);
  const counts = Object.fromEntries(jobStates.map(key => [key, count(rawCounts[key])])) as Snapshot["jobs"]["counts"];
  if (Object.values(counts).reduce((a,b) => a+b, 0) !== sampled) fail();
  return { schema_version: 1, scope: "technical_admin", actor_id: session.user.id, checked_at, valid_until, window_start, window_end, components, software, activity: { state: "not_available" }, jobs: { sampled, has_more: more(jobs.has_more, sampled), counts } };
}
export async function readOperations(session: Session, signal: AbortSignal): Promise<Snapshot> {
  if (!session.user.scopes.includes("technical_admin")) throw new OperationsError(403);
  const response = await fetch("/api/v1/operations/read", { method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", signal, headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrfToken }, body: JSON.stringify({ scope: "technical_admin" }) });
  if (!response.ok) throw new OperationsError(response.status);
  return parseSnapshot(await response.json(), session);
}
