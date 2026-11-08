import { taskScopes } from "./tasks-api";
export const documentScopes = taskScopes;
export type Scope = keyof typeof documentScopes;
export type Document = { id: string; owner_id: string; scope: Scope; state: "active" | "forgotten"; revision: number; created_at: string; updated_at: string; can_edit: boolean; title?: string; filename?: string; source_reference?: string; sha256?: string; byte_size?: number; reviewed?: boolean; line_count?: number; content_text?: string; text_origin?: "original_utf8" };
export type Filters = { scope: Scope; reviewed_only: boolean; search: string; after: string | null };
export type Page = { schema_version: 1; mode: "document_page"; actor_id: string; checked_at: string; page_limit: 25; managed_copy: false | null; filters: Filters; items: Document[]; next_cursor: string | null };
export type History = { schema_version: 1; document_id: string; current_revision: number; state: "active" | "forgotten"; items: { revision: number; actor_id: string; operation: string; created_at: string; snapshot: Document | null }[]; next_cursor: number | null };
export type Excerpt = Document & { start_line: number; end_line: number; excerpt: string; notice: string };
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const uuid = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) > 0;
const date = (v: unknown): v is string => typeof v === "string" && Number.isFinite(Date.parse(v));
const text = (v: unknown, max: number): v is string => typeof v === "string" && Array.from(v).length <= max;
function invalid(): never { throw new Error("Invalid document response"); }
export function parseDocument(v: unknown, full = true, history = false): Document {
  if (!object(v) || !uuid(v.id) || !uuid(v.owner_id) || typeof v.scope !== "string" || !Object.hasOwn(documentScopes,v.scope) || !integer(v.revision) || !date(v.created_at) || !date(v.updated_at) || (!history && typeof v.can_edit !== "boolean")) invalid();
  const meta = { id:v.id, owner_id:v.owner_id, scope:v.scope as Scope, revision:v.revision, created_at:v.created_at, updated_at:v.updated_at, can_edit: history ? false : v.can_edit as boolean };
  if (v.state === "forgotten") return {...meta,state:"forgotten"};
  if (v.state !== "active" || !text(v.title,160) || !v.title.trim() || !text(v.filename,120) || !text(v.source_reference,512) || !v.source_reference.trim() || typeof v.reviewed !== "boolean" || typeof v.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(v.sha256) || !integer(v.byte_size) || v.byte_size>131072 || !integer(v.line_count) || v.text_origin !== "original_utf8" || (full && (!text(v.content_text,32000) || !v.content_text.length))) invalid();
  return {...meta,state:"active",title:v.title,filename:v.filename,source_reference:v.source_reference,reviewed:v.reviewed,sha256:v.sha256,byte_size:v.byte_size,line_count:v.line_count,text_origin:"original_utf8",...(full ? {content_text:v.content_text as string} : {})};
}
export class DocumentError extends Error {
  constructor(public status:number) { super(status === 409 ? "The document changed or a library limit was reached. Your draft is kept; discard and reload before retrying." : status === 422 ? "Check the document details, file limits and requested lines." : [401,403,404,410].includes(status) ? "Documents are no longer available. Reload your session or library." : "Documents are unavailable. Reload before repeating a change."); }
}
export async function request(path:string, body:object, csrf:string, signal:AbortSignal):Promise<unknown> {
  const response = await fetch(`/api/v1/documents${path}`,{method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",signal,headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(body)});
  if (!response.ok) throw new DocumentError(response.status);
  return response.json();
}
export async function list(filters:Filters,csrf:string,signal:AbortSignal,exported=false):Promise<Page> {
  const v=await request(exported?"/export":"/query",exported?{...filters,acknowledge_copy_limits:true}:filters,csrf,signal);
  if (!object(v) || v.schema_version!==1 || v.mode!=="document_page" || !uuid(v.actor_id) || !date(v.checked_at) || v.page_limit!==25 || v.managed_copy!==(exported?false:null) || !object(v.filters) || Object.keys(filters).some(k=>v.filters && (v.filters as Record<string,unknown>)[k]!==filters[k as keyof Filters]) || !Array.isArray(v.items) || v.items.length>25 || !(v.next_cursor===null || uuid(v.next_cursor))) invalid();
  const items=v.items.map(x=>parseDocument(x,false));
  if (items.some((x,i)=>x.state!=="active" || x.scope!==filters.scope || (filters.reviewed_only && !x.reviewed) || (i>0 && x.id<=items[i-1].id) || (filters.after!==null && x.id<=filters.after)) || (v.next_cursor!==null && (items.length!==25 || items[24].id!==v.next_cursor))) invalid();
  return {schema_version:1,mode:"document_page",actor_id:v.actor_id,checked_at:v.checked_at,page_limit:25,managed_copy:exported?false:null,filters,items,next_cursor:v.next_cursor as string|null};
}
export async function action(row:Document,op:"read"|"correct"|"replace"|"forget",values:object,csrf:string,signal:AbortSignal):Promise<Document> {
  const v=parseDocument(await request(`/${row.id}/${op}`,{scope:row.scope,...(op==="read"?{}:{expected_revision:row.revision}),...values},csrf,signal));
  if (v.id!==row.id || v.owner_id!==row.owner_id || v.scope!==row.scope || (op!=="read" && v.revision!==row.revision+1) || (op==="forget"?v.state!=="forgotten":v.state!=="active")) invalid();
  return v;
}
export async function upload(scope:Scope,values:object,csrf:string,signal:AbortSignal):Promise<Document> {
  const v=parseDocument(await request("",{scope,...values},csrf,signal));
  if (v.state!=="active" || v.scope!==scope || !v.can_edit || v.revision!==1 || v.reviewed!==false) invalid();
  return v;
}
export async function history(row:Document,after:number,csrf:string,signal:AbortSignal):Promise<History> {
  const v=await request(`/${row.id}/history`,{scope:row.scope,after},csrf,signal);
  if (!object(v) || v.schema_version!==1 || v.document_id!==row.id || !integer(v.current_revision) || !["active","forgotten"].includes(v.state as string) || !Array.isArray(v.items) || v.items.length>25 || !(v.next_cursor===null || integer(v.next_cursor))) invalid();
  const items=v.items.map((x,i)=>{
    if (!object(x) || x.revision!==after+i+1 || x.actor_id!==row.owner_id || !date(x.created_at) || !["uploaded","corrected","replaced","forgotten"].includes(x.operation as string)) invalid();
    const snapshot=x.snapshot===null?null:parseDocument(x.snapshot,true,true);
    if ((v.state==="forgotten"?snapshot!==null:snapshot===null) || (snapshot && (snapshot.id!==row.id || snapshot.scope!==row.scope || snapshot.owner_id!==row.owner_id || snapshot.revision!==x.revision))) invalid();
    return {revision:x.revision as number,actor_id:x.actor_id as string,operation:x.operation as string,created_at:x.created_at,snapshot};
  });
  if (items.some(x=>x.revision>(v.current_revision as number)) || (v.next_cursor!==null && (items.length!==25 || v.next_cursor!==items[24].revision))) invalid();
  return {schema_version:1,document_id:row.id,current_revision:v.current_revision,state:v.state as History["state"],items,next_cursor:v.next_cursor as number|null};
}
export async function excerpt(row:Document,start:number,end:number,csrf:string,signal:AbortSignal):Promise<Excerpt> {
  const v=await request(`/${row.id}/excerpt`,{scope:row.scope,expected_revision:row.revision,start_line:start,end_line:end},csrf,signal);
  // Excerpts deliberately have no mutation controls or full text.
  if (!object(v)) invalid();
  const doc=parseDocument({...v,can_edit:false},false);
  if (doc.id!==row.id || doc.scope!==row.scope || doc.owner_id!==row.owner_id || doc.revision!==row.revision || doc.sha256!==row.sha256 || !doc.reviewed || v.start_line!==start || v.end_line!==end || !text(v.excerpt,16384) || new TextEncoder().encode(v.excerpt).length>16384 || !text(v.notice,512)) invalid();
  return {...doc,start_line:start,end_line:end,excerpt:v.excerpt,notice:v.notice};
}
export async function original(row:Document,version:number,csrf:string,signal:AbortSignal):Promise<{bytes:Uint8Array<ArrayBuffer>;filename:string}> {
  const v=await request(`/${row.id}/original`,{scope:row.scope,expected_revision:row.revision,version,acknowledge_copy_limits:true},csrf,signal);
  if (!object(v) || v.schema_version!==1 || v.document_id!==row.id || v.current_revision!==row.revision || v.revision!==version || v.managed_copy!==false || !text(v.original_base64,174764) || typeof v.sha256!=="string" || !/^[a-f0-9]{64}$/.test(v.sha256) || v.download_filename!==`${row.id}-v${version}.txt`) invalid();
  const raw=atob(v.original_base64),bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
  if (!bytes.length || bytes.length>131072 || btoa(raw)!==v.original_base64) invalid();
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  if (Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,"0")).join("")!==v.sha256 || (version===row.revision && v.sha256!==row.sha256)) invalid();
  if (signal.aborted) throw new DOMException("Aborted","AbortError");
  return {bytes,filename:v.download_filename as string};
}
export async function fileValues(file:File):Promise<{filename:string;original_base64:string}> {
  if (!/\.(txt|md)$/i.test(file.name) || !file.size || file.size>131072) throw new Error("Choose a nonempty .txt or .md file up to 128 KiB and 32,000 characters.");
  const bytes=new Uint8Array(await file.arrayBuffer());
  const text=new TextDecoder("utf-8",{fatal:true,ignoreBOM:true}).decode(bytes);
  if (Array.from(text).length>32000 || text.includes("\0")) throw new Error("Choose UTF-8 text without NUL, up to 32,000 characters.");
  let raw=""; for (const byte of bytes) raw+=String.fromCharCode(byte);
  return {filename:file.name,original_base64:btoa(raw)};
}
