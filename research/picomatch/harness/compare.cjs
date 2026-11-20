'use strict';
// usage: node compare.cjs <resultsDir> <variant...>  (stock must be present)
const fs = require('fs'); const C = require('./corpus.cjs');
const dir = process.argv[2]; const vs = process.argv.slice(3);
const R = Object.fromEntries(['stock', ...vs].map(v => [v, JSON.parse(fs.readFileSync(`${dir}/${v}.json`))]));
const rows = []; const ex = {};
for (const g of ['G1', 'G1dot', 'G4', 'G2', 'G3', 'G5', 'G6', 'G7']) {
  const cases = C[g]();
  // independent expectations: G1/G1dot/G4 hand-expected; G7 reference oracle; others differential vs stock
  let exp;
  if (g === 'G7') exp = cases.map(c => C.refMatch(c.pattern, c.input) ? '1' : '0').join('');
  else if (cases[0].expected !== undefined) exp = cases.map(c => c.expected ? '1' : '0').join('');
  for (const v of ['stock', ...vs]) { const b = R[v][g].bits; const s = R.stock[g].bits;
    let vsStock = 0, rej = 0, acc = 0, vsExp = exp ? 0 : null, errs = R[v][g].err;
    for (let i = 0; i < b.length; i++) { if (b[i] !== s[i]) { vsStock++; if (s[i] === '1') rej++; else acc++; (ex[`${v}|${g}`] ||= []).length < 4 && ex[`${v}|${g}`].push(`${JSON.stringify(cases[i].pattern)} ${JSON.stringify(cases[i].input)} ${JSON.stringify(cases[i].opts)} stock=${s[i]} cand=${b[i]}`); }
      if (exp && b[i] !== exp[i]) vsExp++; }
    rows.push({ group: g, variant: v, total: b.length, passVsStock: b.length - vsStock, mismatchVsStock: vsStock, rejectsValid: rej, acceptsInvalid: acc, mismatchVsIndependentExpectation: vsExp, thrown: errs }); } }
console.table(rows.map(r => ({ ...r })));
fs.writeFileSync(`${dir}/summary.json`, JSON.stringify({ rows, examples: ex }, null, 1));
if (process.env.EX) for (const [k, v] of Object.entries(ex)) { console.log(k); v.forEach(x => console.log('   ', x)); }
