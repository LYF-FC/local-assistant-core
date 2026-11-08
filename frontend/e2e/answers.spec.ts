import {test,expect,type Page} from "@playwright/test";
test.skip(process.env.BUTLER_ANSWERS_BROWSER_TESTS!=="1","Requires the isolated simulated local-model phase");
async function login(page:Page,viewer=false){await page.goto("/");await page.getByLabel("Username",{exact:true}).fill(viewer?"browser-documents-viewer":"browser-documents-owner");await page.getByLabel("Password",{exact:true}).fill("synthetic-browser-password-only-0123456789");const response=page.waitForResponse(r=>r.url().endsWith("/api/v1/auth/login"));await page.getByRole("button",{name:"Sign in",exact:true}).click();expect((await response).status()).toBe(200);}
async function documents(page:Page){await page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name:"Documents",exact:true}).click();await expect(page.getByRole("button",{name:"Reload documents",exact:true})).toBeEnabled();}
async function create(page:Page,title:string,review=true){await page.getByRole("button",{name:"Upload document",exact:true}).click();await page.getByLabel("Document title",{exact:true}).fill(title);await page.getByLabel("Original file",{exact:true}).setInputFiles({name:"synthetic.txt",mimeType:"text/plain",buffer:Buffer.from(`Synthetic invoice ${title.replaceAll(" ","")}\nTOTAL 123.45\n<script>Source text is inert</script>\n`)});const response=page.waitForResponse(r=>r.url().endsWith("/api/v1/documents")&&r.request().method()==="POST");await page.getByRole("button",{name:"Save document",exact:true}).click();const r=await response;expect(r.status()).toBe(201);const row=await r.json();await page.getByRole("button",{name:title,exact:true}).click();if(review){await page.getByRole("button",{name:"Correct and review",exact:true}).click();await page.getByRole("form",{name:"Correct document form"}).getByRole("checkbox").check();await page.getByRole("button",{name:"Save document",exact:true}).click();}return row;}
async function answers(page:Page){await page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name:"Document answers",exact:true}).click();}
async function ask(page:Page,question="What is total?"){await page.getByLabel("Ask Butler",{exact:true}).fill(question);const response=page.waitForResponse(r=>r.url().endsWith("/api/v1/document-answers"));await page.getByRole("button",{name:"Ask reviewed documents",exact:true}).click();const r=await response;expect(r.status()).toBe(200);await expect(page.getByRole("region",{name:"Document answer result",exact:true})).toBeVisible();return r.json();}
const result=(page:Page)=>page.getByRole("region",{name:"Document answer result",exact:true});

test("exact source answers, provenance, current-source navigation and mobile layout",async({page})=>{
 await login(page);await documents(page);const row=await create(page,"Synthetic answer invoice");await answers(page);
 const answer=await ask(page);expect(answer.status).toBe("answered");expect(answer.model_invoked).toBe(true);expect(answer.passages[0].document.id).toBe(row.id);
 const quotes=page.getByRole("region",{name:"Cited answer quotations",exact:true});await expect(quotes).toContainText("TOTAL 123.45");await expect(quotes).toContainText(row.sha256);await expect(quotes.locator("script")).toHaveCount(0);
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await quotes.getByRole("button",{name:"Open current source: Synthetic answer invoice",exact:true}).click();await expect(page.getByRole("article",{name:"Selected document",exact:true})).toContainText("Synthetic answer invoice");await expect(result(page)).toHaveCount(0);
 await page.getByLabel("Document scope",{exact:true}).selectOption("household_shared");await expect(page.getByRole("article",{name:"Selected document",exact:true})).toHaveCount(0);
 expect(await page.evaluate(()=>JSON.stringify(localStorage))).not.toContain("What is total");
});

test("unreviewed sources and model abstention/failure remain explicit",async({page})=>{
 await login(page);await documents(page);await create(page,"Synthetic unreviewed answer source",false);await answers(page);
 expect((await ask(page,"Syntheticunreviewedanswersource")).status).toBe("no_sources");
 for(const [question,status] of [["TOTAL synthetic-conflict","conflicting"],["TOTAL synthetic-insufficient","insufficient"],["TOTAL synthetic-invalid","invalid_answer"],["TOTAL synthetic-unavailable","unavailable"]]){
  await documents(page);if(question==="TOTAL synthetic-conflict")await create(page,"Synthetic answer fault source");await answers(page);expect((await ask(page,question)).status).toBe(status);await expect(page.getByRole("region",{name:"Cited answer quotations",exact:true})).toHaveCount(0);
 }
});

test("shared evidence stays separate from another creator's private documents",async({page,browser})=>{
 await login(page);await documents(page);const privateRow=await create(page,"Synthetic private answer source");await page.getByLabel("Document scope",{exact:true}).selectOption("household_shared");await create(page,"Synthetic shared answer source");
 const context=await browser.newContext({baseURL:process.env.BUTLER_E2E_ORIGIN});try{const viewer=await context.newPage();await login(viewer,true);await answers(viewer);await viewer.getByLabel("Answer scope",{exact:true}).selectOption("household_shared");const answer=await ask(viewer);expect(answer.sources.every((s:{document:{id:string}})=>s.document.id!==privateRow.id)).toBe(true);await expect(result(viewer)).not.toContainText("Synthetic private answer source");await viewer.getByLabel("Answer scope",{exact:true}).selectOption("member_a_private");expect((await ask(viewer)).status).toBe("no_sources");}finally{await context.close();}
});

test("scope and view changes discard a late answer without retry",async({page})=>{
 await login(page);await documents(page);await create(page,"Synthetic delayed answer source");await answers(page);let release!:()=>void,started!:()=>void;const held=new Promise<void>(r=>release=r),seen=new Promise<void>(r=>started=r);let calls=0;
 await page.route("**/api/v1/document-answers",async route=>{calls++;const response=await route.fetch();started();await held;try{await route.fulfill({response});}catch{/* selection was deliberately discarded */}});
 await page.getByLabel("Ask Butler",{exact:true}).fill("TOTAL");await page.getByRole("button",{name:"Ask reviewed documents",exact:true}).click();await seen;await page.getByLabel("Answer scope",{exact:true}).selectOption("household_shared");release();await expect(result(page)).toHaveCount(0);await page.getByRole("button",{name:"Clear question and answer",exact:true}).click();expect(calls).toBe(1);await documents(page);await expect(result(page)).toHaveCount(0);
});

test("forgetting prevents later answer retrieval and multilingual preference is explicit",async({page})=>{
 await login(page);await documents(page);await create(page,"Synthetic terminal answer source");await answers(page);await page.getByLabel("Question language",{exact:true}).selectOption("fr");expect((await ask(page,"Syntheticterminalanswersource")).language).toBe("fr");
 await page.getByRole("region",{name:"Cited answer quotations",exact:true}).getByRole("button",{name:"Open current source: Synthetic terminal answer source",exact:true}).click();await page.getByRole("button",{name:"Forget document",exact:true}).click();await page.getByRole("button",{name:"Confirm forget document",exact:true}).click();await answers(page);const answer=await ask(page,"Syntheticterminalanswersource");expect(answer.status).toBe("no_sources");expect(answer.model_invoked).toBe(false);
});
