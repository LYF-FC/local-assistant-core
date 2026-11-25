import { useEffect, useRef, useState } from "react";
import { renderOriginalPages } from "./original-pages";

export default function OriginalPages({ bytes, onClose }: { bytes: Uint8Array; onClose: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<{ phase: "drawing" | "done" | "error"; pages?: number; shown?: number }>({ phase: "drawing" });
  useEffect(() => {
    const control = new AbortController(); // Hide, a new document or unmount aborts the render and terminates the worker
    setState({ phase: "drawing" });
    if (host.current)
      renderOriginalPages(bytes, host.current, control.signal)
        .then(r => { if (!control.signal.aborted) setState({ phase: "done", ...r }); })
        .catch(() => { if (!control.signal.aborted) setState({ phase: "error" }); });
    return () => control.abort();
  }, [bytes]);
  return <section aria-label="Original pages" className="original-pages">
    <h4>Original (rendered pages)</h4>
    <p>Up to the first 3 pages are drawn as images in this page only. Nothing is saved or downloaded, and no PDF script, link or form is run. Reading a PDF in the browser is not verified confinement; do not treat it as safe.</p>
    {state.phase === "drawing" && <p role="status">Drawing the original pages…</p>}
    {state.phase === "error" && <p role="alert">The original could not be shown here (it may be damaged, encrypted or too large to draw). It is unchanged and still kept; use the acknowledged download instead.</p>}
    {state.phase === "done" && state.pages !== undefined && state.shown !== undefined && state.pages > state.shown && <p role="status">Showing the first {state.shown} of {state.pages} pages.</p>}
    <div ref={host} className="original-pages-canvases" />
    <button onClick={onClose}>Hide original pages</button>
  </section>;
}
