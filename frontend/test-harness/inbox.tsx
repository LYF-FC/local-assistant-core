// Isolated synthetic browser test entry; not part of the production build or authentication flow.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import AttentionInboxPanel from "../src/AttentionInboxPanel";
import type { Open } from "../src/attention-inbox";
import "../src/styles.css";
function Harness() {
  const [opened, setOpened] = useState<Open[]>([]), [searched, setSearched] = useState(0), [signedOut, setSignedOut] = useState(0);
  const session = { user: { id: "22222222-2222-4222-8222-222222222222", display_name: "Synthetic browser actor", scopes: ["member_a_private", "household_shared"] }, csrfToken: "synthetic-component-csrf-" + "0".repeat(40) };
  return <main className="shell"><h1>Synthetic attention inbox component test</h1><p>Mocked API data only. This entry does not test or alter product sign-in or HTTPS.</p>
    <AttentionInboxPanel session={session} onUnauthorized={() => setSignedOut(value => value + 1)} onOpen={target => setOpened(value => [...value, target])} onSearch={() => setSearched(value => value + 1)} />
    <output aria-label="Navigation record" data-opened={JSON.stringify(opened)} data-searched={searched} data-signed-out={signedOut}>Opened {opened.length}; search {searched}; signed out {signedOut}</output></main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
