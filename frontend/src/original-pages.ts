// In-page view of a PDF original as rendered page images (spec 078, decision D4).
// The PDF is never embedded (no <iframe>, <object>, <embed> or blob URL navigation) and no scripting, annotation, link
// or form layer is created: pdf.js only draws each page onto a <canvas>. Eval, XFA and range/stream fetching are off;
// FontFace loading is left at the pdf.js default (disableFontFace: true draws a blank page, see the comment below). Reading a hostile PDF in the browser is NOT verified confinement.
// Rendering is bounded: at most MAX_PAGES (3) pages, one at a time, a pixel budget and side limits per canvas, a total
// time limit, and an abort (Hide, new document, unmount) that cancels the render, destroys the loading task and
// terminates the pdf.js worker, so nothing keeps running behind a hidden or replaced view.
export const MAX_PAGES = 3;
export const RENDER_TIMEOUT_MS = 20_000;
export const DESTROY_WAIT_MS = 500;
const MAX_CANVAS_PIXELS = 4_000_000;
const MAX_CANVAS_SIDE = 8192;
const MIN_CANVAS_SIDE = 50;
const MAX_ASPECT = 20;

export type RenderResult = { pages: number; shown: number };

/** The few pdf.js members used here; injectable so teardown and limits are testable without a browser. */
export type Engine = {
  getDocument(options: Record<string, unknown>): { promise: Promise<any>; destroy(): unknown }; // eslint-disable-line @typescript-eslint/no-explicit-any
  PDFWorker: new (options: { port: unknown }) => { destroy(): void };
  Worker: new () => { terminate(): void };
};

export function canvasScale(pageWidth: number, pageHeight: number, cssWidth: number, ratio: number): number {
  const wanted = (Math.max(cssWidth, 100) * Math.min(Math.max(ratio, 1), 2)) / pageWidth;
  const limit = Math.sqrt(MAX_CANVAS_PIXELS / (pageWidth * pageHeight));
  return Math.min(wanted, limit);
}

/** Refuse a page whose shape cannot be drawn within the limits (very tall or very narrow, or not finite). */
export function pageFits(width: number, height: number, scale: number): boolean {
  if (![width, height, scale].every(Number.isFinite) || width <= 0 || height <= 0 || scale <= 0) return false;
  if (Math.max(width, height) / Math.min(width, height) > MAX_ASPECT) return false;
  const w = Math.floor(width * scale);
  const h = Math.floor(height * scale);
  return w >= MIN_CANVAS_SIDE && h >= MIN_CANVAS_SIDE && w <= MAX_CANVAS_SIDE && h <= MAX_CANVAS_SIDE && w * h <= MAX_CANVAS_PIXELS;
}

async function loadEngine(): Promise<Engine> {
  const pdfjs = await import("pdfjs-dist");
  // Bundled as a classic same-origin worker script (a `.mjs` asset would be served without a script type and blocked).
  const Worker = (await import("pdfjs-dist/build/pdf.worker.min.mjs?worker")).default;
  return { getDocument: o => pdfjs.getDocument(o as never) as never, PDFWorker: pdfjs.PDFWorker as never, Worker: Worker as never };
}

export async function renderOriginalPages(
  bytes: Uint8Array,
  container: HTMLElement,
  signal: AbortSignal,
  engine?: Engine,
  timeoutMs: number = RENDER_TIMEOUT_MS,
): Promise<RenderResult> {
  const pdf = engine ?? (await loadEngine());
  let thread: { terminate(): void } | null = null;
  let worker: { destroy(): void } | null = null;
  let task: { promise: Promise<any>; destroy(): unknown } | null = null; // eslint-disable-line @typescript-eslint/no-explicit-any
  let current: { cancel(): void } | null = null;
  let stopped: Error | null = null;
  let reject: (e: Error) => void = () => undefined;
  const halted = new Promise<never>((_, r) => { reject = r; });
  halted.catch(() => undefined);
  let teardown: Promise<void> | null = null;
  // Idempotent. Stops the render at once; the loading task gets a bounded moment (DESTROY_WAIT_MS) to finish its own
  // cleanup (it also releases the page's fonts), then the PDFWorker is destroyed and the thread is terminated explicitly
  // (PDFWorker.destroy() may leave a caller-supplied thread running). Whatever was created before a failure is torn down.
  const stop = (reason: Error): Promise<void> => {
    if (teardown) return teardown;
    stopped = reason;
    try { current?.cancel(); } catch { /* already finished */ }
    reject(reason);
    teardown = (async () => {
      let wait: ReturnType<typeof setTimeout> | undefined;
      try {
        if (task) await Promise.race([Promise.resolve(task.destroy()), new Promise<void>(r => { wait = setTimeout(r, DESTROY_WAIT_MS); })]);
      } catch { /* already destroyed */ }
      clearTimeout(wait);
      try { worker?.destroy(); } catch { /* already destroyed */ }
      try { thread?.terminate(); } catch { /* already terminated */ }
    })();
    return teardown;
  };
  const guard = <T,>(promise: Promise<T>): Promise<T> => Promise.race([promise, halted]);
  const onAbort = () => void stop(new DOMException("Aborted", "AbortError"));
  signal.addEventListener("abort", onAbort);
  const timer = setTimeout(() => void stop(new Error("The original took too long to draw")), timeoutMs);
  try {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    thread = new pdf.Worker();
    worker = new pdf.PDFWorker({ port: thread });
    task = pdf.getDocument({
      data: bytes.slice(),
      worker,
      isEvalSupported: false,
      enableXfa: false,
      // disableFontFace stays at its default: with it the non-embedded standard fonts of a text PDF are not drawn at all
      // (observed: a blank page) unless the standard font files are bundled too; that alternative is an open follow-up.
      disableAutoFetch: true,
      disableStream: true,
      disableRange: true,
      stopAtErrors: false,
      verbosity: 0,
    });
    const doc = await guard<any>(task.promise); // eslint-disable-line @typescript-eslint/no-explicit-any
    const shown = Math.min(doc.numPages, MAX_PAGES);
    container.replaceChildren();
    for (let number = 1; number <= shown; number++) {
      if (stopped) throw stopped;
      const page = await guard<any>(doc.getPage(number)); // eslint-disable-line @typescript-eslint/no-explicit-any
      const base = page.getViewport({ scale: 1 });
      const ratio = globalThis.devicePixelRatio || 1;
      const scale = canvasScale(base.width, base.height, container.clientWidth || 600, ratio);
      if (!pageFits(base.width, base.height, scale)) throw new Error("This page shape cannot be drawn within the limits");
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.className = "original-page";
      canvas.setAttribute("role", "img");
      canvas.setAttribute("aria-label", `Original page ${number} of ${doc.numPages}`);
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas is not available");
      container.append(canvas);
      const rendering = page.render({ canvasContext: context, viewport });
      current = rendering;
      await guard(rendering.promise);
      current = null;
      page.cleanup();
    }
    return { pages: doc.numPages, shown };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
    await stop(new Error("finished"));
  }
}
