import {afterEach,expect,it,vi} from "vitest";
import * as api from "./calendars-api";
const id="11111111-1111-4111-8111-111111111111",owner="22222222-2222-4222-8222-222222222222",eventId="33333333-3333-4333-8333-333333333333";
const event={kind:"timed",uid:"synthetic",recurrence_id:"",sequence:0,title:"Synthetic event",description:"<script>inert</script>",status:"confirmed",timezone:"UTC",start:"2026-10-25T09:00:00Z",end:"2026-10-25T10:00:00Z"};
const window={complete:true,cursor:"synthetic",fetched_at:"2026-11-08T10:00:00Z",timezone:"UTC",start_date:"2026-10-25",end_date:"2026-10-26",events:[event]};
const source={id,owner_id:owner,scope:"household_shared",state:"active",revision:2,created_at:"2026-11-08T10:00:00Z",updated_at:"2026-11-08T10:00:00Z",can_edit:true,data:{label:"Synthetic calendar",status:"ready",window,attempt_at:"2026-11-08T10:00:00Z",changes:{added:1,updated:0,removed_in_coverage:0,outside_coverage_unknown:0}}};
function briefing(){return {schema_version:1,scope:"household_shared",day:"2026-10-25",timezone:"UTC",checked_at:new Date().toISOString(),valid_until:new Date(Date.now()+55000).toISOString(),start_at:"2026-10-25T00:00:00Z",end_at:"2026-10-26T00:00:00Z",calendars:[{...source,label:"Synthetic calendar",status:"ready",fetched_at:window.fetched_at,start_date:window.start_date,end_date:window.end_date,timezone:"UTC",covers_day:true,stale:true}],events:[{...event,id:eventId,source_id:id,source_revision:2,source_label:"Synthetic calendar",stale:true,availability:"ready",possible_conflict:false}],tasks:[],memories:[],truncated:{calendars:false,events:false,tasks:false,memories:false},notice:"Synthetic scoped snapshot"};}
const parse=(v:unknown)=>api.parseBriefing(v,"household_shared","2026-10-25","UTC");
afterEach(()=>vi.unstubAllGlobals());
it("previews complete bounded snapshots with inert event text",()=>{const value=api.previewWindow(JSON.stringify(window));expect(value.events[0].description).toBe("<script>inert</script>");expect(api.parseSource(source,"household_shared").data?.window?.cursor).toBe("synthetic");});
it.each([{complete:false},{complete:1},{events:[event,event]},{events:Array(101).fill(event)},{end_date:"2027-01-01"},{timezone:"No/Zone"},{start_date:"2026-02-30"},{events:[{...event,sequence:true}]},{events:[{...event,start:"2026-10-25T09:00:00"}]}])("refuses malformed preview %j",change=>{expect(()=>api.previewWindow(JSON.stringify({...window,...change}))).toThrow();});
it("bounds UTF-8 preview bytes",()=>{expect(()=>api.previewWindow("界".repeat(30000))).toThrow();});
it("checks scope, source provenance and expiry before presenting a briefing",()=>{expect(parse(briefing()).events[0].id).toBe(eventId);});
it.each(["scope","expired","long_expiry","source","revision","duplicate","cancelled","availability","truncation","day","zone"])("refuses %s briefing",change=>{const v=briefing();if(change==="scope")v.scope="member_a_private";if(change==="expired")v.valid_until=new Date(Date.now()-1).toISOString();if(change==="long_expiry")v.valid_until=new Date(Date.now()+120000).toISOString();if(change==="source")v.events[0].source_id=owner;if(change==="revision")v.events[0].source_revision=3;if(change==="duplicate")v.events.push(v.events[0]);if(change==="cancelled")v.events[0].status="cancelled";if(change==="availability")v.events[0].availability="offline";if(change==="truncation")(v.truncated as unknown as Record<string,unknown>).events="yes";if(change==="day")v.day="2026-10-26";if(change==="zone")v.timezone="Europe/Paris";expect(()=>parse(v)).toThrow();});
it("uses one protected no-store request and pins the requested briefing",async()=>{const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(briefing())));vi.stubGlobal("fetch",fetch);const signal=new AbortController().signal;await api.getBriefing("household_shared","2026-10-25","UTC","synthetic",signal);expect(fetch).toHaveBeenCalledWith("/api/v1/calendars/briefing",expect.objectContaining({method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",signal,headers:{"Content-Type":"application/json","X-CSRF-Token":"synthetic"}}));expect(fetch).toHaveBeenCalledTimes(1);});
it.each([401,403,409,410,422,429,503])("sanitizes %s without mutation retries",async status=>{const fetch=vi.fn().mockResolvedValue(new Response("Private provider error",{status}));vi.stubGlobal("fetch",fetch);await expect(api.createSource("Synthetic","household_shared","synthetic",new AbortController().signal)).rejects.toBeInstanceOf(api.CalendarError);expect(fetch).toHaveBeenCalledTimes(1);});
it("rejects wrong source receipts",()=>{expect(()=>api.parseSource(source,"member_a_private")).toThrow();expect(()=>api.parseSource({...source,state:"forgotten"},"household_shared")).toThrow();});

// ---- Briefing version 2: per-source states, limits, markers --------------------------------------
const dupId="44444444-4444-4444-8444-444444444444";
function briefingV2(){
 const v=briefing() as Record<string,any>;
 v.schema_version=2;v.horizon_days=2;v.cancelled_count=0;
 v.days=[{day:"2026-10-25",start_at:"2026-10-25T00:00:00Z",end_at:"2026-10-26T00:00:00Z",events:1},{day:"2026-10-26",start_at:"2026-10-26T00:00:00Z",end_at:"2026-10-27T00:00:00Z",events:0}];
 v.end_at="2026-10-27T00:00:00Z";
 v.calendars[0]={...v.calendars[0],mode:"manual",source_state:"stale",as_of:window.fetched_at,unreadable:0};
 v.events[0]={...v.events[0],source_state:"stale",as_of:window.fetched_at,days:["2026-10-25"],continues:false,recurring:true,exception:"modified",possible_duplicate_of:[dupId]};
 v.limits={sources:{shown:1,truncated:false,omitted_at_least:0},events:{shown:1,truncated:false,omitted_at_least:0},tasks:{shown:0,truncated:false,omitted_at_least:0},memories:{shown:0,truncated:false,omitted_at_least:0},unreadable_items:0};
 return v;
}
const parse2=(v:unknown)=>api.parseBriefing(v,"household_shared","2026-10-25","UTC");
it("accepts a version 2 briefing and keeps its states, counts and markers",()=>{const r=parse2(briefingV2());expect(r.schema_version).toBe(2);expect(r.calendars[0]).toMatchObject({mode:"manual",source_state:"stale",unreadable:0});expect(r.events[0]).toMatchObject({recurring:true,exception:"modified",days:["2026-10-25"],possible_duplicate_of:[dupId]});expect(r.limits?.events.shown).toBe(1);expect(r.days).toHaveLength(2);});
it.each(api.sourceStates)("accepts the source state %s",state=>{const v=briefingV2();v.calendars[0].source_state=state;v.events[0].source_state=state;expect(parse2(v).calendars[0].source_state).toBe(state);});
it("keeps a version 1 briefing readable without version 2 fields",()=>{const r=parse(briefing());expect(r.limits).toBeUndefined();expect(r.calendars[0].source_state).toBeUndefined();});
it.each(["state","mode","as_of","unreadable","unreadable_state","horizon","days_length","cancelled","limits_missing","limit_shape","flag_mismatch","shown_mismatch","unreadable_sum","event_state","event_as_of","event_days","continues","duplicate_ids","omitted_without_truncation","provider_blocked_on_manual"])("refuses an inconsistent version 2 briefing: %s",change=>{
 const v=briefingV2();
 if(change==="state")v.calendars[0].source_state="fine";
 if(change==="mode")v.calendars[0].mode="live";
 if(change==="as_of")v.calendars[0].as_of="yesterday";
 if(change==="unreadable")v.calendars[0].unreadable=-1;
 if(change==="unreadable_state"){v.calendars[0].unreadable=2;v.limits.unreadable_items=2;}
 if(change==="horizon")v.horizon_days=8;
 if(change==="days_length")v.days.pop();
 if(change==="cancelled")v.cancelled_count="1";
 if(change==="limits_missing")delete v.limits;
 if(change==="limit_shape")v.limits.events.shown="1";
 if(change==="flag_mismatch")v.truncated.events=true;
 if(change==="shown_mismatch")v.limits.events.shown=2;
 if(change==="unreadable_sum")v.limits.unreadable_items=1;
 if(change==="event_state")v.events[0].source_state="available";
 if(change==="event_as_of")v.events[0].as_of=null;
 if(change==="event_days")v.events[0].days=[];
 if(change==="continues")v.events[0].continues=true;
 if(change==="duplicate_ids")v.events[0].possible_duplicate_of=["not-an-id"];
 if(change==="omitted_without_truncation")v.limits.events.omitted_at_least=3;
 if(change==="provider_blocked_on_manual")v.calendars[0].blocked_reason="series_limit";
 expect(()=>parse2(v)).toThrow();});
it("accepts unreadable items only together with unknown coverage and matching counts",()=>{const v=briefingV2();v.calendars[0].source_state="unknown_coverage";v.events[0].source_state="unknown_coverage";v.calendars[0].unreadable=2;v.limits.unreadable_items=2;expect(parse2(v).limits?.unreadable_items).toBe(2);});
it("accepts reconciled truncation: flags equal the counts",()=>{const v=briefingV2();v.limits.events={shown:1,truncated:true,omitted_at_least:7};v.truncated.events=true;expect(parse2(v).limits?.events.omitted_at_least).toBe(7);});
it("places an all-day multi-day event on its date list in any display zone",()=>{const v=briefingV2();v.events[0]={...v.events[0],kind:"all_day",start:undefined,end:undefined,start_date:"2026-10-25",end_date:"2026-10-27",days:["2026-10-25","2026-10-26"],continues:true};v.days[0].events=1;v.days[1].events=1;expect(parse2(v).events[0].days).toEqual(["2026-10-25","2026-10-26"]);});
it("requests a horizon only when asked and syncs through one protected request",async()=>{const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(briefingV2())));vi.stubGlobal("fetch",fetch);await api.getBriefing("household_shared","2026-10-25","UTC","synthetic",new AbortController().signal,2);expect(JSON.parse((fetch.mock.calls[0][1] as RequestInit).body as string)).toMatchObject({horizon_days:2});
 const sync=vi.fn().mockResolvedValue(new Response(JSON.stringify({source_id:id,provider:{status:"ok",attempts:0,applied_seq:1,last_success_at:null,next_attempt_at:null,last_error_code:null,blocked_reason:null},sync:{outcome:"ok",reason:null,pages:1,changes:1}})));vi.stubGlobal("fetch",sync);
 const r=await api.syncSource(source as unknown as api.SourceMeta,false,"synthetic",new AbortController().signal);expect(r.sync?.outcome).toBe("ok");expect(sync).toHaveBeenCalledTimes(1);expect(sync.mock.calls[0][0]).toBe(`/api/v1/calendars/${id}/sync`);});
it("shows a provider mode and sync summary on source cards and refuses a malformed one",async()=>{
 const card={...source,label:"Synthetic calendar",status:"setup_required",fetched_at:null,start_date:null,end_date:null,timezone:null,mode:"provider",sync:{status:"ok",last_success_at:"2026-11-08T10:00:00Z",blocked_reason:null,last_error_code:null}};delete (card as any).data;
 const respond=(c:unknown)=>vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({schema_version:1,scope:"household_shared",items:[c],next_cursor:null}))));
 respond(card);expect((await api.listSources("household_shared",null,"synthetic",new AbortController().signal)).items[0].sync?.status).toBe("ok");
 respond({...card,sync:{...card.sync,status:"weird"}});await expect(api.listSources("household_shared",null,"synthetic",new AbortController().signal)).rejects.toThrow();
 respond({...card,mode:"live"});await expect(api.listSources("household_shared",null,"synthetic",new AbortController().signal)).rejects.toThrow();});
