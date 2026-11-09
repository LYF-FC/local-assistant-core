import { useMemo, useState } from "react";
import type { Session } from "./api";
import { privateFirstScopes } from "./scope-preference";
import DiscoveryPanel from "./DiscoveryPanel";
import MemoryPanel from "./MemoryPanel";
import ContextPanel from "./ContextPanel";
import RemindersPanel from "./RemindersPanel";
import DocumentsPanel from "./DocumentsPanel";
import TasksPanel from "./TasksPanel";
import RoutinesPanel from "./RoutinesPanel";
import CalendarPanel from "./CalendarPanel";
import AnswersPanel from "./AnswersPanel";
import type { Document } from "./documents-api";
import InstallationPanel from "./InstallationPanel";
import WorkPanel from "./WorkPanel";

export default function RecordsWorkspace(props: { session: Session; onUnauthorized: () => void }) {
  const session = useMemo(() => ({ ...props.session, user: { ...props.session.user, scopes: privateFirstScopes(props.session.user.scopes) } }), [props.session]);
  const panelProps = { ...props, session };
  const [documentTarget,setDocumentTarget]=useState<Document|null>(null);
  const [view, setView] = useState<"memory" | "discovery" | "context" | "work" | "tasks" | "reminders" | "documents" | "answers" | "calendar" | "routines" | "installation">("memory");
  return <><nav aria-label="Local records" className="memory-actions records-nav">{session.user.scopes.includes("technical_admin") && <button aria-pressed={view === "installation"} onClick={()=>setView("installation")}>Installation setup</button>}<button aria-pressed={view === "routines"} onClick={()=>setView("routines")}>Recurring routines</button><button aria-pressed={view === "calendar"} onClick={()=>setView("calendar")}>Calendar and briefing</button><button aria-pressed={view === "documents"} onClick={() => {setDocumentTarget(null);setView("documents");}}>Documents</button><button aria-pressed={view === "answers"} onClick={()=>setView("answers")}>Document answers</button><button aria-pressed={view === "reminders"} onClick={() => setView("reminders")}>My reminders</button><button aria-pressed={view === "tasks"} onClick={() => setView("tasks")}>Tasks and agenda</button><button aria-pressed={view === "memory"} onClick={() => setView("memory")}>Memory</button><button aria-pressed={view === "discovery"} onClick={() => setView("discovery")}>Discovery</button><button aria-pressed={view === "context"} onClick={() => setView("context")}>Context preview</button><button aria-pressed={view === "work"} onClick={() => setView("work")}>Work Companion</button></nav>
    <p className="hint">Switching views discards unsaved drafts and reloads current records.</p>
    {view === "installation" ? <InstallationPanel {...panelProps} /> : view === "routines" ? <RoutinesPanel {...panelProps} /> : view === "calendar" ? <CalendarPanel {...panelProps} /> : view === "answers" ? <AnswersPanel {...panelProps} onOpenSource={document=>{setDocumentTarget(document);setView("documents");}} /> : view === "documents" ? <DocumentsPanel {...panelProps} initialDocument={documentTarget??undefined} /> : view === "reminders" ? <RemindersPanel {...panelProps} /> : view === "tasks" ? <TasksPanel {...panelProps} /> : view === "memory" ? <MemoryPanel {...panelProps} /> : view === "discovery" ? <DiscoveryPanel {...panelProps} /> : view === "context" ? <ContextPanel {...panelProps} /> : <WorkPanel {...panelProps} />}</>;
}
