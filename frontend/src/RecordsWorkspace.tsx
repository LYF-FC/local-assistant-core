import { useMemo, useState } from "react";
import type { Session } from "./api";
import { privateFirstScopes } from "./scope-preference";
import DiscoveryPanel from "./DiscoveryPanel";
import MemoryPanel from "./MemoryPanel";
import ContextPanel from "./ContextPanel";
import RemindersPanel from "./RemindersPanel";
import DocumentsPanel from "./DocumentsPanel";
import TasksPanel from "./TasksPanel";
import WorkPanel from "./WorkPanel";

export default function RecordsWorkspace(props: { session: Session; onUnauthorized: () => void }) {
  const session = useMemo(() => ({ ...props.session, user: { ...props.session.user, scopes: privateFirstScopes(props.session.user.scopes) } }), [props.session]);
  const panelProps = { ...props, session };
  const [view, setView] = useState<"memory" | "discovery" | "context" | "work" | "tasks" | "reminders" | "documents">("memory");
  return <><nav aria-label="Local records" className="memory-actions records-nav"><button aria-pressed={view === "documents"} onClick={() => setView("documents")}>Documents</button><button aria-pressed={view === "reminders"} onClick={() => setView("reminders")}>My reminders</button><button aria-pressed={view === "tasks"} onClick={() => setView("tasks")}>Tasks and agenda</button><button aria-pressed={view === "memory"} onClick={() => setView("memory")}>Memory</button><button aria-pressed={view === "discovery"} onClick={() => setView("discovery")}>Discovery</button><button aria-pressed={view === "context"} onClick={() => setView("context")}>Context preview</button><button aria-pressed={view === "work"} onClick={() => setView("work")}>Work Companion</button></nav>
    <p className="hint">Switching views discards unsaved drafts and reloads current records.</p>
    {view === "documents" ? <DocumentsPanel {...panelProps} /> : view === "reminders" ? <RemindersPanel {...panelProps} /> : view === "tasks" ? <TasksPanel {...panelProps} /> : view === "memory" ? <MemoryPanel {...panelProps} /> : view === "discovery" ? <DiscoveryPanel {...panelProps} /> : view === "context" ? <ContextPanel {...panelProps} /> : <WorkPanel {...panelProps} />}</>;
}
