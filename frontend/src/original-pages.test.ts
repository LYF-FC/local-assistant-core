import { afterEach, describe, expect, it, vi } from "vitest";
import { DESTROY_WAIT_MS, type Engine, MAX_PAGES, pageFits, renderOriginalPages } from "./original-pages";

// A fake pdf.js: records teardown, and lets a test decide when (or whether) a page render settles.
function fake(options: { pages?: number; width?: number; height?: number; render?: "never" | "ok" } = {}) {
  const log = { terminated: 0, workerDestroyed: 0, taskDestroyed: 0, cancelled: 0, rendered: 0 };
  let release: () => void = () => undefined;
  const engine: Engine = {
    Worker: class { terminate() { log.terminated++; } } as never,
    PDFWorker: class { destroy() { log.workerDestroyed++; } } as never,
    getDocument: () => ({
      promise: Promise.resolve({
        numPages: options.pages ?? 1,
        getPage: async () => ({
          getViewport: ({ scale }: { scale: number }) => ({ width: (options.width ?? 612) * scale, height: (options.height ?? 792) * scale }),
          render: () => ({
            promise: options.render === "never" ? new Promise<void>(() => undefined) : Promise.resolve().then(() => { log.rendered++; release(); }),
            cancel: () => { log.cancelled++; },
          }),
          cleanup: () => undefined,
        }),
      }),
      destroy: async () => { log.taskDestroyed++; },
    }),
  };
  return { engine, log };
}

const canvases: unknown[] = [];
function stubDom() {
  canvases.length = 0;
  vi.stubGlobal("document", { createElement: () => { const c = { width: 0, height: 0, className: "", setAttribute() {}, getContext: () => ({}) }; canvases.push(c); return c; } });
}
const container = () => ({ clientWidth: 600, replaceChildren() {}, append() {} }) as unknown as HTMLElement;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("bounded in-page PDF view (spec 078)", () => {
  it("draws at most 3 pages and tears the worker and task down when it is done", async () => {
    stubDom();
    const { engine, log } = fake({ pages: 9 });
    const result = await renderOriginalPages(new Uint8Array([1]), container(), new AbortController().signal, engine);
    expect(result).toEqual({ pages: 9, shown: MAX_PAGES });
    expect(canvases).toHaveLength(MAX_PAGES);
    expect(log.workerDestroyed).toBe(1);
    expect(log.terminated).toBe(1);
    expect(log.taskDestroyed).toBe(1);
  });
  it("Hide mid-render aborts: the render is cancelled, the task destroyed and the worker terminated", async () => {
    stubDom();
    const { engine, log } = fake({ render: "never" });
    const control = new AbortController();
    const running = renderOriginalPages(new Uint8Array([1]), container(), control.signal, engine);
    await new Promise(r => setTimeout(r, 0));
    control.abort();
    await expect(running).rejects.toMatchObject({ name: "AbortError" });
    expect(log.cancelled).toBe(1);
    expect(log.taskDestroyed).toBe(1);
    expect(log.workerDestroyed).toBe(1);
    expect(log.terminated).toBe(1);
  });
  it("switching document or unmounting (both abort the same signal) terminates the thread exactly once, even if aborted twice", async () => {
    stubDom();
    const { engine, log } = fake({ render: "never" });
    const control = new AbortController();
    const running = renderOriginalPages(new Uint8Array([1]), container(), control.signal, engine);
    await new Promise(r => setTimeout(r, 0));
    control.abort();
    control.abort();
    await expect(running).rejects.toMatchObject({ name: "AbortError" });
    expect(log.terminated).toBe(1);
  });
  it("a synchronous getDocument failure, or a PDFWorker that cannot be built, still terminates the thread", async () => {
    stubDom();
    const { engine, log } = fake();
    await expect(renderOriginalPages(new Uint8Array([1]), container(), new AbortController().signal, { ...engine, getDocument: () => { throw new Error("boom"); } })).rejects.toThrow("boom");
    expect(log.terminated).toBe(1);
    expect(log.workerDestroyed).toBe(1);
    const second = fake();
    await expect(renderOriginalPages(new Uint8Array([1]), container(), new AbortController().signal, { ...second.engine, PDFWorker: class { constructor() { throw new Error("no worker"); } } as never })).rejects.toThrow("no worker");
    expect(second.log.terminated).toBe(1);
  });
  it("waits at most a bounded moment for destroy() before terminating, and never builds anything for an aborted signal", async () => {
    stubDom();
    vi.useFakeTimers();
    const { engine, log } = fake({ render: "never" });
    const hung = { ...engine, getDocument: (o: Record<string, unknown>) => ({ ...engine.getDocument(o), destroy: () => new Promise(() => undefined) }) };
    const control = new AbortController();
    const running = renderOriginalPages(new Uint8Array([1]), container(), control.signal, hung);
    const outcome = expect(running).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(10);
    control.abort();
    await vi.advanceTimersByTimeAsync(10);
    expect(log.terminated).toBe(0); // still waiting for destroy()
    await vi.advanceTimersByTimeAsync(DESTROY_WAIT_MS + 1);
    await outcome;
    expect(log.terminated).toBe(1);
    vi.useRealTimers();
    const aborted = new AbortController();
    aborted.abort();
    const second = fake();
    await expect(renderOriginalPages(new Uint8Array([1]), container(), aborted.signal, second.engine)).rejects.toMatchObject({ name: "AbortError" });
    expect(second.log.terminated).toBe(0);
  });
  it("a render that never finishes is stopped by the time limit with a visible error", async () => {
    stubDom();
    vi.useFakeTimers();
    const { engine, log } = fake({ render: "never" });
    const running = renderOriginalPages(new Uint8Array([1]), container(), new AbortController().signal, engine, 5000);
    const outcome = expect(running).rejects.toThrow("too long");
    await vi.advanceTimersByTimeAsync(5001);
    await outcome;
    expect(log.workerDestroyed).toBe(1);
    expect(log.terminated).toBe(1);
    expect(log.taskDestroyed).toBe(1);
  });
  it("an already aborted signal starts nothing that keeps running", async () => {
    stubDom();
    const { engine, log } = fake();
    const control = new AbortController();
    control.abort();
    await expect(renderOriginalPages(new Uint8Array([1]), container(), control.signal, engine)).rejects.toMatchObject({ name: "AbortError" });
    expect(log.terminated).toBe(0); // nothing was created
  });
  it("refuses very tall, very narrow and non-finite pages instead of drawing a distorted or huge canvas", async () => {
    expect(pageFits(612, 792, 0.98)).toBe(true);
    expect(pageFits(10, 10000, 0.5)).toBe(false);
    expect(pageFits(10000, 10, 0.5)).toBe(false);
    expect(pageFits(Number.NaN, 792, 1)).toBe(false);
    expect(pageFits(612, 792, 100)).toBe(false);
    stubDom();
    const { engine, log } = fake({ width: 10, height: 10000 });
    await expect(renderOriginalPages(new Uint8Array([1]), container(), new AbortController().signal, engine)).rejects.toThrow("cannot be drawn");
    expect(canvases).toHaveLength(0);
    expect(log.workerDestroyed).toBe(1);
    expect(log.terminated).toBe(1);
  });
});
