export const taskScopes = { household_shared: "Shared household", member_a_private: "Member A — private", member_b_private: "Member B — private" } as const;
export type TaskScope = keyof typeof taskScopes;
export type TaskStatus = "open" | "done" | "cancelled";
export type TaskValues = { title: string; details: string; source_reference: string; due_at: string | null; assignment: "unknown" | "me" };
type Meta = { id: string; owner_id: string; scope: TaskScope; state: "active" | "forgotten"; revision: number; created_at: string; updated_at: string; can_edit: boolean };
export type ActiveTask = Meta & { state: "active"; title: string; details: string; source_reference: string; due_at: string | null; assignee_id: string | null; status: TaskStatus; completed_at: string | null; cancelled_at: string | null };
export type Task = ActiveTask | (Meta & { state: "forgotten" });
export type TaskFilters = { scope: TaskScope; status: "all" | TaskStatus; due: "all" | "overdue" | "next_seven_days" | "unknown"; search: string; after: string | null };
export type TaskPage = { schema_version: 1; mode: "manual_task_page"; checked_at: string; filters: TaskFilters; page_limit: 25; managed_copy: false | null; items: ActiveTask[]; next_cursor: string | null };
export type TaskHistory = { schema_version: 1; task_id: string; current_revision: number; state: "active" | "forgotten"; items: { revision: number; actor_id: string; operation: string; created_at: string; snapshot: Task | null }[]; next_cursor: number | null };
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const uuid = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(v);
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 1;
const date = (v: unknown): v is string => typeof v === "string" && Number.isFinite(Date.parse(v));
const nullableDate = (v: unknown) => v === null || date(v);
const text = (v: unknown, max: number): v is string => typeof v === "string" && Array.from(v).length <= max;
function invalid(): never { throw new Error("Invalid task response"); }
export function parseTask(v: unknown, history = false): Task {
  if (!object(v) || !uuid(v.id) || !uuid(v.owner_id) || typeof v.scope !== "string" || !Object.hasOwn(taskScopes, v.scope) || !integer(v.revision) || !date(v.created_at) || !date(v.updated_at) || (!history && typeof v.can_edit !== "boolean")) invalid();
  const meta: Meta = { id: v.id, owner_id: v.owner_id, scope: v.scope as TaskScope, revision: v.revision, created_at: v.created_at, updated_at: v.updated_at, state: "active", can_edit: history ? false : v.can_edit as boolean };
  if (v.state === "forgotten") return { ...meta, state: "forgotten" };
  if (v.state !== "active" || !text(v.title, 160) || !v.title.trim() || !text(v.details, 4000) || !text(v.source_reference, 512) || !v.source_reference.trim() || !["open", "done", "cancelled"].includes(v.status as string) || !(v.assignee_id === null || v.assignee_id === v.owner_id) || !nullableDate(v.due_at) || !nullableDate(v.completed_at) || !nullableDate(v.cancelled_at)) invalid();
  if ((v.status === "open" && (v.completed_at !== null || v.cancelled_at !== null)) || (v.status === "done" && (!date(v.completed_at) || v.cancelled_at !== null)) || (v.status === "cancelled" && (!date(v.cancelled_at) || v.completed_at !== null))) invalid();
  return { ...meta, state: "active", title: v.title, details: v.details, source_reference: v.source_reference, status: v.status as TaskStatus, assignee_id: v.assignee_id as string | null, due_at: v.due_at as string | null, completed_at: v.completed_at as string | null, cancelled_at: v.cancelled_at as string | null };
}
function parseFilters(v: unknown): TaskFilters {
  if (!object(v) || typeof v.scope !== "string" || !Object.hasOwn(taskScopes, v.scope) || !["all", "open", "done", "cancelled"].includes(v.status as string) || !["all", "overdue", "next_seven_days", "unknown"].includes(v.due as string) || !text(v.search, 160) || !(v.after === null || uuid(v.after))) invalid();
  return { scope: v.scope as TaskScope, status: v.status as TaskFilters["status"], due: v.due as TaskFilters["due"], search: v.search, after: v.after as string | null };
}
export function parseTaskPage(v: unknown, expected: TaskFilters, exported = false): TaskPage {
  if (!object(v) || v.schema_version !== 1 || v.mode !== "manual_task_page" || !date(v.checked_at) || v.page_limit !== 25 || v.managed_copy !== (exported ? false : null) || !Array.isArray(v.items) || v.items.length > 25 || !(v.next_cursor === null || uuid(v.next_cursor))) invalid();
  const filters = parseFilters(v.filters);
  if (Object.keys(expected).some(k => expected[k as keyof TaskFilters] !== filters[k as keyof TaskFilters])) invalid();
  const items = v.items.map(item => parseTask(item));
  if (items.some(item => item.state !== "active" || item.scope !== expected.scope) || new Set(items.map(item => item.id)).size !== items.length || items.some((item, i) => (i > 0 && item.id <= items[i-1].id) || (expected.after !== null && item.id <= expected.after)) || (v.next_cursor !== null && (items.length !== 25 || items[24].id !== v.next_cursor))) invalid();
  return { schema_version: 1, mode: "manual_task_page", checked_at: v.checked_at, filters, page_limit: 25, managed_copy: v.managed_copy as false | null, items: items as ActiveTask[], next_cursor: v.next_cursor as string | null };
}
export class TaskError extends Error {
  constructor(public status: number) { super(status === 409 ? "This task changed or the action is no longer valid. Your draft is kept. Discard and reload to review the latest task." : status === 422 ? "Check the task details and due date." : [401,403,404,410].includes(status) ? "Tasks are no longer available. Reload your session or task list." : "Tasks are unavailable. Try again; check the list before repeating a change."); }
}
async function request(path: string, body: object, csrf: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`/api/v1/tasks${path}`, { method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", signal, headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body) });
  if (!response.ok) throw new TaskError(response.status);
  return response.json();
}
export async function listTasks(filters: TaskFilters, csrf: string, signal: AbortSignal, exported = false): Promise<TaskPage> { return parseTaskPage(await request(exported ? "/export" : "/query", exported ? { ...filters, acknowledge_copy_limits: true } : filters, csrf, signal), filters, exported); }
export async function createTask(values: TaskValues, scope: TaskScope, csrf: string, signal: AbortSignal): Promise<Task> {
  const result = parseTask(await request("", { ...values, scope }, csrf, signal));
  if (result.scope !== scope || result.state !== "active" || !result.can_edit || result.status !== "open" || result.revision !== 1) invalid();
  return result;
}
export async function taskAction(task: ActiveTask, operation: "read" | "correct" | "transition" | "forget", csrf: string, signal: AbortSignal, values?: TaskValues | { status: TaskStatus }): Promise<Task> {
  const result = parseTask(await request(`/${task.id}/${operation}`, { scope: task.scope, ...(operation === "read" ? {} : { expected_revision: task.revision }), ...values }, csrf, signal));
  if (result.id !== task.id || result.scope !== task.scope || result.owner_id !== task.owner_id || (operation !== "read" && result.revision !== task.revision + 1) || (operation === "forget" ? result.state !== "forgotten" : result.state !== "active")) invalid();
  return result;
}
export async function taskHistory(task: ActiveTask, after: number, csrf: string, signal: AbortSignal): Promise<TaskHistory> {
  const v = await request(`/${task.id}/history`, { scope: task.scope, after }, csrf, signal);
  if (!object(v) || v.schema_version !== 1 || v.task_id !== task.id || !integer(v.current_revision) || !["active", "forgotten"].includes(v.state as string) || !Array.isArray(v.items) || v.items.length > 25 || !(v.next_cursor === null || integer(v.next_cursor))) invalid();
  const items = v.items.map((item: unknown, i: number) => {
    if (!object(item) || item.revision !== after + i + 1 || !uuid(item.actor_id) || !date(item.created_at) || !["created", "corrected", "completed", "cancelled", "reopened", "forgotten"].includes(item.operation as string)) invalid();
    const snapshot = item.snapshot === null ? null : parseTask(item.snapshot, true);
    if ((snapshot && (snapshot.id !== task.id || snapshot.scope !== task.scope || snapshot.owner_id !== task.owner_id || snapshot.revision !== item.revision || snapshot.state !== "active")) || (v.state === "forgotten" ? snapshot !== null : snapshot === null) || item.actor_id !== task.owner_id) invalid();
    return { revision: item.revision as number, actor_id: item.actor_id, created_at: item.created_at, operation: item.operation as string, snapshot };
  });
  if (items.some(item => item.revision > (v.current_revision as number)) || (v.next_cursor !== null && (items.length !== 25 || v.next_cursor !== items[24].revision))) invalid();
  return { schema_version: 1, task_id: task.id, current_revision: v.current_revision, state: v.state as "active" | "forgotten", items, next_cursor: v.next_cursor as number | null };
}
