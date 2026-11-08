import { afterEach, expect, it, vi } from "vitest";
import { catalogue, parseCatalogue, parseInspection, parseRequest, recovered, submit } from "./work-notes-api";
import type { Action } from "./work-notes-api";
const ws="11111111-1111-4111-8111-111111111111",record="22222222-2222-4222-8222-222222222222",nonce="33333333-3333-4333-8333-333333333333",policy="44444444-4444-4444-8444-444444444444",source="55555555-5555-4555-8555-555555555555";
const session={user:{id:ws,display_name:"Synthetic",scopes:[]},csrfToken:"synthetic-csrf-token"};
const frame={schema_version:1,mode:"synthetic_notes_catalogue",workspace_id:ws,checked_at:"2026-11-05T12:00:00Z",valid_until:"2026-11-05T12:01:00Z",features:{capture:true,review:true,confirmation:true,changes:true,export:true},model_invoked:false,execution_allowed:false,real_ingestion_allowed:false};
const row={id:record,revision:1,state:"draft",label:"example",content_available:true,retain_until:"2026-11-05T13:00:00Z"};
const page={...frame,pages:{notes:{items:[row],next_cursor:null}}};
const request={id:record,operation:"capture_draft",request_id:nonce,target_record_id:null,expected_revision:null,state:"pending",record_id:null,revision:null,expires_at:"2026-11-05T12:05:00Z",prepared_at:frame.checked_at,within_lifetime:true};
afterEach(()=>vi.unstubAllGlobals());
it("accepts bounded labelled notes and exact preview bindings",()=>{
  expect(parseCatalogue(page,ws,"notes").pages.notes!.items[0].label).toBe("example");
  const inspection={...frame,mode:"synthetic_note_inspection",payload_hash:"a".repeat(64),item:{id:record,workspace_id:ws,policy_id:policy,revision:1,state:"draft",kind:"question",marker:"synthetic:example",source_ids:[source],owner_id:null,due_at:null,retain_until:row.retain_until,actor_id:ws,created_at:frame.checked_at,updated_at:frame.checked_at},references:{sources:[{id:source,label:"selected"}],owner:null,policy:{id:policy,max_age_seconds:86400}}};
  expect(parseInspection(inspection,ws,record).item.owner_id).toBeNull();
  expect(()=>parseInspection({...inspection,item:{...inspection.item,workspace_id:record}},ws,record)).toThrow();
  expect(()=>parseInspection({...inspection,references:{...inspection.references,sources:[]}},ws,record)).toThrow();
});
it.each([{workspace_id:record},{execution_allowed:true},{real_ingestion_allowed:true},{valid_until:frame.checked_at},{valid_until:"2026-11-05T12:02:00Z"},{features:{capture:"yes"}}])("rejects bad frame %j",change=>expect(()=>parseCatalogue({...page,...change},ws,"notes")).toThrow());
it.each([{items:Array(26).fill(row),next_cursor:null},{items:[row,row],next_cursor:null},{items:[{...row,label:"<script>"}],next_cursor:null},{items:[row],next_cursor:ws},{items:[{...row,state:"forgotten"}],next_cursor:null}])("rejects unsafe pages %j",notes=>expect(()=>parseCatalogue({...frame,pages:{notes}},ws,"notes")).toThrow());
it("validates historical outcomes and action/target recovery",()=>{
  expect(parseRequest(request).state).toBe("pending");
  expect(()=>parseRequest({...request,state:"applied"})).toThrow();
  const action={operation:"capture_draft" as const,request_id:nonce,target_record_id:null,expected_revision:null};
  expect(recovered({items:[parseRequest(request)],next_cursor:null},action)?.id).toBe(record);
  expect(()=>recovered({items:[parseRequest(request)],next_cursor:null},{...action,operation:"forget_note"})).toThrow();
  expect(recovered({items:[],next_cursor:null},action)).toBeNull();
});
it("uses safe JSON/CSRF/no-store reads without browser persistence",async()=>{
  const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>page});vi.stubGlobal("fetch",fetch);
  await catalogue(ws,session,new AbortController().signal,"notes");
  expect(fetch.mock.calls[0][1]).toMatchObject({method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",headers:{"X-CSRF-Token":session.csrfToken}});
});
it("retries the identical frozen capture nonce and payload",async()=>{
  const fetch=vi.fn().mockRejectedValueOnce(new TypeError("interrupted")).mockResolvedValue({ok:true,json:async()=>({schema_version:1,mode:"synthetic_draft_capture",capture_preparation_id:record,state:"pending",capture_applied:false,record_id:null,revision:null,expires_at:request.expires_at,model_invoked:false,execution_allowed:false,real_ingestion_allowed:false})});vi.stubGlobal("fetch",fetch);
  const action:Action={operation:"capture_draft",request_id:nonce,target_record_id:null,expected_revision:null,body:{request_id:nonce,decision:"capture_draft",policy_id:policy,draft:{marker:"synthetic:frozen"}}};
  await expect(submit(ws,action,session,new AbortController().signal)).rejects.toThrow();
  expect((await submit(ws,action,session,new AbortController().signal)).state).toBe("pending");
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
});
it("does not accept a malformed success as applied",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({schema_version:1,mode:"synthetic_draft_capture",capture_preparation_id:record,state:"applied",capture_applied:true,record_id:record,revision:99,expires_at:request.expires_at,model_invoked:false,execution_allowed:false,real_ingestion_allowed:false})}));
  const action:Action={operation:"capture_draft",request_id:nonce,target_record_id:null,expected_revision:null,body:{request_id:nonce}};
  await expect(submit(ws,action,session,new AbortController().signal)).rejects.toThrow();
});

it("rejects an applied change bound to another note",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({schema_version:1,mode:"synthetic_note_change",operation:"correct_note",change_request_id:nonce,state:"applied",change_applied:true,record_id:source,revision:2,expires_at:request.expires_at,model_invoked:false,execution_allowed:false,real_ingestion_allowed:false})}));
  const action:Action={operation:"correct_note",request_id:nonce,target_record_id:record,expected_revision:1,body:{request_id:nonce}};
  await expect(submit(ws,action,session,new AbortController().signal)).rejects.toThrow();
});
