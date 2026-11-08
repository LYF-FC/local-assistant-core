import type { ActiveTask, TaskFilters, TaskPage } from "../tasks-api";
export const task: ActiveTask = { id:"11111111-1111-4111-8111-111111111111",owner_id:"22222222-2222-4222-8222-222222222222",scope:"member_a_private",state:"active",revision:1,created_at:"2026-11-07T12:00:00Z",updated_at:"2026-11-07T12:00:00Z",can_edit:true,title:"Synthetic task",details:"Synthetic details",source_reference:"Synthetic source",due_at:null,assignee_id:null,status:"open",completed_at:null,cancelled_at:null };
export const filters: TaskFilters = {scope:"member_a_private",status:"open",due:"all",search:"%_",after:null};
export const page: TaskPage = {schema_version:1,mode:"manual_task_page",checked_at:task.created_at,filters,page_limit:25,managed_copy:null,items:[task],next_cursor:null};
