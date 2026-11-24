// In-page view of a PDF original as rendered page images (spec 078, decision D4).
// The PDF is never embedded (no <iframe>, <object>, <embed> or blob URL navigation) and no scripting, annotation, link
// or form layer is created: pdf.js only draws each page onto a <canvas>. Eval, XFA and range/stream fetching are off.
// Rendering is bounded: at most MAX_PAGES (3) pages, one at a time, within a pixel budget per canvas.
export const MAX_PAGES = 3;
const MAX_CANVAS_PIXELS = 4_000_000;

export type RenderResult = { pages: number; shown: number };

export function canvasScale(pageWidth: number, pageHeight: number, cssWidth: number, ratio: number): number {
  const wanted = (Math.max(cssWidth, 100) * Math.min(Math.max(ratio, 1), 2)) / pageWidth;
  const limit = Math.sqrt(MAX_CANVAS_PIXELS / (pageWidth * pageHeight));
  return Math.min(wanted, limit);
}

export async function renderOriginalPages(bytes: Uint8Array, container: HTMLElement, signal: AbortSignal): Promise<RenderResult> {
  const pdfjs = await import("pdfjs-dist");
  // Bundled as a classic same-origin worker script (a `.mjs` asset would be served without a script type and blocked).
  const Worker = (await import("pdfjs-dist/build/pdf.worker.min.mjs?worker")).default;
  pdfjs.GlobalWorkerOptions.workerPort = new Worker();
  const task = pdfjs.getDocument({
    data: bytes.slice(),
    isEvalSupported: false,
    enableXfa: false,
    disableAutoFetch: true,
    disableStream: true,
    disableRange: true,
    stopAtErrors: false,
    verbosity: 0,
  });
  try {
    const doc = await task.promise;
    const shown = Math.min(doc.numPages, MAX_PAGES);
    container.replaceChildren();
    for (let number = 1; number <= shown; number++) {
      if (signal.aborted) throw new DOMException("Aborted", "AbortError");
      const page = await doc.getPage(number);
      const base = page.getViewport({ scale: 1 });
      const ratio = globalThis.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: canvasScale(base.width, base.height, container.clientWidth || 600, ratio) });
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.className = "original-page";
      canvas.setAttribute("role", "img");
      canvas.setAttribute("aria-label", `Original page ${number} of ${doc.numPages}`);
      container.append(canvas);
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas is not available");
      await page.render({ canvasContext: context, viewport }).promise;
      page.cleanup();
    }
    return { pages: doc.numPages, shown };
  } finally {
    void task.destroy();
  }
}
