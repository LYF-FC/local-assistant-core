import { expect, it } from "vitest";
import { privateFirstScopes } from "./scope-preference";
it("keeps a granted personal scope ahead of alphabetically earlier shared records",()=>{
 expect(privateFirstScopes(["household_shared","member_a_private"])).toEqual(["member_a_private","household_shared"]);
});
it("prefers the other granted private member without inventing a grant",()=>{
 expect(privateFirstScopes(["household_shared","member_b_private"])).toEqual(["member_b_private","household_shared"]);
});
it("keeps membership contents and the original array unchanged",()=>{
 const scopes=["technical_admin","member_business","finance_private","parents_child"];
 expect(privateFirstScopes(scopes)).toEqual(["finance_private","technical_admin","member_business","parents_child"]);
 expect(scopes).toEqual(["technical_admin","member_business","finance_private","parents_child"]);
});
it("keeps an explicit shared-only or empty grant set unchanged",()=>{
 expect(privateFirstScopes(["household_shared"])).toEqual(["household_shared"]);
 expect(privateFirstScopes([])).toEqual([]);
});
