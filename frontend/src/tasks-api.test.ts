import { afterEach, expect, it, vi } from "vitest";
import { createTask, listTasks, parseTask, parseTaskPage, taskAction, TaskError, taskHistory } from "./tasks-api";
import { filters, page, task } from "./test-support/tasks";
const signal=()=>new AbortController().signal;
const response=(v:unknown)=>new Response(JSON.stringify(v));
afterEach(()=>vi.unstubAllGlobals());
it("uses same-origin, no-store, abortable POST bodies with CSRF and no search in URLs",async()=>{
 const fetch=vi.fn().mockResolvedValue(response(page));vi.stubGlobal("fetch",fetch);const abort=signal();expect(await listTasks(filters,"synthetic-csrf",abort)).toEqual(page);
 expect(fetch).toHaveBeenCalledWith("/api/v1/tasks/query",expect.objectContaining({method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",signal:abort,headers:{"Content-Type":"application/json","X-CSRF-Token":"synthetic-csrf"},body:JSON.stringify(filters)}));
});
it("only acknowledges an explicit export request and requires unmanaged live-page metadata",async()=>{
 const fetch=vi.fn().mockResolvedValue(response({...page,managed_copy:false}));vi.stubGlobal("fetch",fetch);await listTasks(filters,"synthetic",signal(),true);expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({...filters,acknowledge_copy_limits:true});expect(fetch.mock.calls[0][0]).toBe("/api/v1/tasks/export");
 expect(()=>parseTaskPage(page,filters,true)).toThrow("Invalid task");
});
it.each([401,403,404,409,410,422,503])("sanitizes %s errors without retrying or leaking upstream content",async status=>{
 const fetch=vi.fn().mockResolvedValue(new Response("Synthetic private upstream",{status}));vi.stubGlobal("fetch",fetch);await expect(listTasks(filters,"synthetic",signal())).rejects.toBeInstanceOf(TaskError);expect(fetch).toHaveBeenCalledTimes(1);
});
it.each([{revision:true},{scope:"technical_admin"},{status:"inferred"},{assignee_id:task.id},{due_at:"wrong"},{completed_at:task.created_at},{details:"x".repeat(4001)},{title:" "},{can_edit:"yes"},{source_reference:""}])("rejects malformed task metadata %j",change=>{expect(()=>parseTask({...task,...change})).toThrow("Invalid task");});
it("accepts explicit done/cancelled timestamps and minimal tombstones without content",()=>{
 expect(parseTask({...task,status:"done",completed_at:task.created_at})).toMatchObject({status:"done"});expect(parseTask({...task,status:"cancelled",cancelled_at:task.created_at})).toMatchObject({status:"cancelled"});
 expect(parseTask({...task,state:"forgotten"})).not.toHaveProperty("title");
});
it.each([{items:Array(26).fill(task)},{items:[task,task]},{filters:{...filters,scope:"household_shared"}},{items:[{...task,scope:"household_shared"}]},{items:[{...task,state:"forgotten"}]},{next_cursor:task.id},{page_limit:50},{schema_version:2},{checked_at:"bad"}])("rejects mismatched or misleading page %j",change=>{expect(()=>parseTaskPage({...page,...change},filters)).toThrow("Invalid task");});
it("binds create and mutation results to the requested scope, identity and next revision",async()=>{
 const values={title:task.title,details:task.details,source_reference:task.source_reference,due_at:null,assignment:"unknown" as const};const fetch=vi.fn().mockResolvedValueOnce(response(task)).mockResolvedValueOnce(response({...task,revision:2,title:"Synthetic changed"})).mockResolvedValueOnce(response({...task,revision:2,id:task.owner_id}));vi.stubGlobal("fetch",fetch);
 await createTask(values,"member_a_private","synthetic",signal());await taskAction(task,"correct","synthetic",signal(),{...values,title:"Synthetic changed"});expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({scope:"member_a_private",expected_revision:1});await expect(taskAction(task,"correct","synthetic",signal(),values)).rejects.toThrow("Invalid task");
});
it("validates sequential owner history and redacted forgotten snapshots",async()=>{
 const {can_edit:_,...snapshot}=task;const row={revision:1,actor_id:task.owner_id,operation:"created",created_at:task.created_at,snapshot};const history={schema_version:1,task_id:task.id,current_revision:1,state:"active",items:[row],next_cursor:null};const fetch=vi.fn().mockResolvedValueOnce(response(history)).mockResolvedValueOnce(response({...history,state:"forgotten",items:[{...row,snapshot:null}]})).mockResolvedValueOnce(response({...history,items:[{...row,actor_id:task.id}]}));vi.stubGlobal("fetch",fetch);
 expect((await taskHistory(task,0,"synthetic",signal())).items[0].snapshot).toMatchObject({title:task.title});expect((await taskHistory(task,0,"synthetic",signal())).items[0].snapshot).toBeNull();await expect(taskHistory(task,0,"synthetic",signal())).rejects.toThrow("Invalid task");
});
it("propagates aborts with no retry",async()=>{const fetch=vi.fn().mockRejectedValue(new DOMException("Aborted","AbortError"));vi.stubGlobal("fetch",fetch);await expect(listTasks(filters,"synthetic",signal())).rejects.toMatchObject({name:"AbortError"});expect(fetch).toHaveBeenCalledTimes(1);});
