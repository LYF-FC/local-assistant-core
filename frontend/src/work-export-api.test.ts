import { afterEach, expect, it, vi } from "vitest";
import { parseExport, prepareExport } from "./work-notes-api";
import type { ExportRequest } from "./work-notes-api";
const ws="11111111-1111-4111-8111-111111111111", record="22222222-2222-4222-8222-222222222222", policy="33333333-3333-4333-8333-333333333333", source="44444444-4444-4444-8444-444444444444", receipt="55555555-5555-4555-8555-555555555555";
const checked="2026-11-06T12:00:00Z", retention="2026-11-06T13:00:00Z";
const selection:ExportRequest={selections:[{id:record,expected_revision:2}],include_drafts:false,purpose:"preview"};
const note={id:record,workspace_id:ws,policy_id:policy,revision:2,state:"confirmed",kind:"decision",marker:"synthetic:export-example",source_ids:[source],owner_id:null,due_at:null,retain_until:retention,actor_id:ws,created_at:"2026-11-06T11:00:00Z",updated_at:"2026-11-06T11:30:00Z"};
const references={sources:[{id:source,label:"sample-source"}],owner:null,policy:{id:policy,max_age_seconds:86400}};
function response(change:Record<string,unknown>={}, bundleChange:Record<string,unknown>={}) {
  const bundle={schema_version:1,mode:"synthetic_work_notes_archive",workspace_id:ws,export_id:receipt,generated_at:checked,retain_until:retention,current_revisions_only:true,managed_copy:false,execution_allowed:false,raw_transcripts_included:false,drafts_permitted:false,items:[{item:note,references}],...bundleChange};
  return {schema_version:1,mode:"synthetic_notes_export",workspace_id:ws,checked_at:checked,valid_until:"2026-11-06T12:01:00Z",features:{capture:true,review:true,confirmation:true,changes:true,export:true},model_invoked:false,execution_allowed:false,real_ingestion_allowed:false,purpose:"preview",bundle,reviewed_hash:"a".repeat(64),bundle_bytes:new TextEncoder().encode(JSON.stringify(bundle)).length,...change};
}
afterEach(()=>vi.unstubAllGlobals());
it("preserves selected current records and unknowns without adding inspection hashes",()=>{
  const value=parseExport(response(),ws,selection);
  expect(value.bundle.items[0].item.owner_id).toBeNull();
  expect(value.bundle.items[0].references.sources[0].id).toBe(source);
  expect(JSON.stringify(value.bundle)).not.toContain("payload_hash");
  expect(value.request).not.toBe(selection);
  expect(value.request.selections).not.toBe(selection.selections);
});
it.each([
  {workspace_id:record},{execution_allowed:true},{purpose:"download"},{bundle_bytes:32769},{bundle_bytes:1},{reviewed_hash:"bad"},{valid_until:checked},{features:{export:false}},
])("rejects unsafe export envelope %j",change=>expect(()=>parseExport(response(change),ws,selection)).toThrow());
it.each([
  {workspace_id:record},{managed_copy:true},{raw_transcripts_included:true},{current_revisions_only:false},{execution_allowed:true},{drafts_permitted:true},{retain_until:checked},{generated_at:"2026-11-06T12:01:00Z"},{items:[]},
  {items:[{item:{...note,revision:3},references}]},
  {items:[{item:{...note,state:"draft"},references}]},
  {items:[{item:note,references:{...references,sources:[]}}]},
  {items:[{item:{...note,retain_until:"2026-11-06T12:30:00Z"},references}]},
  {items:[{item:{...note,source_ids:[]},references:{...references,sources:[]}}]},
])("rejects unreviewed, ineligible or inconsistent archive %j",change=>expect(()=>parseExport(response({},change),ws,selection)).toThrow());
it("requires explicit draft policy and exact download hash/acknowledgement",()=>{
  expect(parseExport(response({}, {drafts_permitted:true,items:[{item:{...note,state:"draft"},references}]}),ws,{...selection,include_drafts:true}).bundle.items[0].item.state).toBe("draft");
  const request:ExportRequest={...selection,purpose:"download",acknowledge_copy_limits:true,reviewed_hash:"a".repeat(64)};
  expect(parseExport(response({purpose:"download"}),ws,request).purpose).toBe("download");
  expect(()=>parseExport(response({purpose:"download"}),ws,{...request,reviewed_hash:"b".repeat(64)})).toThrow();
  expect(()=>parseExport(response({purpose:"download"}),ws,{...request,acknowledge_copy_limits:false})).toThrow();
});
it("sends a fresh JSON/CSRF/no-store download request with frozen selections",async()=>{
  const request:ExportRequest={...selection,purpose:"download",acknowledge_copy_limits:true,reviewed_hash:"a".repeat(64)};
  const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>response({purpose:"download"})});vi.stubGlobal("fetch",fetch);
  await prepareExport(ws,request,{user:{id:ws,display_name:"Synthetic",scopes:[]},csrfToken:"synthetic-csrf"},new AbortController().signal);
  expect(fetch.mock.calls[0][0]).toBe(`/api/v1/work/workspaces/${ws}/notes/export`);
  expect(fetch.mock.calls[0][1]).toMatchObject({method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",headers:{"X-CSRF-Token":"synthetic-csrf"}});
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(request);
});
