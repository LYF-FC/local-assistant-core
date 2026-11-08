import { useEffect, useState } from "react";
import { AuthError, getHealth, resumeSession, signIn, signOut } from "./api";
import RecordsWorkspace from "./RecordsWorkspace";
import type { Session } from "./api";
import type { FormEvent } from "react";

export default function App() {
  const secure = window.location.protocol === "https:";
  const [status, setStatus] = useState("Checking");
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(secure);
  const [busy, setBusy] = useState(false);
  const [slug, setSlug] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal).then(() => setStatus("Ready")).catch(() => {
      if (!controller.signal.aborted) setStatus("Unavailable");
    });
    if (secure) resumeSession(controller.signal).then(value => {
      if (!controller.signal.aborted) setSession(value);
    }).catch(err => {
      if (!controller.signal.aborted && !(err instanceof AuthError && err.status === 401)) setError("Session unavailable. Try again.");
    }).finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
  }, [secure]);
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!secure || busy) return;
    const secret = password;
    setPassword(""); setError(""); setBusy(true);
    try { setSession(await signIn(slug, secret)); }
    catch (err) { setSession(null); setError(err instanceof AuthError ? err.message : "Sign-in unavailable. Try again."); }
    finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError("");
    try { setSession(await resumeSession()); }
    catch { setSession(null); setError("Session unavailable. Sign in again."); }
    finally { setBusy(false); }
  }
  async function logout() {
    if (!session) return;
    setBusy(true); setError("");
    try { await signOut(session.csrfToken); setSession(null); }
    catch (err) {
      if (err instanceof AuthError && err.status === 401) setSession(null);
      else setError("Sign-out unavailable. Refresh session and try again.");
    }
    finally { setBusy(false); }
  }
  return <main className="shell">
    <header className="topbar"><div><p className="eyebrow">Family operating system</p><h1>Butler</h1></div><p role="status">{status}</p></header>
    <section className="hero"><h2>Your private family assistant</h2>
      {!secure ? <p>Open the HTTPS address shown by setup to sign in securely.</p> : checking ? <p>Checking session…</p> : session ? <section aria-label="Your session" className="auth-panel">
        <p>Signed in as <strong>{session.user.display_name}</strong></p>
        <h3>Your current access</h3><ul>{session.user.scopes.map(scope => <li key={scope}>{scope}</li>)}</ul>
        <div className="auth-actions"><button disabled={busy} onClick={refresh}>Refresh session</button><button disabled={busy} onClick={logout}>Sign out</button></div>
      </section> : <form className="auth-panel" onSubmit={login} aria-label="Sign in">
        <p>Sign in with your locally provisioned account.</p>
        <label htmlFor="slug">Username</label><input id="slug" name="username" autoComplete="username" value={slug} maxLength={64} pattern={"[a-z0-9][a-z0-9_\\-]*"} onChange={event => setSlug(event.target.value)} required disabled={busy} />
        <label htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete="current-password" value={password} maxLength={1024} onChange={event => setPassword(event.target.value)} required disabled={busy} />
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>}
      {error && <p role="alert" className="error">{error}</p>}
      <p>Use Tasks and agenda to organize manual tasks, or Memory to inspect and update explicit entries.</p>
      <div className="command"><input aria-label="Ask Butler" placeholder="Search or ask Butler…" disabled /><button disabled>Ask</button></div>
    </section>
    {secure && session && !busy && <RecordsWorkspace key={session.csrfToken} session={session} onUnauthorized={() => setSession(null)} />}
  </main>;
}
