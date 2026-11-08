import { openSyntheticSession } from "./work-browser-session";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test.skip(process.env.BUTLER_WORK_NOTES_BROWSER_TESTS !== "1", "Optional synthetic interface overlay required");
function apply(module: string, id: string) {
  if (process.env.BUTLER_ENV !== "test" || process.env.BUTLER_POSTGRES_DB !== "butler_test_container" || process.env.COMPOSE_PROJECT_NAME !== "butler-ci") throw new Error("Disposable CI executor only");
  execFileSync("docker",["compose","-f","infra/core/compose.yml","run","--rm","-T","migrate","python","-m",module,"--environment","test","--request",id],{cwd:resolve(process.cwd(),".."),env:process.env,timeout:45000,stdio:"pipe"});
}
async function open(page: Page) {
  await openSyntheticSession(page, "browser-work-notes");
  await page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name:"Work Companion",exact:true}).click();
  await page.getByRole("button",{name:"Load assigned workspaces",exact:true}).click();
  await page.getByRole("button",{name:"synthetic-adapter-ci",exact:true}).click();
  const panel=page.getByRole("region",{name:"Synthetic Work notes",exact:true});
  await panel.getByRole("button",{name:"Open synthetic notes",exact:true}).click();
  await expect(panel.getByRole("button",{name:"New sample note",exact:true})).toBeEnabled();
  return panel;
}
async function fill(page: Page,text: string) {
  await page.getByRole("button",{name:"New sample note",exact:true}).click();
  const form=page.getByRole("form",{name:"New sample note",exact:true});
  await form.getByLabel("Sample note",{exact:true}).fill(text);
  await form.getByRole("checkbox",{name:"container-adapter",exact:true}).check();
  await form.getByLabel("Retention policy",{exact:true}).selectOption({index:1});
  await form.getByLabel("Keep until",{exact:true}).selectOption("3600");
  await expect(form.getByLabel("Owner",{exact:true})).toHaveValue("unknown");
  return form;
}
test("complete labelled capture review confirmation correction and forget on mobile and desktop",async({page})=>{
  test.setTimeout(90000);
  const panel=await open(page);
  const form=await fill(page,"Browser sample workflow");
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/work-notes-mobile.png",fullPage:true});
  const prepared=page.waitForResponse(r=>r.url().endsWith("/captures")&&r.request().method()==="POST");
  await form.getByRole("button",{name:"Request save",exact:true}).click();
  const capture=await(await prepared).json();
  await expect(panel.getByRole("region",{name:"Request outcome",exact:true})).toContainText("Nothing is applied yet");
  await expect(panel.getByRole("button",{name:"New sample note",exact:true})).toBeDisabled();
  apply("app.work_capture_worker",capture.capture_preparation_id);
  await panel.getByRole("button",{name:"Recover or refresh request status",exact:true}).click();
  await expect(panel.getByRole("region",{name:"Request outcome",exact:true})).toContainText("Applied at version 1");
  await panel.getByRole("button",{name:"Open resulting note",exact:true}).click();
  const detail=panel.getByRole("region",{name:"Selected work note",exact:true});
  await expect(detail).toContainText("Browser sample workflow");
  await expect(detail).toContainText("Unknown");
  const pending=page.waitForResponse(r=>r.url().endsWith("/confirm")&&r.request().method()==="POST");
  await detail.getByRole("button",{name:"Confirm this version",exact:true}).click();
  const confirmation=await(await pending).json();
  apply("app.work_confirmation_worker",confirmation.confirmation_request_id);
  await panel.getByRole("button",{name:"Recover or refresh request status",exact:true}).click();
  await expect(panel.getByRole("region",{name:"Request outcome",exact:true})).toContainText("Applied at version 2");
  await panel.getByRole("button",{name:"Open resulting note",exact:true}).click();
  await expect(detail).toContainText("confirmed");
  await page.setViewportSize({width:1280,height:900});
  await page.screenshot({path:"test-results/work-notes-desktop.png",fullPage:true});
  await detail.getByRole("button",{name:"Correct note",exact:true}).click();
  const edit=panel.getByRole("form",{name:"Correct sample note",exact:true});
  await edit.getByLabel("Sample note",{exact:true}).fill("Corrected browser sample");
  const corrected=page.waitForResponse(r=>r.url().endsWith("/correct")&&r.request().method()==="POST");
  await edit.getByRole("button",{name:"Request correction",exact:true}).click();
  apply("app.work_notes_worker",(await(await corrected).json()).change_request_id);
  await panel.getByRole("button",{name:"Recover or refresh request status",exact:true}).click();
  await panel.getByRole("button",{name:"Open resulting note",exact:true}).click();
  await expect(detail).toContainText("Corrected browser sample");
  await expect(detail).toContainText("draft");
  await detail.getByRole("button",{name:"Forget note",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"Forget this sample note?",exact:true});
  await dialog.getByRole("button",{name:"Keep note",exact:true}).click();
  await expect(detail).toBeVisible();
  await detail.getByRole("button",{name:"Forget note",exact:true}).click();
  const forgotten=page.waitForResponse(r=>r.url().endsWith("/forget")&&r.request().method()==="POST");
  await dialog.getByRole("button",{name:"Request forgetting",exact:true}).click();
  apply("app.work_notes_worker",(await(await forgotten).json()).change_request_id);
  await panel.getByRole("button",{name:"Recover or refresh request status",exact:true}).click();
  await expect(panel.getByRole("region",{name:"Request outcome",exact:true})).toContainText("Applied at version 4");
  await panel.getByRole("button",{name:"Reload notes and options",exact:true}).click();
  await expect(panel).not.toContainText("Corrected browser sample");
});
test("ambiguous response recovers one request and denial or late read cannot restore private content",async({page})=>{
  test.setTimeout(60000);
  const panel=await open(page);
  const form=await fill(page,"Recovered browser sample");
  let captureId="";let calls=0;
  await page.route("**/api/v1/work/workspaces/*/captures",async route=>{
    calls+=1;const response=await route.fetch();captureId=(await response.json()).capture_preparation_id;
    await route.abort("failed");
  });
  await form.getByRole("button",{name:"Request save",exact:true}).click();
  await expect(panel.getByRole("alert")).toContainText("uncertain");
  await panel.getByRole("button",{name:"Recover or refresh request status",exact:true}).click();
  await expect(panel.getByRole("region",{name:"Request outcome",exact:true})).toContainText("Awaiting processing");
  expect(calls).toBe(1);
  apply("app.work_capture_worker",captureId);
  await panel.getByRole("button",{name:"Recover or refresh request status",exact:true}).click();
  await panel.getByRole("button",{name:"Open resulting note",exact:true}).click();
  await expect(panel.getByRole("region",{name:"Selected work note",exact:true})).toContainText("Recovered browser sample");
  await page.route("**/notes/catalogue",route=>route.fulfill({status:403,json:{detail:"Denied"}}));
  await panel.getByRole("button",{name:"Reload notes and options",exact:true}).click();
  await expect(panel.getByRole("alert")).toBeVisible();
  await expect(panel).not.toContainText("Recovered browser sample");
  await page.unroute("**/notes/catalogue");
  await panel.getByRole("button",{name:"Open synthetic notes",exact:true}).click();
  let release!:()=>void;const hold=new Promise<void>(resolve=>{release=resolve;});
  let reached!:()=>void;const started=new Promise<void>(resolve=>{reached=resolve;});
  await page.route("**/notes/*/inspect",async route=>{
    const response=await route.fetch();reached();await hold;
    try{await route.fulfill({response});}catch{/* aborted on view change */}
  });
  await panel.getByRole("button",{name:/Recovered browser sample.*draft/}).click();
  await started;
  await page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name:"Memory",exact:true}).click();
  release();
  await expect(page.getByRole("region",{name:"Synthetic Work notes",exact:true})).toHaveCount(0);
  await expect(page.getByRole("region",{name:"Memory",exact:true})).toBeVisible();
});

test("preview expiry removes edited content and unavailable credentials clear the catalogue",async({page})=>{
  await page.clock.install();
  const panel=await open(page);
  await fill(page,"Ephemeral browser sample");
  await page.clock.fastForward(61000);
  await expect(panel.getByRole("form",{name:"New sample note",exact:true})).toHaveCount(0);
  await expect(panel).not.toContainText("Ephemeral browser sample");
  await expect(panel.getByRole("button",{name:"Open synthetic notes",exact:true})).toBeVisible();
  await panel.getByRole("button",{name:"Open synthetic notes",exact:true}).click();
  await expect(panel.getByRole("button",{name:"New sample note",exact:true})).toBeEnabled();
  await page.route("**/notes/catalogue",route=>route.fulfill({status:503,json:{detail:"Synthetic notes unavailable"}}));
  await panel.getByRole("button",{name:"Reload notes and options",exact:true}).click();
  await expect(panel.getByRole("alert")).toBeVisible();
  await expect(panel.getByRole("button",{name:"New sample note",exact:true})).toHaveCount(0);
});
