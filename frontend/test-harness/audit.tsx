// Isolated synthetic browser test entry; not part of the production build or authentication flow.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import AuditSummarySection from "../src/AuditSummarySection";
import "../src/styles.css";
function Harness() {
  const [signedOut, setSignedOut] = useState(0);
  const session = { user: { id: "33333333-3333-4333-8333-333333333333", display_name: "Synthetic browser actor", scopes: ["household_shared", "technical_admin"] }, csrfToken: "synthetic-component-csrf-" + "0".repeat(40) };
  return <main className="shell"><h1>Synthetic audit summary component test</h1><p>Mocked API data only. This entry does not test or alter product sign-in or HTTPS.</p>
    <AuditSummarySection session={session} onUnauthorized={() => setSignedOut(value => value + 1)} />
    <output aria-label="Navigation record" data-signed-out={signedOut}>Signed out {signedOut}</output></main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
