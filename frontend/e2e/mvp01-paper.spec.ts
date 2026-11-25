import {expect,test,type Page,type BrowserContext} from "@playwright/test";
// Spec 078 browser evidence for "the paper invoice": runs only against the named rehearsal (or a disposable copy) after
// `scripts/mvp01-owner-check.py paper-journey` (P1 text PDF and P2 scan, both filed), with the hostile test PDF imported
// by `paper-hostile-import`. Same public-CA rules as the earlier MVP-01 specs: ignoreHTTPSErrors stays false.
// Phases: paper-ui (worker running), paper-down (worker stopped, P3 imported by paper-worker-down).
// Assertions are on states and wording, never on OCR text.
const phase=process.env.BUTLER_MVP01_BROWSER_PHASE;
test.skip(process.env.BUTLER_MVP01_BROWSER_TESTS!=="1"||!["paper-ui","paper-down"].includes(phase??""),"Requires the MVP-01 rehearsal with the paper-invoice fixtures");
const T={malformed:"MVP-01 malformed test PDF",huge:"MVP-01 huge-page test PDF",pdf:"MVP-01 paper invoice (text PDF)",scan:"MVP-01 paper invoice (scan)",offline:"MVP-01 paper invoice (worker stopped)",hostile:"MVP-01 hostile test PDF"};
async function login(page:Page){
 const password=process.env.BUTLER_MVP01_OWNER_PASSWORD;if(!password)throw new Error("Synthetic owner password required");
 await page.goto("/");await page.getByLabel("Username",{exact:true}).fill("mvp01-owner");await page.getByLabel("Password",{exact:true}).fill(password);
 await page.getByRole("button",{name:"Sign in",exact:true}).click();await expect(page.getByRole("navigation",{name:"Local records"})).toBeVisible();
}
const nav=(page:Page,name:string)=>page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name,exact:true}).click();
async function openDocuments(page:Page){
 await nav(page,"Documents");
 const panel=page.getByRole("region",{name:"Documents",exact:true});
 await panel.getByLabel("Document scope",{exact:true}).selectOption("household_shared");
 await expect(panel.getByRole("listitem").first()).toBeVisible();
 return panel;
}
async function viewOriginal(page:Page,scope:{getByRole:Page["getByRole"]}){
 // The in-page view stays behind the same acknowledgement as the download.
 const view=scope.getByRole("button",{name:"View original pages",exact:true});
 await expect(view).toBeDisabled();
 await page.getByLabel("Acknowledge document copy limits",{exact:true}).check();
 await view.click();
}
const noOverflow=(page:Page)=>expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
// A drawn page is not blank: pixels darker than the page background exist (the scan has a grey, low-contrast background).
const hasInk=(page:Page,label:RegExp)=>page.getByRole("img",{name:label}).first().evaluate((c:HTMLCanvasElement)=>{
 const d=c.getContext("2d")!.getImageData(0,0,c.width,c.height).data;let dark=0;for(let i=0;i<d.length;i+=4)if(d[i]<215&&d[i+3]>0)dark++;return dark;
});

// One sign-in per phase (the account allows 5 per 15 minutes and the limiter is never cleared): the tests share a page.
let context:BrowserContext,shared:Page;
test.describe.configure({mode:"serial"});
test.beforeAll(async({browser})=>{
 context=await browser.newContext({baseURL:process.env.BUTLER_E2E_ORIGIN,ignoreHTTPSErrors:false});shared=await context.newPage();shared.on("console",m=>logs.push(`${m.type()}: ${m.text()}`));shared.on("pageerror",e=>logs.push(`pageerror: ${e.message}`));shared.on("requestfailed",r=>logs.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`));await login(shared);
});
const logs:string[]=[];
test.afterEach(async({},info)=>{if(info.status!==info.expectedStatus)console.log("PAGE LOG:\n"+logs.splice(0).join("\n"));else logs.length=0;});
test.afterAll(async()=>{await context?.close();});
test.describe("paper-ui",()=>{
 test.skip(phase!=="paper-ui","Phase paper-ui only");
 test("list badges, in-page original, OCR wording, Unknown is not zero, no horizontal scroll",async()=>{
  const page=shared;
  const requests:string[]=[];page.on("request",r=>requests.push(r.url()));
  const panel=await openDocuments(page);
  // Badges tell the extraction state of every PDF at a glance.
  await expect(panel.getByRole("listitem").filter({hasText:T.pdf})).toContainText("Text extracted");
  await expect(panel.getByRole("listitem").filter({hasText:T.scan})).toContainText("OCR text (uncertain)");
  // Text PDF: the original is shown as rendered pages in the page, not embedded and not downloaded.
  await panel.getByRole("button",{name:T.pdf,exact:true}).click();
  const detail=page.getByRole("article",{name:"Selected document",exact:true});
  await expect(detail).toContainText("Text extracted");
  await viewOriginal(page,detail);
  await expect(detail.getByRole("img",{name:/Original page 1 of 1/})).toBeVisible();
  expect(await hasInk(page,/Original page 1 of 1/)).toBeGreaterThan(50);
  await expect(page.locator("iframe, embed, object")).toHaveCount(0);
  await expect(detail).toContainText("no PDF script, link or form is run");
  await expect(detail).toContainText("not verified confinement");
  // Scan after OCR: says OCR is uncertain and that a line can be missing; the original shows beside the text.
  await panel.getByRole("button",{name:T.scan,exact:true}).click();
  const scan=page.getByRole("article",{name:"Selected document",exact:true});
  await expect(scan.getByRole("region",{name:"PDF extraction",exact:true})).toContainText("line can be missing");
  await viewOriginal(page,scan);
  await expect(scan.getByRole("img",{name:/Original page 1 of 1/})).toBeVisible();
  expect(await hasInk(page,/Original page 1 of 1/)).toBeGreaterThan(50);
  // The plan and the filing view say Unknown is not zero once the review is loaded.
  await scan.getByRole("button",{name:"Load invoice review",exact:true}).click();
  await expect(page.getByRole("region",{name:"Invoice filing plan",exact:true})).toContainText("Unknown is not zero");
  await expect(page.getByRole("region",{name:"Synthetic filing execution",exact:true})).toContainText("Unknown is not zero");
  await expect(page.getByRole("region",{name:"Synthetic filing execution",exact:true})).toContainText("Filed in the synthetic metadata destination");
  // Mobile width: no horizontal scroll with a drawn page.
  await page.setViewportSize({width:390,height:844});await noOverflow(page);
  expect(requests.filter(u=>/example\.invalid/.test(u))).toEqual([]);
 });
 test("hostile PDF: its original is drawn as an image only, with no script, no dialog and no request to an external host",async()=>{
  const page=shared;
  const external:string[]=[];page.on("request",r=>{const u=r.url();if(!u.startsWith(process.env.BUTLER_E2E_ORIGIN??"https://localhost"))external.push(u);});
  const dialogs:string[]=[];page.on("dialog",async d=>{dialogs.push(d.message());await d.dismiss();});
  const popups:string[]=[];page.on("popup",p=>popups.push(p.url()));
  await page.setViewportSize({width:1280,height:900});await page.goto("/");await expect(page.getByRole("navigation",{name:"Local records"})).toBeVisible();
  const panel=await openDocuments(page);
  await panel.getByRole("button",{name:T.hostile,exact:true}).click();
  const detail=page.getByRole("article",{name:"Selected document",exact:true});
  await viewOriginal(page,detail);
  await expect(detail.getByRole("img",{name:/Original page 1 of 1/}).or(detail.getByRole("alert"))).toBeVisible();
  // Click where the link annotation sits in the PDF: nothing may navigate, open or request.
  const canvas=detail.getByRole("img",{name:/Original page 1 of 1/});
  if(await canvas.count()){const box=(await canvas.boundingBox())!;await page.mouse.click(box.x+box.width*0.2,box.y+box.height*0.08);}
  await page.waitForTimeout(1500);
  expect(dialogs).toEqual([]);expect(popups).toEqual([]);
  expect(external.filter(u=>/example\.invalid/.test(u))).toEqual([]);
  expect(page.url().startsWith(process.env.BUTLER_E2E_ORIGIN??"https://localhost")).toBe(true);
  await expect(page.locator("iframe, embed, object")).toHaveCount(0);
 });
test("opening another document never shows the previous original or keeps its confirmations",async()=>{
  const page=shared;await page.setViewportSize({width:1280,height:900});await page.goto("/");
  const panel=await openDocuments(page);
  await panel.getByRole("button",{name:T.pdf,exact:true}).click();
  let detail=page.getByRole("article",{name:"Selected document",exact:true});
  await viewOriginal(page,detail);
  await expect(detail.getByRole("img",{name:/Original page 1 of 1/})).toBeVisible();
  await panel.getByRole("button",{name:T.scan,exact:true}).click();
  detail=page.getByRole("article",{name:"Selected document",exact:true});
  await expect(detail).toContainText(T.scan);
  await expect(page.getByRole("region",{name:"Original pages",exact:true})).toHaveCount(0);
  await expect(page.getByRole("img",{name:/Original page/})).toHaveCount(0);
  await expect(page.getByLabel("Acknowledge document copy limits",{exact:true})).not.toBeChecked();
  await expect(detail.getByRole("button",{name:"View original pages",exact:true})).toBeDisabled();
 });
 test("damaged and oversized-page PDFs end in a visible state, never a blank or a crash",async()=>{
  const page=shared;const crashes:string[]=[];page.on("pageerror",e=>crashes.push(e.message));page.on("crash",()=>crashes.push("page crashed"));
  await page.setViewportSize({width:1280,height:900});await page.goto("/");
  const panel=await openDocuments(page);
  // Damaged PDF: either the view says it could not be shown, or (if the viewer repairs it) a page is drawn; never nothing.
  await panel.getByRole("button",{name:T.malformed,exact:true}).click();
  let detail=page.getByRole("article",{name:"Selected document",exact:true});
  await viewOriginal(page,detail);
  await expect(detail.getByRole("alert").or(detail.getByRole("img",{name:/Original page 1/}))).toBeVisible({timeout:15000});
  // Oversized page: drawn within the canvas budget (small pixel count), or a visible failure.
  await panel.getByRole("button",{name:T.huge,exact:true}).click();
  detail=page.getByRole("article",{name:"Selected document",exact:true});
  await viewOriginal(page,detail);
  await expect(detail.getByRole("alert").or(detail.getByRole("img",{name:/Original page 1/}))).toBeVisible({timeout:15000});
  const canvas=detail.getByRole("img",{name:/Original page 1/});
  if(await canvas.count()){const px=await canvas.evaluate((c:HTMLCanvasElement)=>c.width*c.height);expect(px).toBeLessThanOrEqual(4_000_001);}
  await page.setViewportSize({width:390,height:844});await noOverflow(page);
  expect(crashes).toEqual([]);
 });
});

test.describe("paper-down",()=>{
 test.skip(phase!=="paper-down","Phase paper-down only");
 test("worker stopped: honest unavailable wording, original kept, repeated attempts are guarded and visible",async()=>{
  const page=shared;
  const panel=await openDocuments(page);
  await expect(panel.getByRole("listitem").filter({hasText:T.offline})).toContainText("Extraction unavailable");
  await panel.getByRole("button",{name:T.offline,exact:true}).click();
  const detail=page.getByRole("article",{name:"Selected document",exact:true});
  const section=detail.getByRole("region",{name:"PDF extraction",exact:true});
  await expect(section).toContainText("offline");
  await expect(section).toContainText("original is kept");
  await expect(section).toContainText("pdf-worker start");
  await expect(section).not.toContainText(/\bfailed\b/i);
  // UI guard: no attempt can be clicked until the owner confirms the worker is back; the state stays visible.
  await expect(section.getByRole("button",{name:"Re-extract PDF text",exact:true})).toBeDisabled();
 // The confirmation belongs to this document: tick it, open another document and come back: it is unticked and locked again.
 await section.getByLabel("I started the PDF worker and want to try again",{exact:true}).check();
 await expect(section.getByRole("button",{name:"Re-extract PDF text",exact:true})).toBeEnabled();
 await panel.getByRole("button",{name:T.pdf,exact:true}).click();
 await panel.getByRole("button",{name:T.offline,exact:true}).click();
 const again=page.getByRole("article",{name:"Selected document",exact:true}).getByRole("region",{name:"PDF extraction",exact:true});
 await expect(again.getByLabel("I started the PDF worker and want to try again",{exact:true})).not.toBeChecked();
 await expect(again.getByRole("button",{name:"Re-extract PDF text",exact:true})).toBeDisabled();
 await expect(section.getByRole("button",{name:"Re-extract PDF text",exact:true})).toBeDisabled();
  await expect(section.getByRole("button",{name:"Run OCR (up to 2 pages)",exact:true})).toBeDisabled();
  await expect(section).toContainText("unavailable");
  // The original stays viewable while the parser is offline.
  await viewOriginal(page,section);
  await expect(detail.getByRole("img",{name:/Original page 1 of 1/})).toBeVisible();
  await page.setViewportSize({width:390,height:844});await noOverflow(page);
 });
});
