import type { Document } from "../documents-api";
import { task } from "./tasks";

// Synthetic fixtures shared by the attention inbox unit and browser tests.
export const me = "22222222-2222-4222-8222-222222222222", other = "33333333-3333-4333-8333-333333333333";
export const SECRET = "synthetic secret payload";
export const scope = "member_a_private" as const;
export const session = { user: { id: me, display_name: "Synthetic owner", scopes: [scope, "household_shared"] }, csrfToken: "synthetic-csrf" };
export const uid = (n: number) => `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
export const soon = () => new Date(Date.now() + 5 * 60_000).toISOString();
export const now = () => new Date().toISOString();
export const stamp = "2026-11-08T10:00:00Z";

export const approvalPage = (items: object[] = [approval(1)], extra: object = {}) => ({ schema_version: 1, mode: "approval_page", checked_at: now(), page_limit: 25, items, next_cursor: null, ...extra });
export function approval(n: number, change: object = {}) { return { id: uid(n), scope, action_type: "validation.noop", status: "pending", requested_at: stamp, expires_at: soon(), requested_by_you: n === 1, ...change }; }
export function filingRow(n: number, state: string, change: object = {}) { return { id: uid(n), document_id: uid(900 + n), owner_id: me, scope, destination: "synthetic", state, revision: 2, plan_revision: 1, source_revision: 1, attempts: 3, next_attempt_at: null, resolved_at: null, reason: "destination_unavailable", created_at: stamp, updated_at: stamp, scrubbed: false, ...change }; }
export const filingPage = (state: string, items: object[] = []) => ({ schema_version: 1, checked_at: now(), owner_id: me, scope, state, items, next_cursor: null, notice: "Synthetic destination only. No file, folder or network effect exists." });
export function notificationRow(n: number, state: string, change: object = {}) { return { id: uid(n), reminder_id: uid(800 + n), task_id: uid(700 + n), owner_id: me, scope, channel: "in_app", state, revision: 2, cycle: 1, attempts: 2, next_attempt_at: null, resolved_at: null, reason: "channel_unavailable", created_at: stamp, updated_at: stamp, ...change }; }
export const notificationPage = (state: string, items: object[] = []) => ({ schema_version: 1, checked_at: now(), owner_id: me, scope, state, items, next_cursor: null });
export const taskPage = (items: object[] = []) => ({ schema_version: 1, mode: "manual_task_page", checked_at: now(), filters: { scope, status: "open", due: "overdue", search: "", after: null }, page_limit: 25, managed_copy: null, items, next_cursor: null });
export const doc = (change: Partial<Document> = {}): Document => ({ id: uid(50), owner_id: me, scope, state: "active", revision: 3, created_at: stamp, updated_at: stamp, can_edit: true, title: "Synthetic review", filename: "s.txt", source_reference: "Synthetic", reviewed: false, sha256: "a".repeat(64), byte_size: 5, line_count: 1, text_origin: "original_utf8", content_text: SECRET, ...change } as Document);
export const documentPage = (items: object[] = []) => ({ schema_version: 1, mode: "document_page", actor_id: me, checked_at: now(), page_limit: 25, managed_copy: null, filters: { scope, reviewed_only: false, search: "", after: null }, items, next_cursor: null });
export const reminderPage = (items: object[] = []) => ({ schema_version: 1, checked_at: now(), owner_id: me, scope, state: "delivered", after: null, items, next_cursor: null, managed_copy: null, preferences: { schema_version: 1, revision: 0, enabled: true, timezone: "UTC", quiet_start: 1320, quiet_end: 480, daily_limit: 5 } });
export const reminderRow = () => ({ reminder: { id: uid(60), task_id: task.id, owner_id: me, scope, state: "delivered", revision: 2, cycle: 1, policy_revision: 0, task_revision: 1, scheduled_at: stamp, next_attempt_at: null, delivered_at: stamp, reason: null, created_at: stamp, updated_at: stamp }, task: { ...task, owner_id: me, scope, due_at: stamp } });

