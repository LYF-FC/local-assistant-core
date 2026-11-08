import { afterEach, describe, expect, it, vi } from "vitest";
import { getHealth } from "./api";

afterEach(() => vi.unstubAllGlobals());
describe("public health client", () => {
  it("accepts the minimal ready contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"status":"ok"}')));
    await expect(getHealth()).resolves.toEqual({ status: "ok" });
  });
  it("does not reveal an upstream error body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private detail", { status: 503 })));
    await expect(getHealth()).rejects.toThrow("Butler is not ready");
  });
  it("rejects malformed contracts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"inference_url":"private"}')));
    await expect(getHealth()).rejects.toThrow("Invalid health response");
  });
  it("passes cancellation and no-store to fetch", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    await getHealth(controller.signal);
    expect(fetch).toHaveBeenCalledWith("/api/v1/health", { signal: controller.signal, cache: "no-store" });
  });
});

// Client security behavior is also exercised through real Chromium + TLS in CI.
describe("identity client", () => {
  it("uses authenticated same-origin JSON bootstrap without browser persistence", async () => {
    const { resumeSession } = await import("./api");
    const data = { user: { id: "synthetic", display_name: "Synthetic", scopes: ["household_shared"] }, csrf_token: "c".repeat(43) };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(data)));
    vi.stubGlobal("fetch", fetch);
    await expect(resumeSession()).resolves.toEqual({ user: data.user, csrfToken: data.csrf_token });
    expect(fetch).toHaveBeenCalledWith("/api/v1/auth/session", expect.objectContaining({ method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", body: "{}", headers: { "Content-Type": "application/json" } }));
  });
  it("sanitizes upstream identity failures", async () => {
    const { resumeSession } = await import("./api");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private-secret", { status: 503 })));
    await expect(resumeSession()).rejects.toThrow("Unable to complete sign-in request");
  });
  it("rejects malformed session contracts", async () => {
    const { resumeSession } = await import("./api");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { id: "x", display_name: "Synthetic", scopes: [7] }, csrf_token: "c".repeat(43) }))));
    await expect(resumeSession()).rejects.toThrow("Invalid identity response");
  });
  it("requires matching identity after sign-in and supplies CSRF on sign-out", async () => {
    const { signIn, signOut } = await import("./api");
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ user_id: "one", csrf_token: "c".repeat(43) }))).mockResolvedValueOnce(new Response(JSON.stringify({ id: "two", display_name: "Synthetic", scopes: [] }))).mockResolvedValueOnce(new Response('{"status":"signed_out"}'));
    vi.stubGlobal("fetch", fetch);
    await expect(signIn("synthetic", "synthetic-password")).rejects.toThrow("Invalid identity response");
    await signOut("c".repeat(43));
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/auth/logout", expect.objectContaining({ headers: { "Content-Type": "application/json", "X-CSRF-Token": "c".repeat(43) } }));
  });
});
