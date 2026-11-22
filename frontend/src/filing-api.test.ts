import {afterEach,expect,it,vi} from "vitest";
import {cancelFiling,filingHistory,parseFiling,queryFilings,requestFiling,FilingError,type Filing} from "./filing-api";
import type {Document} from "./documents-api";
import type {Receipt} from "./invoices-api";
const id="11111111-1111-4111-8111-111111111111",owner="22222222-2222-4222-8222-222222222222",exec="33333333-3333-4333-8333-333333333333";
const doc={id,owner_id:owner,scope:"household_shared",revision:2,can_edit:true} as Document;
const receipt={status:"reviewed",review_revision:4} as Receipt;
const signal=new AbortController().signal;
function row(change:Partial<Filing>={}):Filing{return {id:exec,document_id:id,owner_id:owner,scope:"household_shared",destination:"synthetic",state:"pending",revision:1,plan_revision:4,source_revision:2,attempts:0,next_attempt_at:"2026-11-22T10:00:00+00:00",resolved_at:null,reason:null,created_at:"2026-11-22T10:00:00+00:00",updated_at:"2026-11-22T10:00:00+00:00",scrubbed:false,...change};}
function reply(body:unknown,status=200){return vi.fn().mockResolvedValue(new Response(JSON.stringify(body),{status}));}
afterEach(()=>vi.unstubAllGlobals());
it("sends one exact request bound to document, source revision, plan revision and both acknowledgements",async()=>{
 const fetch=reply({schema_version:1,replayed:false,filing:row()},201);vi.stubGlobal("fetch",fetch);
 const created=await requestFiling(doc,receipt,"csrf",signal);
 expect(created.replayed).toBe(false);expect(fetch).toHaveBeenCalledTimes(1);
 const [url,init]=fetch.mock.calls[0];expect(url).toBe("/api/v1/filing/request");expect(init.credentials).toBe("same-origin");expect(init.redirect).toBe("error");expect(init.headers["X-CSRF-Token"]).toBe("csrf");
 expect(JSON.parse(init.body)).toEqual({scope:"household_shared",document_id:id,expected_document_revision:2,expected_review_revision:4,acknowledge_synthetic_destination:true,acknowledge_exact_plan:true});
});
it("does not call the server without a reviewed saved plan revision",async()=>{
 const fetch=vi.fn();vi.stubGlobal("fetch",fetch);
 await expect(requestFiling(doc,{status:"draft",review_revision:null} as Receipt,"c",signal)).rejects.toBeInstanceOf(FilingError);
 expect(fetch).not.toHaveBeenCalled();
});
it("does not retry a conflict and hides server text",async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response("Private path invoices/x",{status:409}));vi.stubGlobal("fetch",fetch);
 const error=await requestFiling(doc,receipt,"c",signal).catch(e=>e);
 expect(error).toBeInstanceOf(FilingError);expect(error.status).toBe(409);expect(error.message).not.toContain("invoices/x");expect(fetch).toHaveBeenCalledTimes(1);
});
it.each([
 ["other document",{document_id:"44444444-4444-4444-8444-444444444444"}],
 ["other owner",{owner_id:"44444444-4444-4444-8444-444444444444"}],
 ["other scope",{scope:"member_a_private"}],
 ["real destination",{destination:"nas"}],
 ["unknown state",{state:"done"}],
 ["terminal without resolution",{state:"filed"}],
 ["resolution without terminal",{resolved_at:"2026-11-22T10:00:00+00:00"}],
 ["attempts above bound",{attempts:4}],
 ["bad reason",{reason:"/etc/passwd"}],
 ["scrubbed with link",{scrubbed:true}],
])("rejects a mismatched filing: %s",(_name,change)=>{expect(()=>parseFiling(row(change as Partial<Filing>),doc)).toThrow();});
it.each([
 ["different plan revision",{plan_revision:3}],
 ["different source revision",{source_revision:1}],
 ["scrubbed",{scrubbed:true,document_id:null,plan_revision:null,source_revision:null}],
])("rejects a created filing that is not the exact request: %s",async(_name,change)=>{
 vi.stubGlobal("fetch",reply({schema_version:1,replayed:false,filing:row(change as Partial<Filing>)},201));
 await expect(requestFiling(doc,receipt,"c",signal)).rejects.toThrow();
});
it("lists only this document's bounded unique items and keeps earlier plan revisions visible",async()=>{
 vi.stubGlobal("fetch",reply({schema_version:1,checked_at:"2026-11-22T10:00:00+00:00",owner_id:owner,scope:"household_shared",state:"all",items:[row({plan_revision:3})],next_cursor:null,notice:"Synthetic destination only."}));
 const listing=await queryFilings(doc,"c",signal);expect(listing.items[0].plan_revision).toBe(3);
});
it.each([
 ["duplicate",(i:Filing)=>[i,i]],
 ["too many",(i:Filing)=>Array.from({length:26},(_,n)=>({...i,id:`33333333-3333-4333-8333-${String(n).padStart(12,"0")}`}))],
])("rejects a malformed listing: %s",async(_name,items)=>{
 vi.stubGlobal("fetch",reply({schema_version:1,checked_at:"2026-11-22T10:00:00+00:00",owner_id:owner,scope:"household_shared",state:"all",items:items(row()),next_cursor:null,notice:"n"}));
 await expect(queryFilings(doc,"c",signal)).rejects.toThrow();
});
it("rejects a listing for another owner",async()=>{
 vi.stubGlobal("fetch",reply({schema_version:1,checked_at:"2026-11-22T10:00:00+00:00",owner_id:"44444444-4444-4444-8444-444444444444",scope:"household_shared",state:"all",items:[],next_cursor:null,notice:"n"}));
 await expect(queryFilings(doc,"c",signal)).rejects.toThrow();
});
it("accepts ordered history whose snapshots lack the scrubbed marker and rejects reordering",async()=>{
 const snap=(n:number)=>{const {scrubbed:_s,...rest}=row({revision:n});return rest;};
 const good={schema_version:1,execution_id:exec,items:[{revision:1,operation:"requested",recorded_at:"2026-11-22T10:00:00+00:00",snapshot:snap(1)},{revision:2,operation:"attempted",recorded_at:"2026-11-22T10:01:00+00:00",snapshot:snap(2)}],next_cursor:null};
 vi.stubGlobal("fetch",reply(good));
 const history=await filingHistory(doc,row(),0,"c",signal);expect(history.items.map(i=>i.operation)).toEqual(["requested","attempted"]);
 vi.stubGlobal("fetch",reply({...good,items:[...good.items].reverse()}));
 await expect(filingHistory(doc,row(),0,"c",signal)).rejects.toThrow();
 vi.stubGlobal("fetch",reply({...good,execution_id:"44444444-4444-4444-8444-444444444444"}));
 await expect(filingHistory(doc,row(),0,"c",signal)).rejects.toThrow();
});
it("cancels one exact revision and requires a cancelled result for the same filing",async()=>{
 const fetch=reply({schema_version:1,filing:row({state:"cancelled",revision:2,resolved_at:"2026-11-22T10:02:00+00:00",reason:"cancelled_by_owner"})});vi.stubGlobal("fetch",fetch);
 const next=await cancelFiling(doc,row(),"c",signal);expect(next.state).toBe("cancelled");
 expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({scope:"household_shared",execution_id:exec,expected_revision:1});
 vi.stubGlobal("fetch",reply({schema_version:1,filing:row({state:"filed",resolved_at:"2026-11-22T10:02:00+00:00"})}));
 await expect(cancelFiling(doc,row(),"c",signal)).rejects.toThrow();
});

const editor="55555555-5555-4555-8555-555555555555";
it("accepts an empty listing for a non-owner editor who is the caller, and refuses anything else for them",async()=>{
 const listing=(items:unknown[],owner=editor)=>({schema_version:1,checked_at:"2026-11-22T10:00:00+00:00",owner_id:owner,scope:"household_shared",state:"all",items,next_cursor:null,notice:"n"});
 vi.stubGlobal("fetch",reply(listing([])));
 expect((await queryFilings(doc,"c",signal,editor)).items).toEqual([]);
 vi.stubGlobal("fetch",reply(listing([row({owner_id:editor})])));
 await expect(queryFilings(doc,"c",signal,editor)).rejects.toThrow();
 vi.stubGlobal("fetch",reply(listing([],owner)));
 await expect(queryFilings(doc,"c",signal,editor)).rejects.toThrow();
});
