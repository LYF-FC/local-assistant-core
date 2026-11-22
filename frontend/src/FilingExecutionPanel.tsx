import {useCallback,useEffect,useRef,useState} from "react";
import type {Session} from "./api";
import type {Document} from "./documents-api";
import type {FilingPlan,Receipt} from "./invoices-api";
import * as api from "./filing-api";
import { filingExplanation } from "./filing-reasons";
const POLL_MS=5000,MAX_POLLS=24;
const labels:Record<api.FilingState,string>={pending:"Pending (waiting or in progress)",unknown:"Unknown (outcome being looked up, never repeated blindly)",filed:"Filed in the synthetic metadata destination",failed:"Failed",cancelled:"Cancelled"};
export default function FilingExecutionPanel({document:doc,receipt,plan,session,onUnauthorized}:{document:Document;receipt:Receipt;plan:FilingPlan;session:Session;onUnauthorized:()=>void}){
 const [listing,setListing]=useState<api.Listing|null>(null),[events,setEvents]=useState<Record<string,api.Events>>({}),[intent,setIntent]=useState(false),[limits,setLimits]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState(""),[polls,setPolls]=useState(0);
 const active=useRef<AbortController|null>(null),epoch=useRef(0);
 useEffect(()=>()=>{active.current?.abort();epoch.current++;},[]);
 const run=useCallback(async(action:(s:AbortSignal)=>Promise<void>)=>{active.current?.abort();const ctl=new AbortController(),generation=++epoch.current;active.current=ctl;setBusy(true);setError("");try{await action(ctl.signal);}catch(e){if(ctl.signal.aborted||generation!==epoch.current)return;if(e instanceof api.FilingError&&e.status===401)onUnauthorized();setError(e instanceof api.FilingError?e.message:"Synthetic filing data is invalid. Reload the document before repeating a request.");}finally{if(!ctl.signal.aborted&&generation===epoch.current)setBusy(false);}},[onUnauthorized]);
 const refresh=useCallback(()=>{void run(async s=>{const l=await api.queryFilings(doc,session.csrfToken,s,session.user.id);if(!s.aborted)setListing(l);});},[run,doc,session.csrfToken,session.user.id]);
 // The panel appears only after the invoice review is loaded and a plan is approved; reading its own filings then is a
 // read-only query, so the status (waiting, filed, failed) is shown without a second click and the request form is
 // never offered before we know whether this exact request already exists.
 useEffect(()=>{refresh();},[refresh]);
 const open=listing?.items.some(i=>i.state==="pending"||i.state==="unknown")??false;
 useEffect(()=>{if(!open||busy||polls>=MAX_POLLS)return;const t=setTimeout(()=>{setPolls(n=>n+1);refresh();},POLL_MS);return()=>clearTimeout(t);},[open,busy,polls,refresh]);
 function request(){void run(async s=>{const c=await api.requestFiling(doc,receipt,session.csrfToken,s);if(s.aborted)return;setNotice(c.replayed?"This exact request already existed; nothing new was started.":"Request recorded. A separate worker applies it; this page only shows its status.");setIntent(false);setLimits(false);setPolls(0);const l=await api.queryFilings(doc,session.csrfToken,s,session.user.id);if(!s.aborted)setListing(l);});}
 function inspect(f:api.Filing){void run(async s=>{const h=await api.filingHistory(doc,f,0,session.csrfToken,s);if(!s.aborted)setEvents(v=>({...v,[f.id]:h}));});}
 function cancel(f:api.Filing){void run(async s=>{await api.cancelFiling(doc,f,session.csrfToken,s);if(s.aborted)return;setNotice("Unstarted request cancelled. No filing effect occurred.");const l=await api.queryFilings(doc,session.csrfToken,s,session.user.id);if(!s.aborted)setListing(l);});}
 const isOwner=doc.can_edit&&doc.owner_id===session.user.id;
 const mine=listing?.items.find(i=>i.plan_revision===receipt.review_revision&&i.source_revision===doc.revision);
 return <section aria-label="Synthetic filing execution"><h4>Synthetic filing execution</h4>
 <p>Plan approval authorized nothing. A filing needs this separate request, bound to the exact saved source, plan and destination shown below. The destination is a <strong>synthetic metadata simulation</strong> for the local rehearsal: it records filing identity, logical path, SHA-256 and size. It does not copy the invoice and writes no real folder, share or NAS.</p>
 <dl><dt>Document</dt><dd><code>{doc.id}</code> · source revision {doc.revision}</dd><dt>Approved plan</dt><dd>review revision {receipt.review_revision} · <code>{plan.relative_path}</code></dd><dt>Original SHA-256</dt><dd><code>{plan.source_sha256}</code></dd><dt>Destination</dt><dd>Synthetic metadata destination (simulation)</dd></dl>
 {isOwner&&listing&&!mine&&<fieldset disabled={busy}><legend>Request this exact filing</legend><label><input type="checkbox" checked={intent} onChange={e=>setIntent(e.target.checked)}/>I authorize one filing of exactly this saved source and approved plan to the synthetic metadata destination.</label><label><input type="checkbox" checked={limits} onChange={e=>setLimits(e.target.checked)}/>I understand this simulates a destination: nothing is copied and no real folder exists.</label><button disabled={!intent||!limits} onClick={request}>Request synthetic filing</button></fieldset>}
 {mine&&<p>A request for this exact source and plan exists (state: {mine.state}).</p>}
 <button disabled={busy} onClick={refresh}>Refresh filing status</button>
 {busy&&<p role="status">Checking synthetic filing status…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 {listing&&<><p>{listing.notice} Checked {listing.checked_at}.</p>{listing.items.length===0&&<p>{isOwner?"No filing requested for this document.":"You have no filing of your own for this document."}</p>}{listing.next_cursor&&<p>Only the first 25 filings are shown; older ones are not listed here.</p>}{!isOwner&&<p>Only the document owner can request, cancel or list filings of this document; this view shows only your own.</p>}<ul>{listing.items.map(f=><li key={f.id}><p>Filing <code>{f.id}</code>: <strong>{labels[f.state]}</strong> · attempts {f.attempts} · plan revision {f.plan_revision??"scrubbed"} · source revision {f.source_revision??"scrubbed"}{f.plan_revision!==receipt.review_revision||f.source_revision!==doc.revision?" (an earlier source or plan)":""}{f.reason?` · reason: ${f.reason.replaceAll("_"," ")}`:""}</p>
 <p role="status">{filingExplanation(f)}</p>
 <button disabled={busy} onClick={()=>inspect(f)}>Show filing history {f.id.slice(0,8)}</button>{isOwner&&f.state==="pending"&&f.attempts===0&&<button disabled={busy} onClick={()=>cancel(f)}>Cancel unstarted filing {f.id.slice(0,8)}</button>}
 {events[f.id]?.next_cursor!=null&&<p>Only the first 25 history entries are shown.</p>}{events[f.id]&&<ol aria-label={`Filing history ${f.id.slice(0,8)}`}>{events[f.id].items.map(e=><li key={e.revision}>Revision {e.revision}: {e.operation.replaceAll("_"," ")} · {e.recorded_at}{e.snapshot?` · ${e.snapshot.state}`:""}</li>)}</ol>}</li>)}</ul></>}
 </section>;
}
