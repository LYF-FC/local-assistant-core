import {test,expect,type Page,type Download} from "@playwright/test";
import {readFileSync} from "node:fs";

test.skip(process.env.BUTLER_PDF_BROWSER_TESTS!=="1","Requires the isolated PDF worker phase");
const cases: {name:string;original:string;status:string;text:string;pages:number}[]=process.env.BUTLER_PDF_BROWSER_TESTS==="1"?JSON.parse(readFileSync(process.env.BUTLER_PDF_BROWSER_CASES!,"utf8")):[];
async function login(page:Page,viewer=false){await page.goto("/");await page.getByLabel("Username",{exact:true}).fill(viewer?"browser-documents-viewer":"browser-documents-owner");await page.getByLabel("Password",{exact:true}).fill("synthetic-browser-password-only-0123456789");const response=page.waitForResponse(r=>r.url().endsWith("/api/v1/auth/login"));await page.getByRole("button",{name:"Sign in",exact:true}).click();const r=await response;expect(r.status()).toBe(200);const csrf=(await r.json()).csrf_token;await page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name:"Documents",exact:true}).click();await expect(page.getByRole("button",{name:"Reload documents",exact:true})).toBeEnabled();return csrf;}
async function draft(page:Page,name:string,title:string){await page.getByRole("button",{name:"Upload document",exact:true}).click();await page.getByLabel("Document title",{exact:true}).fill(title);await page.getByLabel("Original file",{exact:true}).setInputFiles({name:"synthetic.pdf",mimeType:"application/pdf",buffer:Buffer.from(cases.find(x=>x.name===name)!.original,"base64")});}
async function add(page:Page,name:string,title:string){await draft(page,name,title);const response=page.waitForResponse(r=>r.url().endsWith("/api/v1/documents")&&r.request().method()==="POST");await page.getByRole("button",{name:"Save document",exact:true}).click();const r=await response;expect(r.status()).toBe(201);const row=await r.json();await expect(page.getByRole("form",{name:"Upload document form"})).toHaveCount(0);await page.getByRole("button",{name:title,exact:true}).click();await expect(page.getByRole("region",{name:"PDF extraction",exact:true})).toBeVisible();return row;}
async function downloadBytes(download:Download){const stream=await download.createReadStream();const chunks:Buffer[]=[];for await(const chunk of stream!)chunks.push(chunk);return Buffer.concat(chunks);}

test("PDF originals, reviewed page citations, re-extraction, archive and forgetting work together",async({page})=>{
 await login(page);const row=await add(page,"pages","Synthetic PDF lifecycle");expect(row.extraction.status).toBe("ready");await expect(page.getByRole("region",{name:"PDF extraction",exact:true})).toContainText("2 pages");await page.getByRole("button",{name:"Correct and review",exact:true}).click();await page.getByRole("form",{name:"Correct document form"}).getByRole("checkbox").check();await page.getByRole("button",{name:"Save document",exact:true}).click();await page.getByRole("button",{name:row.title,exact:true}).click();await page.getByLabel("First line",{exact:true}).fill("2");await page.getByLabel("Last line",{exact:true}).fill("2");await page.getByRole("button",{name:"Prepare cited excerpt",exact:true}).click();const excerpt=page.getByRole("region",{name:"Cited document excerpt",exact:true});await expect(excerpt).toContainText("Second café");await expect(excerpt).toContainText("PDF pages 2");await page.getByLabel("Acknowledge document copy limits",{exact:true}).check();const download=page.waitForEvent("download");await page.getByRole("button",{name:"Download current original",exact:true}).click();expect(await downloadBytes(await download)).toEqual(Buffer.from(cases.find(x=>x.name==="pages")!.original,"base64"));await page.getByRole("button",{name:"Re-extract PDF text",exact:true}).click();await expect(page.getByRole("region",{name:"Documents",exact:true}).getByRole("status")).toContainText("new unreviewed version");await expect(excerpt).toHaveCount(0);await expect(page.getByRole("button",{name:"Prepare cited excerpt",exact:true})).toHaveCount(0);await page.getByRole("button",{name:"Document history",exact:true}).click();await expect(page.getByRole("region",{name:"Document version history",exact:true})).toContainText("Revision 3 · extracted");const archive=page.getByRole("region",{name:"Local original archive",exact:true});await archive.getByRole("button",{name:"Check archive",exact:true}).click();await archive.getByRole("button",{name:"Archive originals",exact:true}).click();await expect(archive).toContainText("All 3 original versions verified");await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.evaluate(()=>Array.from(document.querySelectorAll("body *")).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,text:e.textContent?.slice(0,80),width:e.getBoundingClientRect().width})).slice(-10))).toEqual([]);await page.getByRole("region",{name:"Documents",exact:true}).screenshot({path:"test-results/documents-pdf-mobile.png"});await page.getByRole("button",{name:"Forget document",exact:true}).click();await page.getByRole("button",{name:"Confirm forget document",exact:true}).click();await expect(page.getByRole("button",{name:row.title,exact:true})).toHaveCount(0);
});

test("blank, encrypted, invalid and oversized extraction states retain sources without review",async({page})=>{
 await login(page);
 for(const name of ["blank","encrypted","invalid","page-limit"]){
  const fixture=cases.find(x=>x.name===name)!;const row=await add(page,name,`Synthetic PDF ${name}`);expect(row.extraction.status).toBe(fixture.status);await expect(page.getByRole("button",{name:"Prepare cited excerpt",exact:true})).toHaveCount(0);await page.getByRole("button",{name:"Correct and review",exact:true}).click();await expect(page.getByRole("form",{name:"Correct document form"}).getByRole("checkbox")).toBeDisabled();await page.getByRole("button",{name:"Cancel editing",exact:true}).click();
 }
});

test("an uncertain upload response can be retried with the same draft key without duplication",async({page})=>{
 await login(page);let first=true;const identities:string[]=[];
 await page.route("**/api/v1/documents",async route=>{if(route.request().method()!=="POST")return route.continue();const response=await route.fetch();expect(response.status()).toBe(201);identities.push((await response.json()).id);if(first){first=false;await route.fulfill({status:503,json:{detail:"Synthetic interrupted response"}});}else await route.fulfill({response});});
 await draft(page,"one","Synthetic PDF uncertain retry");await page.getByRole("button",{name:"Save document",exact:true}).click();await expect(page.getByRole("alert")).toBeVisible();await page.getByRole("button",{name:"Save document",exact:true}).click();await expect(page.getByRole("form",{name:"Upload document form"})).toHaveCount(0);expect(identities.length).toBe(2);expect(identities[0]).toBe(identities[1]);await expect(page.getByRole("button",{name:"Synthetic PDF uncertain retry",exact:true})).toHaveCount(1);
});

test("shared PDF viewers cannot re-extract or access another creator's private source",async({page,browser})=>{
 await login(page);const privateRow=await add(page,"one","Synthetic private PDF");await page.getByLabel("Document scope",{exact:true}).selectOption("household_shared");const shared=await add(page,"one","Synthetic shared PDF");const context=await browser.newContext({baseURL:process.env.BUTLER_E2E_ORIGIN});try{const viewer=await context.newPage();const csrf=await login(viewer,true);await viewer.getByLabel("Document scope",{exact:true}).selectOption("household_shared");await viewer.getByRole("button",{name:shared.title,exact:true}).click();await expect(viewer.getByRole("button",{name:"Re-extract PDF text",exact:true})).toHaveCount(0);const status=await viewer.evaluate(async({csrf,shared,privateRow})=>{const send=async(row:{id:string;scope:string;revision:number},op:string)=>(await fetch(`/api/v1/documents/${row.id}/${op}`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({scope:row.scope,...(op==="extract"?{expected_revision:row.revision}:{})})})).status;return {shared:await send(shared,"extract"),private:await send(privateRow,"read")};},{csrf,shared,privateRow});expect(status).toEqual({shared:403,private:404});}finally{await context.close();}
});

test("explicit scanned OCR preserves source, uncertainty, review and history",async({page})=>{
 await login(page);
 const row=await add(page,"ocr-scan","Synthetic scanned OCR source");
 expect(row.extraction.status).toBe("no_text");
 const panel=page.getByRole("region",{name:"PDF extraction",exact:true});
 const response=page.waitForResponse(r=>r.url().endsWith(`/${row.id}/extract`));
 await page.getByRole("button",{name:"Run OCR (up to 2 pages)",exact:true}).click();
 const result=await response;expect(result.status()).toBe(200);
 const recognized=await result.json();expect(recognized.extraction.engine).toBe("poppler-tesseract-v1");expect(recognized.sha256).toBe(row.sha256);expect(recognized.reviewed).toBe(false);
 await expect(panel).toContainText("OCR recognition is uncertain");
 await page.getByRole("button",{name:"Correct and review",exact:true}).click();
 await page.getByRole("form",{name:"Correct document form"}).getByRole("checkbox").check();
 await page.getByRole("button",{name:"Save document",exact:true}).click();
 await page.getByRole("button",{name:row.title,exact:true}).click();
 await page.getByRole("button",{name:"Prepare cited excerpt",exact:true}).click();
 const cited=page.getByRole("region",{name:"Cited document excerpt",exact:true});
 await expect(cited).toContainText("Synthetic invoice");await expect(cited).toContainText("uncertain OCR");await expect(cited).toContainText("PDF pages 1");
 await page.getByLabel("Acknowledge document copy limits",{exact:true}).check();
 const downloaded=page.waitForEvent("download");await page.getByRole("button",{name:"Download current original",exact:true}).click();
 expect(await downloadBytes(await downloaded)).toEqual(Buffer.from(cases.find(x=>x.name==="ocr-scan")!.original,"base64"));
 await page.getByRole("button",{name:"Document history",exact:true}).click();
 await expect(page.getByRole("region",{name:"Document version history",exact:true})).toContainText("Uncertain OCR");
 await page.getByRole("button",{name:"Run OCR (up to 2 pages)",exact:true}).click();
 await expect(page.getByRole("region",{name:"Documents",exact:true}).getByRole("status")).toContainText("new unreviewed version");
 await expect(cited).toHaveCount(0);await expect(page.getByRole("button",{name:"Prepare cited excerpt",exact:true})).toHaveCount(0);
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole("button",{name:"Forget document",exact:true}).click();await page.getByRole("button",{name:"Confirm forget document",exact:true}).click();
 await expect(page.getByRole("button",{name:row.title,exact:true})).toHaveCount(0);
});
