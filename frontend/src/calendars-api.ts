import {taskScopes,parseTask,type TaskScope,type ActiveTask} from "./tasks-api";
export type CalendarScope=TaskScope;
export {taskScopes as calendarScopes};
export type Occurrence={uid:string;recurrence_id:string;sequence:number;title:string;description:string;status:"confirmed"|"tentative"|"cancelled";timezone:string}&({kind:"timed";start:string;end:string}|{kind:"all_day";start_date:string;end_date:string});
export type Window={complete:true;cursor:string;fetched_at:string;timezone:string;start_date:string;end_date:string;events:Occurrence[]};
type Status="setup_required"|"ready"|"offline"|"failed";
export type Data={label:string;status:Status;window:Window|null;attempt_at:string|null;changes:{added:number;updated:number;removed_in_coverage:number;outside_coverage_unknown:number}|null};
export type SourceMeta={id:string;owner_id:string;scope:CalendarScope;state:"active"|"forgotten";revision:number;created_at:string;updated_at:string;can_edit:boolean};
export type Source=SourceMeta&{data:Data|null};
export type SyncSummary={status:"never"|"ok"|"retry_wait"|"failed"|"blocked";last_success_at:string|null;blocked_reason:string|null;last_error_code:string|null};
export type Card=SourceMeta&{label:string;status:Status;fetched_at:string|null;start_date:string|null;end_date:string|null;timezone:string|null;mode?:"provider";sync?:SyncSummary};
export type SourceState="available"|"stale"|"unavailable"|"blocked"|"unknown_coverage"|"limit_reached";
export const sourceStates:readonly SourceState[]=["available","stale","unavailable","blocked","unknown_coverage","limit_reached"];
export type Limit={shown:number;truncated:boolean;omitted_at_least:number};
export type Limits={sources:Limit;events:Limit;tasks:Limit;memories:Limit;unreadable_items:number};
export type DaySummary={day:string;start_at:string;end_at:string;events:number};
export type SyncResult={source_id:string;provider:{status:string;attempts:number;applied_seq:number;last_success_at:string|null;next_attempt_at:string|null;last_error_code:string|null;blocked_reason:string|null};sync?:{outcome:string;reason:string|null;pages:number;changes:number}};
export type CalendarPage={schema_version:1;scope:CalendarScope;items:Card[];next_cursor:string|null};
export type History={schema_version:1;source_id:string;scope:CalendarScope;current_revision:number;state:"active"|"forgotten";managed_copy:false|null;items:{revision:number;actor_id:string;created_at:string;snapshot:Data|null}[];next_cursor:number|null};
export type AgendaEvent=Occurrence&{id:string;source_id:string;source_revision:number;source_label:string;stale:boolean;availability:Status;possible_conflict:boolean;recurring?:boolean;exception?:"none"|"modified";days?:string[];continues?:boolean;possible_duplicate_of?:string[];source_state?:SourceState;as_of?:string|null};
export type AgendaCalendar=Omit<Card,"mode"|"sync">&{covers_day:boolean;stale:boolean;mode?:"manual"|"provider";source_state?:SourceState;as_of?:string|null;unreadable?:number;blocked_reason?:string|null};
export type Briefing={schema_version:1|2;scope:CalendarScope;day:string;timezone:string;checked_at:string;valid_until:string;start_at:string;end_at:string;horizon_days?:number;days?:DaySummary[];cancelled_count?:number;limits?:Limits;calendars:AgendaCalendar[];events:AgendaEvent[];tasks:(ActiveTask&{overdue:boolean})[];memories:{id:string;revision:number;title:string;source_reference:string}[];truncated:{calendars:boolean;events:boolean;tasks:boolean;memories:boolean};notice:string};
const obj=(v:unknown):v is Record<string,unknown>=>typeof v==="object"&&v!==null&&!Array.isArray(v);
const uuid=(v:unknown):v is string=>typeof v==="string"&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(v);
const text=(v:unknown,max:number,min=0):v is string=>typeof v==="string"&&Array.from(v).length>=min&&Array.from(v).length<=max;
const int=(v:unknown,max=2147483647,min=0):v is number=>Number.isSafeInteger(v)&&(v as number)>=min&&(v as number)<=max;
const instant=(v:unknown):v is string=>typeof v==="string"&&/T.*(Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v));
const date=(v:unknown):v is string=>typeof v==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;
const timezone=(v:unknown):v is string=>{try{if(!text(v,64,1))return false;new Intl.DateTimeFormat("en",{timeZone:v});return true;}catch{return false;}};
const status=(v:unknown):v is Status=>["setup_required","ready","offline","failed"].includes(v as string);
function invalid():never{throw new Error("Invalid calendar response or import");}
function occurrence(v:unknown):Occurrence{
 if(!obj(v)||!text(v.uid,128,1)||!text(v.recurrence_id,128)||!int(v.sequence)||!text(v.title,160,1)||!text(v.description,512)||!["confirmed","tentative","cancelled"].includes(v.status as string)||!timezone(v.timezone))invalid();
 const common={uid:v.uid,recurrence_id:v.recurrence_id,sequence:v.sequence,title:v.title,description:v.description,status:v.status as Occurrence["status"],timezone:v.timezone};
 if(v.kind==="timed"&&instant(v.start)&&instant(v.end)&&Date.parse(v.end)>Date.parse(v.start))return {...common,kind:"timed",start:v.start,end:v.end};
 if(v.kind==="all_day"&&date(v.start_date)&&date(v.end_date)&&v.start_date<v.end_date)return {...common,kind:"all_day",start_date:v.start_date,end_date:v.end_date};
 invalid();
}
export function parseWindow(v:unknown):Window{
 if(!obj(v)||v.complete!==true||!text(v.cursor,128,1)||!instant(v.fetched_at)||!timezone(v.timezone)||!date(v.start_date)||!date(v.end_date)||v.end_date<=v.start_date||Date.parse(v.end_date)-Date.parse(v.start_date)>31*86400000||!Array.isArray(v.events)||v.events.length>100||new TextEncoder().encode(JSON.stringify(v)).length>65536)invalid();
 const events=v.events.map(occurrence);if(new Set(events.map(e=>JSON.stringify([e.uid,e.recurrence_id]))).size!==events.length)invalid();
 return {complete:true,cursor:v.cursor,fetched_at:v.fetched_at,timezone:v.timezone,start_date:v.start_date,end_date:v.end_date,events};
}
export function previewWindow(raw:string):Window{
 if(new TextEncoder().encode(raw).length>70000)invalid();const v:unknown=JSON.parse(raw);
 if(!obj(v)||Object.keys(v).some(k=>!["complete","cursor","fetched_at","timezone","start_date","end_date","events"].includes(k)))invalid();
 if(Array.isArray(v.events))for(const e of v.events){if(!obj(e)||Object.keys(e).some(k=>!["uid","recurrence_id","sequence","title","description","status","timezone","kind",...(e.kind==="timed"?["start","end"]:["start_date","end_date"])].includes(k)))invalid();}
 return parseWindow(v);
}
function data(v:unknown):Data{
 if(!obj(v)||!text(v.label,160,1)||!status(v.status)||!(v.attempt_at===null||instant(v.attempt_at)))invalid();
 const window=v.window===null?null:parseWindow(v.window);
 if(v.status==="ready"&&!window)invalid();
 let changes:Data["changes"]=null;
 if(v.changes!==null){const c=v.changes;if(!obj(c)||!int(c.added,100)||!int(c.updated,100)||!int(c.removed_in_coverage,100)||!int(c.outside_coverage_unknown,100))invalid();changes={added:c.added,updated:c.updated,removed_in_coverage:c.removed_in_coverage,outside_coverage_unknown:c.outside_coverage_unknown};}
 return {label:v.label,status:v.status,window,attempt_at:v.attempt_at,changes};
}
function meta(v:unknown,scope:CalendarScope):SourceMeta{
 if(!obj(v)||!uuid(v.id)||!uuid(v.owner_id)||v.scope!==scope||!["active","forgotten"].includes(v.state as string)||!int(v.revision,101,1)||!instant(v.created_at)||!instant(v.updated_at)||typeof v.can_edit!=="boolean")invalid();
 return {id:v.id,owner_id:v.owner_id,scope,state:v.state as SourceMeta["state"],revision:v.revision,created_at:v.created_at,updated_at:v.updated_at,can_edit:v.can_edit};
}
export function parseSource(v:unknown,scope:CalendarScope):Source{
 const m=meta(v,scope);if(!obj(v)||(m.state==="forgotten"&&v.data!==null)||(m.state==="active"&&v.data===null))invalid();return {...m,data:v.data===null?null:data(v.data)};
}
function card(v:unknown,scope:CalendarScope):Card{
 const m=meta(v,scope);if(!obj(v)||m.state!=="active"||!text(v.label,160,1)||!status(v.status))invalid();
 if(!((v.fetched_at===null&&v.start_date===null&&v.end_date===null&&v.timezone===null)||(instant(v.fetched_at)&&date(v.start_date)&&date(v.end_date)&&v.start_date<v.end_date&&timezone(v.timezone))))invalid();
 const result:Card={...m,label:v.label,status:v.status,fetched_at:v.fetched_at as string|null,start_date:v.start_date as string|null,end_date:v.end_date as string|null,timezone:v.timezone as string|null};
 if(v.mode!==undefined){const s=v.sync;if(v.mode!=="provider"||!obj(s)||!["never","ok","retry_wait","failed","blocked"].includes(s.status as string)||!(s.last_success_at===null||instant(s.last_success_at))||!(s.blocked_reason===null||text(s.blocked_reason,32,1))||!(s.last_error_code===null||text(s.last_error_code,32,1)))invalid();result.mode="provider";result.sync={status:s.status as SyncSummary["status"],last_success_at:s.last_success_at as string|null,blocked_reason:s.blocked_reason as string|null,last_error_code:s.last_error_code as string|null};}
 return result;
}
function limit(v:unknown):Limit{if(!obj(v)||!int(v.shown,100)||typeof v.truncated!=="boolean"||!int(v.omitted_at_least,1000000)||(v.omitted_at_least>0&&!v.truncated))invalid();return {shown:v.shown,truncated:v.truncated,omitted_at_least:v.omitted_at_least};}
export function parseBriefing(v:unknown,scope:CalendarScope,day:string,tz:string):Briefing{
 if(!obj(v)||![1,2].includes(v.schema_version as number)||v.scope!==scope||v.day!==day||v.timezone!==tz||!date(day)||!timezone(tz)||!instant(v.checked_at)||!instant(v.valid_until)||!instant(v.start_at)||!instant(v.end_at)||Date.parse(v.end_at)<=Date.parse(v.start_at)||Date.parse(v.valid_until)<=Date.now()||Date.parse(v.valid_until)-Date.parse(v.checked_at)>60000||Date.parse(v.checked_at)>Date.now()+5000||!Array.isArray(v.calendars)||v.calendars.length>25||!Array.isArray(v.events)||v.events.length>100||!Array.isArray(v.tasks)||v.tasks.length>25||!Array.isArray(v.memories)||v.memories.length>10||!obj(v.truncated)||!["calendars","events","tasks","memories"].every(k=>typeof (v.truncated as Record<string,unknown>)[k]==="boolean")||!text(v.notice,1000))invalid();
 const v2=v.schema_version===2;
 const calendars:AgendaCalendar[]=v.calendars.map(c=>{const {mode:_mode,sync:_sync,...m}=card(obj(c)?{...c,mode:undefined,sync:undefined}:c,scope);if(!obj(c)||typeof c.covers_day!=="boolean"||typeof c.stale!=="boolean")invalid();const base:AgendaCalendar={...m,covers_day:c.covers_day,stale:c.stale};
  if(!v2)return base;
  if(!["manual","provider"].includes(c.mode as string)||!sourceStates.includes(c.source_state as SourceState)||!(c.as_of===null||instant(c.as_of))||!int(c.unreadable,1000000)||(c.unreadable>0&&c.source_state!=="unknown_coverage")||!(c.mode==="provider"||c.blocked_reason===undefined)||!(c.blocked_reason===undefined||c.blocked_reason===null||text(c.blocked_reason,32,1)))invalid();
  return {...base,mode:c.mode as "manual"|"provider",source_state:c.source_state as SourceState,as_of:c.as_of as string|null,unreadable:c.unreadable,blocked_reason:c.blocked_reason as string|null|undefined};});
 const events=v.events.map(e=>{const o=occurrence(e);if(!obj(e)||!uuid(e.id)||!uuid(e.source_id)||!int(e.source_revision,100,1)||!text(e.source_label,160,1)||typeof e.stale!=="boolean"||typeof e.possible_conflict!=="boolean"||!status(e.availability)||o.status==="cancelled"||!calendars.some(c=>c.id===e.source_id&&c.revision===e.source_revision&&c.label===e.source_label&&c.status===e.availability&&c.stale===e.stale))invalid();const extra:Partial<Pick<AgendaEvent,"recurring"|"exception"|"days"|"continues"|"possible_duplicate_of"|"source_state"|"as_of">>={};
  if(v2){const owner=calendars.find(c=>c.id===e.source_id);if(!owner||e.source_state!==owner.source_state||e.as_of!==owner.as_of)invalid();extra.source_state=owner.source_state;extra.as_of=owner.as_of;if(e.recurring!==undefined){if(typeof e.recurring!=="boolean"||!["none","modified"].includes(e.exception as string))invalid();extra.recurring=e.recurring;extra.exception=e.exception as "none"|"modified";}
   if(!Array.isArray(e.days)||e.days.length<1||e.days.length>7||!e.days.every(date)||typeof e.continues!=="boolean"||e.continues!==(e.days.length>1))invalid();extra.days=e.days as string[];extra.continues=e.continues;
   if(e.possible_duplicate_of!==undefined){if(!Array.isArray(e.possible_duplicate_of)||e.possible_duplicate_of.length<1||e.possible_duplicate_of.length>5||!e.possible_duplicate_of.every(uuid))invalid();extra.possible_duplicate_of=e.possible_duplicate_of as string[];}}
  return {...o,id:e.id,source_id:e.source_id,source_revision:e.source_revision,source_label:e.source_label,stale:e.stale,availability:e.availability,possible_conflict:e.possible_conflict,...extra};});
 const tasks=v.tasks.map(t=>{const parsed=parseTask(t);if(!obj(t)||parsed.state!=="active"||parsed.status!=="open"||parsed.scope!==scope||!parsed.due_at||typeof t.overdue!=="boolean"||Date.parse(parsed.due_at)>=Date.parse(v.end_at as string)||t.overdue!==(Date.parse(parsed.due_at)<Date.parse(v.start_at as string)))invalid();return {...parsed,overdue:t.overdue};});
 const memories=v.memories.map(m=>{if(!obj(m)||!uuid(m.id)||!int(m.revision,2147483647,1)||!text(m.title,160,1)||!text(m.source_reference,512,1))invalid();return {id:m.id,revision:m.revision,title:m.title,source_reference:m.source_reference};});
 for(const list of [calendars,events,tasks,memories])if(new Set(list.map(x=>x.id)).size!==list.length)invalid();
 const result:Briefing={schema_version:v.schema_version as 1|2,scope,day,timezone:tz,checked_at:v.checked_at,valid_until:v.valid_until,start_at:v.start_at,end_at:v.end_at,calendars,events,tasks,memories,truncated:v.truncated as Briefing["truncated"],notice:v.notice};
 if(v2){
  const l=v.limits;if(!obj(l)||!int(l.unreadable_items,1000000)||!int(v.horizon_days,7,1)||!Array.isArray(v.days)||v.days.length!==v.horizon_days||!int(v.cancelled_count,1000000))invalid();
  const limits:Limits={sources:limit(l.sources),events:limit(l.events),tasks:limit(l.tasks),memories:limit(l.memories),unreadable_items:l.unreadable_items};
  const flags=v.truncated as Briefing["truncated"];
  // The version-1 booleans must say exactly what the counts say, and the counts must match what was shown.
  if(flags.calendars!==limits.sources.truncated||flags.events!==limits.events.truncated||flags.tasks!==limits.tasks.truncated||flags.memories!==limits.memories.truncated||limits.sources.shown!==calendars.length||limits.events.shown!==events.length||limits.tasks.shown!==tasks.length||limits.memories.shown!==memories.length||limits.unreadable_items!==calendars.reduce((n,c)=>n+(c.unreadable??0),0))invalid();
  const days:DaySummary[]=v.days.map(d=>{if(!obj(d)||!date(d.day)||!instant(d.start_at)||!instant(d.end_at)||!int(d.events,100))invalid();return {day:d.day,start_at:d.start_at,end_at:d.end_at,events:d.events};});
  result.horizon_days=v.horizon_days as number;result.days=days;result.cancelled_count=v.cancelled_count as number;result.limits=limits;
 }
 return result;
}
export class CalendarError extends Error{constructor(public status:number){super(status===409?"The calendar changed or the snapshot conflicts. Your draft is kept; reload and review before trying again.":status===429?"Calendar storage limit reached. Export existing history; changes are paused. Forgetting remains available.":[401,403,404,410].includes(status)?"Calendar access is no longer available. Reload your session or source list.":status===422?"Check the complete snapshot, dates, timezone, event IDs and sequences.":"Calendar service unavailable. Reload before repeating a change.");}}
async function request(path:string,body:object,csrf:string,signal:AbortSignal):Promise<unknown>{const r=await fetch(`/api/v1/calendars${path}`,{method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",signal,headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(body)});if(!r.ok)throw new CalendarError(r.status);return r.json();}
export async function listSources(scope:CalendarScope,after:string|null,csrf:string,signal:AbortSignal):Promise<CalendarPage>{const v=await request("/query",{scope,after},csrf,signal);if(!obj(v)||v.schema_version!==1||v.scope!==scope||!Array.isArray(v.items)||v.items.length>25||!(v.next_cursor===null||uuid(v.next_cursor)))invalid();const items=v.items.map(i=>card(i,scope));if(items.some((x,i)=>(after!==null&&x.id<=after)||(i>0&&x.id<=items[i-1].id))||(v.next_cursor!==null&&(items.length!==25||v.next_cursor!==items[24].id)))invalid();return {schema_version:1,scope,items,next_cursor:v.next_cursor as string|null};}
export async function createSource(label:string,scope:CalendarScope,csrf:string,signal:AbortSignal){const r=parseSource(await request("",{label,scope},csrf,signal),scope);if(r.revision!==1||!r.can_edit||!r.data||r.data.status!=="setup_required")invalid();return r;}
export async function sourceAction(row:SourceMeta,op:"read"|"import"|"unavailable"|"forget",csrf:string,signal:AbortSignal,values:object={}){const v=parseSource(await request(`/${row.id}/${op}`,{scope:row.scope,...(op==="read"?{}:{expected_revision:row.revision}),...values},csrf,signal),row.scope);if(v.id!==row.id||v.owner_id!==row.owner_id||(op==="forget"?v.state!=="forgotten":v.state!=="active")||(op==="unavailable"||op==="forget"?v.revision!==row.revision+1:v.revision<row.revision))invalid();return v;}
export async function getBriefing(scope:CalendarScope,day:string,tz:string,csrf:string,signal:AbortSignal,horizonDays?:number){return parseBriefing(await request("/briefing",{scope,day,timezone:tz,...(horizonDays===undefined?{}:{horizon_days:horizonDays})},csrf,signal),scope,day,tz);}
export async function syncSource(row:SourceMeta,resync:boolean,csrf:string,signal:AbortSignal):Promise<SyncResult>{const v=await request(`/${row.id}/sync`,{scope:row.scope,resync},csrf,signal);if(!obj(v)||v.source_id!==row.id||!obj(v.provider)||!text(v.provider.status,16,1)||!obj(v.sync)||!text(v.sync.outcome,16,1))invalid();return v as unknown as SyncResult;}
export async function history(row:SourceMeta,after:number,exported:boolean,csrf:string,signal:AbortSignal):Promise<History>{const v=await request(`/${row.id}/${exported?"export":"history"}`,{scope:row.scope,after,...(exported?{acknowledge_copy_limits:true}:{})},csrf,signal);if(!obj(v)||v.schema_version!==1||v.source_id!==row.id||v.scope!==row.scope||!int(v.current_revision,101,1)||!["active","forgotten"].includes(v.state as string)||v.managed_copy!==(exported?false:null)||!Array.isArray(v.items)||v.items.length>5||!(v.next_cursor===null||int(v.next_cursor,101,1)))invalid();const items=v.items.map((item,i)=>{if(!obj(item)||item.revision!==after+i+1||item.actor_id!==row.owner_id||!instant(item.created_at)||item.revision>(v.current_revision as number)||(v.state==="forgotten"?item.snapshot!==null:item.snapshot===null))invalid();return {revision:item.revision as number,actor_id:row.owner_id,created_at:item.created_at,snapshot:item.snapshot===null?null:data(item.snapshot)};});if(v.next_cursor!==null&&(items.length!==5||v.next_cursor!==items[4].revision))invalid();return {schema_version:1,source_id:row.id,scope:row.scope,current_revision:v.current_revision,state:v.state as History["state"],managed_copy:v.managed_copy as false|null,items,next_cursor:v.next_cursor as number|null};}
