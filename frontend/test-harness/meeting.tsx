// Isolated synthetic browser test entry; not part of the production build or authentication flow.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import WorkNotesPanel from "../src/WorkNotesPanel";
import "../src/styles.css";
const first = "11111111-1111-4111-8111-111111111111", second = "99999999-9999-4999-8999-999999999999";
function Harness() {
  const [workspace, setWorkspace] = useState(first), [epoch, setEpoch] = useState(0), [signedIn, setSignedIn] = useState(true);
  const session = { user: { id: "88888888-8888-4888-8888-888888888888", display_name: "Synthetic browser actor", scopes: ["technical_admin"] }, csrfToken: "synthetic-component-csrf-" + String(epoch).padStart(40, "0") };
  return <main className="shell"><h1>Synthetic meeting component test</h1><p>Mocked API data only. This entry does not test or alter product sign-in or HTTPS.</p><div className="memory-actions"><button onClick={() => setWorkspace(value => value === first ? second : first)}>Switch test workspace</button><button onClick={() => setEpoch(value => value + 1)}>Reset test session</button></div>{signedIn ? <section className="memory-panel"><WorkNotesPanel key={`${workspace}-${epoch}`} workspace={workspace} session={session} onUnauthorized={() => setSignedIn(false)} /></section> : <p>Test session ended</p>}</main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
