'use strict';
// usage: node run.cjs <variantDir> <out.json>
const path = require('path'); const fs = require('fs');
const pm = require(path.resolve(process.argv[2])); const C = require('./corpus.cjs');
const groups = ['G1', 'G1dot', 'G4', 'G2', 'G3', 'G5', 'G6', 'G7']; const out = {};
for (const g of groups) { const cases = C[g](); let bits = ''; let err = 0;
  for (const c of cases) { try { bits += pm.isMatch(c.input, c.pattern, c.opts) ? '1' : '0'; } catch (e) { bits += 'E'; err++; } }
  out[g] = { n: cases.length, bits, err }; }
fs.writeFileSync(process.argv[3], JSON.stringify(out));
console.log(path.basename(process.argv[2]), Object.fromEntries(groups.map(g => [g, out[g].n])));
