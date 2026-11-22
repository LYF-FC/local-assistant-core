import {readFile} from "node:fs/promises";
import {expect,test,type Page} from "@playwright/test";
// MVP-01 synthetic invoice journey in the browser (spec 076). Runs only against the named local rehearsal
// (scripts/mvp01-owner.sh) with the exported PUBLIC dev CA trusted by the browser; ignoreHTTPSErrors stays false.
// Phase "journey" imports the supplied .eml twice, reviews, plans and files; phase "resume" signs in again after
// a restart and checks the same records. Agenda, reminder, answer and failure scenarios are covered by
// scripts/mvp01-owner-check.py and the existing daily-overview/reminder/answer specs.
const phase=process.env.BUTLER_MVP01_BROWSER_PHASE;
test.skip(process.env.BUTLER_MVP01_BROWSER_TESTS!=="1"||!phase,"Requires the MVP-01 rehearsal and an explicit phase");
const TITLE="MVP-01 rehearsal invoice";
async function login(page:Page){
 const password=process.env.BUTLER_MVP01_OWNER_PASSWORD;if(!password)throw new Error("Synthetic owner password required");
 await page.goto("/");await page.getByLabel("Username",{exact:true}).fill("mvp01-owner");await page.getByLabel("Password",{exact:true}).fill(password);
 await page.getByRole("button",{name:"Sign in",exact:true}).click();await expect(page.getByRole("navigation",{name:"Local records"})).toBeVisible();
 await page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name:"Documents",exact:true}).click();await page.getByLabel("Document scope",{exact:true}).selectOption("household_shared");
}
async function importEml(page:Page,title:string,raw:Buffer){
 await page.getByRole("button",{name:"Import forwarded email…",exact:true}).click();await page.getByLabel("Email document title",{exact:true}).fill(title);
 await page.getByLabel("Forwarded email file",{exact:true}).setInputFiles({name:"invoice.eml",mimeType:"message/rfc822",buffer:raw});
 await page.getByRole("button",{name:"Import email attachment",exact:true}).click();
}
const filing=(page:Page)=>page.getByRole("region",{name:"Synthetic filing execution",exact:true});
test("journey: same email twice, review, plan-only approval, separate exact request, filed once",async({page})=>{
 test.skip(phase!=="journey","journey phase");
 const raw=await readFile(process.env.BUTLER_MVP01_EML??"");
 await login(page);
 await importEml(page,TITLE,raw);
 const intake=page.getByRole("region",{name:"Offline email import",exact:true});
 await expect(intake).toContainText(/imported|already imported/);
 await importEml(page,"A replay must not rename",raw);
 await expect(intake).toContainText("Exact email already imported");
 await page.getByRole("button",{name:"Open imported document",exact:true}).click();
 const selected=page.getByRole("article",{name:"Selected document",exact:true});
 await expect(selected).toContainText("Issuer: Synthetic Rehearsal Vendor");await expect(selected).toContainText(TITLE);
 const provenance=page.getByRole("region",{name:"Original email provenance",exact:true});await provenance.getByRole("button",{name:"Load original email provenance",exact:true}).click();await expect(provenance).toContainText("matches current bytes");
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole("button",{name:"Correct and review",exact:true}).click();await page.getByRole("form",{name:"Correct document form",exact:true}).getByRole("checkbox").check();await page.getByRole("button",{name:"Save document",exact:true}).click();
 await page.getByRole("button",{name:TITLE,exact:true}).click();
 await page.getByRole("button",{name:"Load invoice review",exact:true}).click();await page.getByRole("button",{name:"Prepare invoice candidates",exact:true}).click();
 for(const [name,line] of [["Issuer",1],["Invoice number",2],["Issue date",3],["Total",5],["Currency",6]] as const)await page.getByRole("button",{name:`Use ${name} candidate at line ${line}`,exact:true}).click();
 await expect(page.getByLabel("Due date decision",{exact:true})).toHaveValue("unknown");
 await page.getByLabel("I compared these fields with the original and accept the confirmed/unknown decisions.",{exact:true}).check();await page.getByRole("button",{name:"Save invoice field review",exact:true}).click();
 const plan=page.getByRole("region",{name:"Invoice filing plan",exact:true});await plan.getByRole("button",{name:"Suggest filing plan",exact:true}).click();await expect(plan).toContainText("Plan status: proposed");
 // Plan approval alone must not offer or cause any filing effect.
 await expect(filing(page)).toHaveCount(0);
 await plan.getByLabel("I approve only this saved plan; no filing or future execution is authorized.",{exact:true}).check();await plan.getByLabel("I understand duplicate hints do not verify destination collisions.",{exact:true}).check();await plan.getByRole("button",{name:"Approve filing plan only",exact:true}).click();await expect(plan).toContainText("Plan status: approved");
 const exec=filing(page);await expect(exec).toContainText("synthetic metadata simulation");await expect(exec).toContainText("No filing requested for this document").catch(()=>{});
 await exec.getByRole("button",{name:"Refresh filing status",exact:true}).click();await expect(exec).toContainText("No filing requested for this document");
 const request=exec.getByRole("button",{name:"Request synthetic filing",exact:true});await expect(request).toBeDisabled();
 await exec.getByLabel("I authorize one filing of exactly this saved source and approved plan to the synthetic metadata destination.",{exact:true}).check();await expect(request).toBeDisabled();
 await exec.getByLabel("I understand this simulates a destination: nothing is copied and no real folder exists.",{exact:true}).check();await request.click();
 await expect(exec).toContainText("Filed in the synthetic metadata destination",{timeout:60000});
 await exec.getByRole("button",{name:/^Show filing history/}).first().click();await expect(exec.getByRole("list",{name:/^Filing history/})).toContainText("filed");
 await expect(exec.getByRole("button",{name:"Request synthetic filing",exact:true})).toHaveCount(0);
});
test("resume: after a restart the same document, plan, filing status and history are present",async({page})=>{
 test.skip(phase!=="resume","resume phase");
 await login(page);
 await page.getByRole("button",{name:TITLE,exact:true}).click();
 await page.getByRole("button",{name:"Load invoice review",exact:true}).click();
 const exec=filing(page);await expect(exec).toBeVisible();await exec.getByRole("button",{name:"Refresh filing status",exact:true}).click();
 await expect(exec).toContainText("Filed in the synthetic metadata destination");await expect(exec.getByRole("button",{name:/^Show filing history/})).toHaveCount(1);
 await exec.getByRole("button",{name:/^Show filing history/}).first().click();await expect(exec.getByRole("list",{name:/^Filing history/})).toContainText("requested");
});
