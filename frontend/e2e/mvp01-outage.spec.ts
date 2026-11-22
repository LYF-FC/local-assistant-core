import {expect,test,type Page} from "@playwright/test";
// Spec 077 browser evidence for "the bad-connection day": runs only against the named rehearsal while the simulated
// outage is ON and the invoice-002 filing is waiting (prepared by scripts/mvp01-owner-check.py outage-journey).
// Same public-CA rules as mvp01-owner.spec.ts: ignoreHTTPSErrors stays false.
test.skip(process.env.BUTLER_MVP01_BROWSER_TESTS!=="1"||process.env.BUTLER_MVP01_BROWSER_PHASE!=="outage-ui","Requires the MVP-01 rehearsal in its simulated outage");
const TITLE2="MVP-01 outage-day invoice";
async function login(page:Page){
 const password=process.env.BUTLER_MVP01_OWNER_PASSWORD;if(!password)throw new Error("Synthetic owner password required");
 await page.goto("/");await page.getByLabel("Username",{exact:true}).fill("mvp01-owner");await page.getByLabel("Password",{exact:true}).fill(password);
 await page.getByRole("button",{name:"Sign in",exact:true}).click();await expect(page.getByRole("navigation",{name:"Local records"})).toBeVisible();
}
const nav=(page:Page,name:string)=>page.getByRole("navigation",{name:"Local records"}).getByRole("button",{name,exact:true}).click();
test("outage: waiting filing and unavailable assistant are explained and reachable after sign-in",async({page})=>{
 await login(page);
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 // Attention inbox: the unconfirmed filing, its plain reason, and the link to the document.
 await nav(page,"Attention inbox");
 const inbox=page.getByRole("region",{name:"Attention inbox",exact:true});
 await inbox.getByRole("combobox",{name:/^Inbox scope/}).selectOption("household_shared");
 await inbox.getByRole("button",{name:"Refresh inbox",exact:true}).click();
 const filingGroup=inbox.getByRole("region",{name:"Failures: filing",exact:true});
 await expect(filingGroup).toContainText("Outcome not confirmed");
 await expect(filingGroup).toContainText("Nothing was lost");
 await expect(filingGroup).toContainText("will not write a second time blindly");
 await expect(filingGroup).not.toContainText("Filing failed");
 await filingGroup.getByRole("button",{name:"Open related document",exact:true}).click();
 await expect(page.getByRole("article",{name:"Selected document",exact:true})).toContainText(TITLE2);
 // The filing panel is one labelled click away, not hidden without explanation.
 await expect(page.getByText(/After you load the invoice review/)).toBeVisible();
 await page.getByRole("button",{name:"Load invoice review",exact:true}).click();
 const exec=page.getByRole("region",{name:"Synthetic filing execution",exact:true});
 await expect(exec).toContainText("Nothing was lost");
 await expect(exec).not.toContainText("Filed in the synthetic metadata destination");
 await expect(exec.getByRole("button",{name:"Request synthetic filing",exact:true})).toHaveCount(0);
 // The assistant is stopped: an explicit unavailable answer, while documents stay readable.
 await nav(page,"Document answers");
 await page.getByLabel("Answer scope",{exact:true}).selectOption("household_shared");
 await page.getByLabel("Ask Butler",{exact:true}).fill("What is the total amount?");
 const answered=page.waitForResponse(r=>r.url().endsWith("/api/v1/document-answers"));
 await page.getByRole("button",{name:"Ask reviewed documents",exact:true}).click();
 expect((await answered).status()).toBe(200);
 await expect(page.getByRole("region",{name:"Document answer result",exact:true})).toContainText("Local model unavailable");
});
