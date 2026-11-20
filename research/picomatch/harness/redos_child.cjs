// child: node redos_child.cjs <variantDir> <pattern> <family>; prints "n ms" lines as it ladders (parent enforces wall timeout)
const pm = require(require('path').resolve(process.argv[2])); const pat = process.argv[3]; const fam = process.argv[4];
const mk = { a: n => 'a'.repeat(n) + '?', slash: n => 'a/'.repeat(n >> 1) + '?', ab: n => 'ab'.repeat(n >> 1) + '!' }[fam];
const ladder = [10, 14, 18, 22, 26, 30, 34, 40, 100, 1000, 10000, 50000];
let re; const t0 = process.hrtime.bigint(); try { re = pm.makeRe(pat); } catch (e) { console.log('THROW ' + e.message.slice(0, 60)); process.exit(0); }
console.log('compile ' + (Number(process.hrtime.bigint() - t0) / 1e6).toFixed(2) + ' srclen ' + re.source.length);
for (const n of ladder) { const s = mk(n); const t = process.hrtime.bigint(); pm.isMatch(s, pat); console.log(n + ' ' + (Number(process.hrtime.bigint() - t) / 1e6).toFixed(2)); }
