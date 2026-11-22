import type {Document} from "./documents-api";
import type {Receipt} from "./invoices-api";
export const states=["pending","unknown","filed","failed","cancelled"] as const;
export type FilingState=typeof states[number];
export type Filing={id:string;document_id:string|null;owner_id:string;scope:Document["scope"];destination:"synthetic";state:FilingState;revision:number;plan_revision:number|null;source_revision:number|null;attempts:number;next_attempt_at:string|null;resolved_at:string|null;reason:string|null;created_at:string;updated_at:string;scrubbed:boolean};
export type Listing={items:Filing[];next_cursor:string|null;notice:string;checked_at:string};
export type Event={revision:number;operation:string;recorded_at:string;snapshot:Filing|null};
export type Events={execution_id:string;items:Event[];next_cursor:number|null};
export type Created={replayed:boolean;filing:Filing};
export class FilingError extends Error{constructor(public status:number){super(status===409?"The source, review or plan changed, or this destination is already reserved. Reload the document and review the plan before requesting again.":status===429?"Too many requests. Wait before trying again.":"Synthetic filing data is unavailable or was refused.");}}
const obj=(v:unknown):v is Record<string,unknown>=>typeof v==="object"&&v!==null&&!Array.isArray(v);
const uuid=(v:unknown):v is string=>typeof v==="string"&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(v);
const int=(v:unknown,min=1):v is number=>Number.isSafeInteger(v)&&(v as number)>=min&&(v as number)<=2147483647;
const date=(v:unknown):v is string=>typeof v==="string"&&v.length<=40&&Number.isFinite(Date.parse(v));
const maybeDate=(v:unknown):boolean=>v===null||date(v);
const reasons=/^[a-z_]{1,48}$/;
function invalid():never{throw new Error("Invalid synthetic filing response");}
export function parseFiling(v:unknown,doc:Document,historical=false,owner:string=doc.owner_id):Filing{
 if(!obj(v)||!uuid(v.id)||!uuid(v.owner_id)||v.scope!==doc.scope||v.destination!=="synthetic"||!states.includes(v.state as FilingState)||!int(v.revision)||!int(v.attempts,0)||v.attempts>3||!maybeDate(v.next_attempt_at)||!maybeDate(v.resolved_at)||!(v.reason===null||(typeof v.reason==="string"&&reasons.test(v.reason)))||!date(v.created_at)||!date(v.updated_at)||(historical?v.scrubbed!==undefined:typeof v.scrubbed!=="boolean"))invalid();
 if(v.owner_id!==owner)invalid();
 if(v.scrubbed){if(v.document_id!==null||v.plan_revision!==null||v.source_revision!==null)invalid();}
 else if(v.document_id!==doc.id||!int(v.plan_revision)||!int(v.source_revision))invalid();
 const final=v.state==="filed"||v.state==="failed"||v.state==="cancelled";
 if(final!==(v.resolved_at!==null))invalid();
 return {...v,scrubbed:v.scrubbed===true} as Filing;
}
async function send(path:string,body:object,csrf:string,signal:AbortSignal):Promise<unknown>{const r=await fetch(`/api/v1/filing/${path}`,{method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},signal,body:JSON.stringify(body)});if(!r.ok)throw new FilingError(r.status);return r.json();}
export async function requestFiling(doc:Document,receipt:Receipt,csrf:string,signal:AbortSignal):Promise<Created>{
 if(receipt.review_revision===null||receipt.status!=="reviewed")throw new FilingError(409);
 const v=await send("request",{scope:doc.scope,document_id:doc.id,expected_document_revision:doc.revision,expected_review_revision:receipt.review_revision,acknowledge_synthetic_destination:true,acknowledge_exact_plan:true},csrf,signal);
 if(!obj(v)||v.schema_version!==1||typeof v.replayed!=="boolean")invalid();
 const filing=parseFiling(v.filing,doc);
 if(filing.scrubbed||filing.plan_revision!==receipt.review_revision||filing.source_revision!==doc.revision)invalid();
 return {replayed:v.replayed,filing};
}
// `caller` is the signed-in user: the server lists only the caller's own filings, so for anyone but the document owner the list is empty.
export async function queryFilings(doc:Document,csrf:string,signal:AbortSignal,caller:string=doc.owner_id):Promise<Listing>{
 const v=await send("query",{scope:doc.scope,state:"all",document_id:doc.id},csrf,signal);
 if(!obj(v)||v.schema_version!==1||v.scope!==doc.scope||v.owner_id!==caller||v.state!=="all"||!date(v.checked_at)||typeof v.notice!=="string"||v.notice.length>200||!Array.isArray(v.items)||v.items.length>25||!(v.next_cursor===null||uuid(v.next_cursor)))invalid();
 const items=v.items.map(i=>parseFiling(i,doc,false,caller));
 if(caller!==doc.owner_id&&items.length>0)invalid();
 if(new Set(items.map(i=>i.id)).size!==items.length)invalid();
 return {items,next_cursor:v.next_cursor as string|null,notice:v.notice,checked_at:v.checked_at};
}
export async function filingHistory(doc:Document,filing:Filing,after:number,csrf:string,signal:AbortSignal):Promise<Events>{
 const v=await send("history",{scope:doc.scope,execution_id:filing.id,after},csrf,signal);
 if(!obj(v)||v.schema_version!==1||v.execution_id!==filing.id||!Array.isArray(v.items)||v.items.length>25||!(v.next_cursor===null||int(v.next_cursor)))invalid();
 let last=after;
 const items=v.items.map(e=>{if(!obj(e)||!int(e.revision)||e.revision<=last||typeof e.operation!=="string"||!/^[a-z_]{1,32}$/.test(e.operation)||!date(e.recorded_at))invalid();last=e.revision as number;const snapshot=e.snapshot===null?null:parseFiling(e.snapshot,doc,true);if(snapshot&&(snapshot.id!==filing.id||snapshot.revision!==e.revision))invalid();return {revision:e.revision as number,operation:e.operation as string,recorded_at:e.recorded_at as string,snapshot};});
 return {execution_id:filing.id,items,next_cursor:v.next_cursor as number|null};
}
export async function cancelFiling(doc:Document,filing:Filing,csrf:string,signal:AbortSignal):Promise<Filing>{
 const v=await send("cancel",{scope:doc.scope,execution_id:filing.id,expected_revision:filing.revision},csrf,signal);
 if(!obj(v)||v.schema_version!==1)invalid();
 const next=parseFiling(v.filing,doc);
 if(next.id!==filing.id||next.state!=="cancelled")invalid();
 return next;
}
