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
import DailyOverviewPanel from "./DailyOverviewPanel";
import type { Destination } from "./daily-overview";
import FinancePanel from "./FinancePanel";
import WorkPanel from "./WorkPanel";

export default function RecordsWorkspace(props: { session: Session; onUnauthorized: () => void }) {
  const session = useMemo(() => ({ ...props.session, user: { ...props.session.user, scopes: privateFirstScopes(props.session.user.scopes) } }), [props.session]);
  const panelProps = { ...props, session };
  const [documentTarget,setDocumentTarget]=useState<Document|null>(null);
  const [view, setView] = useState<"memory" | "discovery" | "context" | "work" | "tasks" | "reminders" | "documents" | "answers" | "calendar" | "routines" | "installation" | "overview" | "finance">("memory");
  const [destination,setDestination]=useState<Destination|null>(null);
  function chooseView(next:typeof view){setDocumentTarget(null);setDestination(null);setView(next);}
  function openOverviewTarget(target:Destination){const scope=target.view==="calendar"?target.selection.scope:target.scope;if(!session.user.scopes.includes(scope))return;setDocumentTarget(target.view==="documents"?target.document??null:null);setDestination(target);setView(target.view);}
  return <><nav aria-label="Local records" className="memory-actions records-nav">{session.user.scopes.includes("finance_private") && <button aria-pressed={view === "finance"} onClick={()=>chooseView("finance")}>Financial register</button>}<button aria-pressed={view === "overview"} onClick={()=>chooseView("overview")}>Daily overview</button>{session.user.scopes.includes("technical_admin") && <button aria-pressed={view === "installation"} onClick={()=>chooseView("installation")}>Installation setup</button>}<button aria-pressed={view === "routines"} onClick={()=>chooseView("routines")}>Recurring routines</button><button aria-pressed={view === "calendar"} onClick={()=>chooseView("calendar")}>Calendar and briefing</button><button aria-pressed={view === "documents"} onClick={() => chooseView("documents")}>Documents</button><button aria-pressed={view === "answers"} onClick={()=>chooseView("answers")}>Document answers</button><button aria-pressed={view === "reminders"} onClick={() => chooseView("reminders")}>My reminders</button><button aria-pressed={view === "tasks"} onClick={() => chooseView("tasks")}>Tasks and agenda</button><button aria-pressed={view === "memory"} onClick={() => chooseView("memory")}>Memory</button><button aria-pressed={view === "discovery"} onClick={() => chooseView("discovery")}>Discovery</button><button aria-pressed={view === "context"} onClick={() => chooseView("context")}>Context preview</button><button aria-pressed={view === "work"} onClick={() => chooseView("work")}>Work Companion</button></nav>
    <p className="hint">Switching views discards unsaved drafts and reloads current records.</p>
    {view === "finance" ? <FinancePanel {...panelProps} /> : view === "overview" ? <DailyOverviewPanel {...panelProps} onOpen={openOverviewTarget} /> : view === "installation" ? <InstallationPanel {...panelProps} /> : view === "routines" ? <RoutinesPanel {...panelProps} /> : view === "calendar" ? <CalendarPanel {...panelProps} initialScope={destination?.view==="calendar"?destination.selection.scope:undefined} initialDay={destination?.view==="calendar"?destination.selection.day:undefined} initialTimezone={destination?.view==="calendar"?destination.selection.timezone:undefined} /> : view === "answers" ? <AnswersPanel {...panelProps} onOpenSource={document=>{setDestination(null);setDocumentTarget(document);setView("documents");}} /> : view === "documents" ? <DocumentsPanel {...panelProps} initialDocument={documentTarget??undefined} initialScope={destination?.view==="documents"?destination.scope:undefined} /> : view === "reminders" ? <RemindersPanel {...panelProps} initialScope={destination?.view==="reminders"?destination.scope:undefined} showAllInitially={destination?.view==="reminders"} /> : view === "tasks" ? <TasksPanel {...panelProps} initialScope={destination?.view==="tasks"?destination.scope:undefined} /> : view === "memory" ? <MemoryPanel {...panelProps} /> : view === "discovery" ? <DiscoveryPanel {...panelProps} /> : view === "context" ? <ContextPanel {...panelProps} /> : <WorkPanel {...panelProps} />}</>;
}
