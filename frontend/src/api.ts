export type Health = { status: "ok" | "unavailable" };
export type User = { id: string; display_name: string; scopes: string[] };
export type Session = { user: User; csrfToken: string };
export class AuthError extends Error {
  constructor(public status: number) { super(status === 401 ? "Sign-in required" : status === 429 ? "Too many attempts. Try again later." : "Unable to complete sign-in request"); }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
function user(value: unknown): User {
  if (!record(value) || typeof value.id !== "string" || typeof value.display_name !== "string" || !Array.isArray(value.scopes) || !value.scopes.every(s => typeof s === "string")) throw new Error("Invalid identity response");
  return { id: value.id, display_name: value.display_name, scopes: value.scopes };
}
function csrf(value: unknown): string {
  if (typeof value !== "string" || value.length < 40 || value.length > 128) throw new Error("Invalid session response");
  return value;
}
async function auth(path: string, body?: object, signal?: AbortSignal, csrfToken?: string): Promise<unknown> {
  const response = await fetch(`/api/v1/auth/${path}`, {
    method: body ? "POST" : "GET", credentials: "same-origin", cache: "no-store", redirect: "error", signal,
    headers: body ? { "Content-Type": "application/json", ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}) } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new AuthError(response.status);
  return response.json();
}
export async function resumeSession(signal?: AbortSignal): Promise<Session> {
  const data = await auth("session", {}, signal);
  if (!record(data)) throw new Error("Invalid session response");
  return { user: user(data.user), csrfToken: csrf(data.csrf_token) };
}
export async function signIn(slug: string, password: string, signal?: AbortSignal): Promise<Session> {
  const data = await auth("login", { slug, password }, signal);
  if (!record(data)) throw new Error("Invalid session response");
  const csrfToken = csrf(data.csrf_token);
  const profile = user(await auth("me", undefined, signal));
  if (profile.id !== data.user_id) throw new Error("Invalid identity response");
  return { user: profile, csrfToken };
}
export async function signOut(csrfToken: string): Promise<void> {
  const data = await auth("logout", {}, undefined, csrfToken);
  if (!record(data) || data.status !== "signed_out") throw new Error("Invalid sign-out response");
}
export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch("/api/v1/health", { signal, cache: "no-store" });
  if (!response.ok) throw new Error("Butler is not ready");
  const result: unknown = await response.json();
  if (!record(result) || result.status !== "ok") throw new Error("Invalid health response");
  return { status: "ok" };
}
