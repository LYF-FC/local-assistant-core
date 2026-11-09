import {afterEach,describe,expect,it,vi} from "vitest";
import {apply,exportTemplate,importTemplate,installation,InstallationError,preview,read,template,view} from "./installation-api";
const t={schema_version:1 as const,defaults:{languages:["en"],timezone:"UTC"}};
const r={installation_id:null,revision:0,configuration:null,updated_by:null,created_at:"2026-11-09T00:00:00+00:00",updated_at:"2026-11-09T00:00:00+00:00"};
const session={user:{id:"11111111-1111-4111-8111-111111111111",display_name:"Synthetic",scopes:["technical_admin"]},csrfToken:"synthetic-token"};
const signal=new AbortController().signal;
const catalogue=Array.from({length:14},(_,i)=>({key:`core.${String.fromCharCode(97+i)}`,dependencies:[],mandatory:false,readiness:"available_in_development",activation_control:"not_provided",live_verified:false,notice:"Synthetic capability"}));
const response={schema_version:1,record:r,catalogue,notice:"Synthetic readiness only"};
function mock(data:unknown,status=200){const f=vi.fn().mockResolvedValue(new Response(JSON.stringify(data),{status}));vi.stubGlobal("fetch",f);return f;}
afterEach(()=>vi.unstubAllGlobals());
describe("strict installation boundary",()=>{
 it.each([{...t,installation_id:"synthetic"},{...t,schema_version:true},{...t,defaults:{...t.defaults,secret:"synthetic"}},{...t,defaults:{...t.defaults,languages:["en","en"]}},{...t,defaults:{...t.defaults,languages:[]}},{...t,defaults:{...t.defaults,timezone:"bad zone"}}])("rejects unexpected or malformed templates",v=>expect(()=>template(v)).toThrow());
 it("round trips only sanitized defaults and enforces input size",()=>{expect(importTemplate(JSON.stringify(t))).toEqual(t);expect(()=>importTemplate(" ".repeat(4097))).toThrow();});
 it("rejects identity and revision inconsistencies",()=>{expect(installation(r)).toEqual(r);expect(()=>installation({...r,installation_id:session.user.id})).toThrow();expect(()=>installation({...r,revision:1})).toThrow();});
 it("refuses activation claims and missing dependencies",()=>{expect(view(response).catalogue).toHaveLength(14);expect(()=>view({...response,catalogue:catalogue.map(c=>({...c,live_verified:true}))})).toThrow();expect(()=>view({...response,catalogue:catalogue.map(c=>({...c,dependencies:["unknown"]}))})).toThrow();});
 it("sends protected requests once without caching or retries",async()=>{const f=mock(response);await read(session,signal);expect(f).toHaveBeenCalledTimes(1);expect(f.mock.calls[0][1]).toMatchObject({credentials:"same-origin",cache:"no-store",redirect:"error",signal,headers:{"X-CSRF-Token":session.csrfToken}});expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({scope:"technical_admin"});});
 it("pins previews to source revision and exact normalized defaults",async()=>{const p={schema_version:1,record:r,template:t,changed_fields:["languages","timezone"],creates_identity:true,expires_at:"2026-11-09T00:05:00+00:00",preview_token:"a".repeat(64)};mock(p);expect(await preview(session,r,t,signal)).toEqual(p);mock({...p,template:{...t,defaults:{...t.defaults,languages:["fr"]}}});await expect(preview(session,r,t,signal)).rejects.toThrow();});
 it("rejects unbound apply receipts",async()=>{mock({...response,changed:true});await expect(apply(session,{schema_version:1,record:r,template:t,changed_fields:["languages","timezone"],creates_identity:true,expires_at:"2026-11-09T00:05:00+00:00",preview_token:"a".repeat(64)},signal)).rejects.toThrow();});
 it("rejects an export containing installation identity",async()=>{mock({schema_version:1,export_kind:"setup_template",template:t,managed_copy:false,installation_id:session.user.id});await expect(exportTemplate(session,{...r,configuration:t},signal)).rejects.toThrow();});
 it.each([401,403,409,429,503])("returns sanitized %s without retries",async status=>{const f=mock({detail:"synthetic secret"},status);await expect(read(session,signal)).rejects.toBeInstanceOf(InstallationError);expect(f).toHaveBeenCalledTimes(1);});
});
