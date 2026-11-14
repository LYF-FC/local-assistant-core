import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Session } from "./api";
import * as api from "./operations-api";
const actor="11111111-1111-4111-8111-111111111111";
const session={user:{id:actor,slug:"synthetic",display_name:"Synthetic",scopes:["technical_admin"]},csrfToken:"synthetic-csrf"} as Session;
const now="2026-11-10T12:00:00Z";
function fixture(){return {schema_version:1,scope:"technical_admin",actor_id:actor,checked_at:now,valid_until:"2026-11-10T12:01:00Z",window_start:"2026-11-09T12:00:00Z",window_end:now,components:api.componentKeys.map(key=>({key,state:key==="api"||key==="database"?"observed":key==="local_answers"?"disabled":"unknown"})),software:api.softwareKeys.map(key=>({key,version:key==="api_build"?"0.1-dev":"1.2.3",source:key==="api_build"?"declared_build":"runtime_metadata",assessment:"not_assessed"})),activity:{state:"not_available"},jobs:{sampled:0,has_more:false,counts:{queued:0,running:0,succeeded:0,dead_letter:0,other:0}}};}
function mock(value:unknown,status=200){const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(value),{status}));vi.stubGlobal("fetch",fetch);return fetch;}
beforeEach(()=>{vi.useFakeTimers();vi.setSystemTime(new Date(now));});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
it("accepts observed/configured/unknown distinctions and missing versions",()=>{const value=fixture();value.components[2].state="configured_unverified";value.software[1].version=null as never;const r=api.parseSnapshot(value,session);expect(r.software[1].version).toBeNull();expect(r.components[2].state).toBe("configured_unverified");});
it.each(["owner","scope","version","expiry","future","window","unknown field","duplicate component","missing component","false health","wrong source","unsafe version","approval claim","audit claim","audit payload","sum","negative","unknown count","truncation"])("rejects unsupported %s observations",change=>{const v=fixture();switch(change){case "owner":v.actor_id="foreign";break;case "scope":v.scope="finance_private";break;case "version":v.schema_version=2;break;case "expiry":v.valid_until=now;break;case "future":v.checked_at="2027-01-01T00:00:00Z";break;case "window":v.window_start=now;break;case "unknown field":Object.assign(v,{secret:"synthetic"});break;case "duplicate component":v.components[1]=v.components[0];break;case "missing component":v.components.pop();break;case "false health":v.components[5].state="observed";break;case "wrong source":v.software[1].source="declared_build";break;case "unsafe version":v.software[1].version="<script>synthetic</script>";break;case "approval claim":v.software[1].assessment="approved";break;case "audit claim":v.activity.state="available";break;case "audit payload":Object.assign(v.activity,{items:[]});break;case "sum":v.jobs.counts.running=1;break;case "negative":v.jobs.sampled=-1;break;case "unknown count":Object.assign(v.jobs.counts,{private:1});break;case "truncation":v.jobs.has_more=true;}expect(()=>api.parseSnapshot(v,session)).toThrow();});
it("uses one protected no-store POST without probes or retries",async()=>{const fetch=mock(fixture()),signal=new AbortController().signal;await api.readOperations(session,signal);expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toBe("/api/v1/operations/read");expect(fetch.mock.calls[0][1]).toMatchObject({method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",signal,headers:{"X-CSRF-Token":session.csrfToken}});expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({scope:"technical_admin"});});
it("no request without current admin membership",async()=>{const fetch=mock(fixture());await expect(api.readOperations({...session,user:{...session.user,scopes:["finance_private"]}},new AbortController().signal)).rejects.toMatchObject({status:403});expect(fetch).not.toHaveBeenCalled();});
it.each([401,403,404,410,422,429,503])("sanitizes %s and never retries",async status=>{const fetch=mock({detail:"synthetic private traceback"},status);await expect(api.readOperations(session,new AbortController().signal)).rejects.toMatchObject({status,message:expect.not.stringContaining("traceback")});expect(fetch).toHaveBeenCalledTimes(1);});
it("honors cancellation signal without fallback",async()=>{const controller=new AbortController();controller.abort();const fetch=vi.fn().mockRejectedValue(new DOMException("Aborted","AbortError"));vi.stubGlobal("fetch",fetch);await expect(api.readOperations(session,controller.signal)).rejects.toMatchObject({name:"AbortError"});expect(fetch).toHaveBeenCalledTimes(1);});

const summaryFixture=(window:"24h"|"7d"="24h")=>({schema_version:1,scope:"technical_admin",actor_id:actor,checked_at:now,valid_until:"2026-11-10T12:01:00Z",window,window_start:window==="24h"?"2026-11-09T12:00:00Z":"2026-11-03T12:00:00Z",window_end:now,categories:api.auditCategories.map((key,i)=>({key,success:i+1,denied:i%2,other:0})),totals:{success:28,denied:3,other:0},excludes:[...api.auditExcludes]});
it("accepts the exact audit summary shape and echoes the requested window",()=>{
  expect(api.parseAuditSummary(summaryFixture(),session,"24h").totals).toEqual({success:28,denied:3,other:0});
  expect(api.parseAuditSummary(summaryFixture("7d"),session,"7d").window).toBe("7d");
});
it.each([
  ["another actor",(v:any)=>{v.actor_id="22222222-2222-4222-8222-222222222222";}],
  ["extra top-level key",(v:any)=>{v.events=[];}],
  ["extra category key",(v:any)=>{v.categories[0].actor="x";}],
  ["missing category",(v:any)=>{v.categories.pop();}],
  ["reordered categories",(v:any)=>{v.categories.reverse();}],
  ["unknown category",(v:any)=>{v.categories[0].key="documents";}],
  ["negative count",(v:any)=>{v.categories[0].success=-1;v.totals.success=26;}],
  ["fractional count",(v:any)=>{v.categories[0].success=1.5;}],
  ["string count",(v:any)=>{v.categories[0].success="1";}],
  ["totals not summing",(v:any)=>{v.totals.success=29;}],
  ["wrong window echo",(v:any)=>{v.window="7d";}],
  ["window span mismatch",(v:any)=>{v.window_start="2026-11-09T11:00:00Z";}],
  ["expired",(v:any)=>{v.valid_until="2026-11-10T11:59:00Z";}],
  ["future check",(v:any)=>{v.checked_at="2026-11-10T13:00:00Z";v.window_end="2026-11-10T13:00:00Z";v.valid_until="2026-11-10T13:01:00Z";v.window_start="2026-11-09T13:00:00Z";}],
  ["changed exclusions",(v:any)=>{v.excludes=["content_domain_events"];}],
  ["health claim",(v:any)=>{v.healthy=true;}],
])("rejects an audit summary with %s",(_name,mutate)=>{
  const value:any=summaryFixture();mutate(value);
  expect(()=>api.parseAuditSummary(value,session,"24h")).toThrow();
});
it("sends one protected no-store POST with only the scope and window, and never an id",async()=>{
  const fetch=mock(summaryFixture("7d"));
  await api.readAuditSummary(session,"7d",new AbortController().signal);
  expect(fetch).toHaveBeenCalledTimes(1);
  const [path,init]=fetch.mock.calls[0] as unknown as [string,RequestInit];
  expect(path).toBe("/api/v1/operations/audit-summary");
  expect(init).toMatchObject({method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error"});
  expect(JSON.parse(String(init.body))).toEqual({scope:"technical_admin",window:"7d"});
  expect((init.headers as Record<string,string>)["X-CSRF-Token"]).toBe("synthetic-csrf");
});
it("makes no audit request without the current technical_admin grant or for an unsupported window",async()=>{
  const fetch=mock(summaryFixture());
  await expect(api.readAuditSummary({...session,user:{...session.user,scopes:["finance_private"]}},"24h",new AbortController().signal)).rejects.toMatchObject({status:403});
  await expect(api.readAuditSummary(session,"30d" as never,new AbortController().signal)).rejects.toMatchObject({status:403});
  expect(fetch).not.toHaveBeenCalled();
});
it.each([401,403,404,410,422,429,500,503])("sanitizes audit summary status %s and never retries",async status=>{
  const fetch=mock({detail:"synthetic private traceback"},status);
  await expect(api.readAuditSummary(session,"24h",new AbortController().signal)).rejects.toSatisfy((e:unknown)=>e instanceof api.OperationsError&&!/synthetic|traceback/.test(e.message));
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("rejects a 200 whose body is malformed rather than showing zeros",async()=>{
  mock({});
  await expect(api.readAuditSummary(session,"24h",new AbortController().signal)).rejects.toThrow();
});
