/** Prefer explicitly granted personal scopes; identifier spelling cannot imply sharing. */
export function privateFirstScopes(scopes: readonly string[]): string[] {
  const order = ["member_a_private", "member_b_private", "finance_private"];
  const rank = (scope: string) => { const index = order.indexOf(scope); return index < 0 ? order.length : index; };
  return [...scopes].sort((left, right) => rank(left) - rank(right));
}
