export type WorkWorkspace = { id: string; slug: string };
export type WorkPage = { items: WorkWorkspace[]; next_cursor: string | null };
export type WorkStatus = { workspace: WorkWorkspace; pending_gates: string[]; checked_at: string };
export class WorkError extends Error {
  constructor(public status: number) { super(status === 401 ? "Sign-in required." : status === 404 ? "Workspace access is unavailable. Reload your assigned workspaces." : "Work access unavailable. Try again."); }
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function object(v: unknown): v is Record<string, unknown> { return typeof v === "object" && v !== null && !Array.isArray(v); }
function workspace(v: unknown): WorkWorkspace {
  if (!object(v) || typeof v.id !== "string" || !uuid.test(v.id) || typeof v.slug !== "string" || !/^synthetic-[a-z0-9][a-z0-9_-]{0,53}$/.test(v.slug)) throw new Error("Invalid work workspace response");
  return { id: v.id, slug: v.slug };
}
export function parseWorkPage(v: unknown): WorkPage {
  if (!object(v) || v.schema_version !== 1 || v.capability !== "work_private" || !Array.isArray(v.items) || v.items.length > 25 || !(v.next_cursor === null || (typeof v.next_cursor === "string" && uuid.test(v.next_cursor)))) throw new Error("Invalid work registry response");
  const items = v.items.map(workspace);
  if (new Set(items.map(i => i.id)).size !== items.length || (v.next_cursor !== null && v.next_cursor !== items.at(-1)?.id)) throw new Error("Invalid work registry page");
  return { items, next_cursor: v.next_cursor as string | null };
}
export function parseWorkStatus(v: unknown, id: string): WorkStatus {
  if (!object(v) || v.schema_version !== 1 || v.capability !== "work_private" || v.mode !== "access_foundation_only" || v.authority_mode !== "transaction_snapshot" || typeof v.checked_at !== "string" || !Number.isFinite(Date.parse(v.checked_at)) || v.ingestion_allowed !== false || v.model_invoked !== false || v.execution_allowed !== false || !Array.isArray(v.pending_gates) || v.pending_gates.length !== 5 || !v.pending_gates.every(g => typeof g === "string" && /^[a-z_]{1,64}$/.test(g))) throw new Error("Invalid disabled work status");
  const item = workspace(v.workspace);
  if (item.id !== id) throw new Error("Workspace mismatch");
  return { workspace: item, pending_gates: v.pending_gates as string[], checked_at: v.checked_at as string };
}
async function request(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`/api/v1/work/workspaces${path}`, { method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error", signal });
  if (!response.ok) throw new WorkError(response.status);
  return response.json();
}
export async function listWorkspaces(after: string | null, signal: AbortSignal): Promise<WorkPage> {
  const query = new URLSearchParams({ limit: "25" });
  if (after) query.set("after", after);
  return parseWorkPage(await request(`?${query}`, signal));
}
export async function workStatus(id: string, signal: AbortSignal): Promise<WorkStatus> {
  if (!uuid.test(id)) throw new Error("Invalid workspace selection");
  return parseWorkStatus(await request(`/${encodeURIComponent(id)}/status`, signal), id);
}
