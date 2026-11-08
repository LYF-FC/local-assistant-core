import {parseDocument, type Document, type PageSpan} from "./documents-api";
import {taskScopes} from "./tasks-api";
export type AnswerScope = keyof typeof taskScopes;
export type Evidence = {source:number;document:Document;start_line:number;end_line:number;text:string;page_spans:PageSpan[]};
export type Answer = {schema_version:1;request_id:string;scope:AnswerScope;language:"en"|"fr"|"es";status:"source_only"|"no_sources"|"answered"|"insufficient"|"conflicting"|"unavailable"|"invalid_answer";model_invoked:boolean;execution_allowed:false;generated_at:string;valid_until:string;max_bytes:number;sources:Evidence[];passages:Evidence[];notice:string};
const object=(v:unknown):v is Record<string,unknown>=>typeof v==="object"&&v!==null&&!Array.isArray(v);
const integer=(v:unknown):v is number=>Number.isSafeInteger(v)&&(v as number)>0;
const uuid=(v:unknown):v is string=>typeof v==="string"&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(v);
const text=(v:unknown,max:number):v is string=>typeof v==="string"&&Array.from(v).length<=max&&!v.includes("\0");
function invalid():never{throw new Error("Invalid source answer");}
export class AnswerError extends Error{constructor(public status:number){super(status===409?"The sources or configuration changed. Ask again to rebuild current evidence.":status===413?"Matching excerpts are too long for this request. Narrow your question or inspect the document directly.":status===429?"The question budget was reached. Try again later.":[401,403,404,410].includes(status)?"Access changed. Refresh your session or scope.":"Document answers are unavailable. Try again deliberately; nothing was retried.");}}
function evidence(v:unknown,scope:AnswerScope):Evidence{
 if(!object(v)||Object.keys(v).sort().join(",")!=="document,end_line,page_spans,source,start_line,text"||!integer(v.source)||v.source>3||!integer(v.start_line)||!integer(v.end_line)||v.end_line<v.start_line||v.end_line-v.start_line>=8||!text(v.text,32000)||v.text.split("\n").length!==v.end_line-v.start_line+1||!Array.isArray(v.page_spans))invalid();
 const document=parseDocument(v.document,false);
 if(document.scope!==scope||document.state!=="active"||!document.reviewed||v.end_line>(document.line_count??0))invalid();
 const startLine=v.start_line as number,endLine=v.end_line as number;
 const expected=(document.extraction?.page_spans??[]).filter(s=>s.start_line<=endLine&&s.end_line>=startLine).map(s=>({page:s.page,start_line:Math.max(s.start_line,v.start_line as number),end_line:Math.min(s.end_line,v.end_line as number)}));
 if(v.page_spans.length!==expected.length||v.page_spans.some((s,i)=>!object(s)||Object.keys(s).sort().join(",")!=="end_line,page,start_line"||s.page!==expected[i].page||s.start_line!==expected[i].start_line||s.end_line!==expected[i].end_line))invalid();
 return{source:v.source,document,start_line:v.start_line,end_line:v.end_line,text:v.text,page_spans:expected};
}
export function parseAnswer(v:unknown,scope:AnswerScope,language:string,maxBytes:number):Answer{
 if(!object(v)||v.schema_version!==1||!uuid(v.request_id)||v.scope!==scope||v.language!==language||v.max_bytes!==maxBytes||typeof v.model_invoked!=="boolean"||v.execution_allowed!==false||!text(v.notice,512)||!text(v.generated_at,64)||!text(v.valid_until,64)||!Array.isArray(v.sources)||v.sources.length>3||!Array.isArray(v.passages)||v.passages.length>5||!["source_only","no_sources","answered","insufficient","conflicting","unavailable","invalid_answer"].includes(v.status as string))invalid();
 const start=Date.parse(v.generated_at),end=Date.parse(v.valid_until);
 if(!Number.isFinite(start)||!Number.isFinite(end)||end<=Date.now()||end<=start||end-start>60000||start>Date.now()+5000)invalid();
 const sources=v.sources.map(s=>evidence(s,scope)),passages=v.passages.map(s=>evidence(s,scope));
 if(sources.some((s,i)=>s.source!==i+1)||new Set(sources.map(s=>s.document.id)).size!==sources.length||new TextEncoder().encode(JSON.stringify(v.sources)).length>maxBytes||new TextEncoder().encode(JSON.stringify(v.passages)).length>8192)invalid();
 if(v.status==="no_sources"?(sources.length||v.model_invoked||passages.length):!sources.length)invalid();
 if(v.status==="source_only"&&v.model_invoked)invalid();
 if(v.status==="answered"?(!v.model_invoked||!passages.length):passages.length)invalid();
 if(["insufficient","conflicting","invalid_answer"].includes(v.status as string)&&!v.model_invoked)invalid();
 for(let i=0;i<passages.length;i++){
  const item=passages[i],source=sources[item.source-1];
  if(!source||JSON.stringify(item.document)!==JSON.stringify(source.document)||item.start_line<source.start_line||item.end_line>source.end_line||item.text!==source.text.split("\n").slice(item.start_line-source.start_line,item.end_line-source.start_line+1).join("\n")||passages.slice(0,i).some(p=>p.source===item.source&&p.start_line<=item.end_line&&p.end_line>=item.start_line))invalid();
 }
 return {...v,sources,passages} as unknown as Answer;
}
export async function ask(scope:AnswerScope,question:string,language:"en"|"fr"|"es",maxBytes:number,csrf:string,signal:AbortSignal):Promise<Answer>{
 const r=await fetch("/api/v1/document-answers",{method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",signal,headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({scope,question,language,max_bytes:maxBytes})});
 if(!r.ok)throw new AnswerError(r.status);
 return parseAnswer(await r.json(),scope,language,maxBytes);
}
