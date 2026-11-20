'use strict';
// Compatibility corpus generator. Pure data; no picomatch loaded here.
// Groups: G1 callsite (hand-expected), G2 existing(PR55 style), G3 bracket(PR55 style),
// G4 witnesses (hand-expected), G5 families, G6 inside-extglob, G7 reference-oracle set.

const gen = (alpha, maxLen) => { const out = ['']; let lv = ['']; for (let l = 1; l <= maxLen; l++) { lv = lv.flatMap(p => alpha.map(c => p + c)); out.push(...lv); } return out; };

function G1() { // [pattern, input, options, expected]  expected from reasoning, not from picomatch
  const inc = '**/*.{test,spec}.?(c|m)[jt]s?(x)';
  const T = [
    [inc, 'src/App.test.tsx', true], [inc, 'src/a/b/c.spec.mjs', true], [inc, 'x.test.cts', true],
    [inc, 'src/App.tsx', false], [inc, 'src/App.test.css', false], [inc, 'src/App.test.jsxx', false],
    [inc, 'node_modules/p/x.test.ts', true], // include is path-agnostic; exclude handles node_modules
    ['**/node_modules/**', 'node_modules/a/b.js', true], ['**/node_modules/**', 'src/a.js', false],
    ['**/node_modules/**', 'a/node_modules/b/c.js', true],
    ['**/.git/**', '.git/config', true], // CORRECTED: a literal '.git' in the pattern matches a leading dot (initial hand expectation 'false' was wrong)
    ['**/*.{bench,benchmark}.?(c|m)[jt]s?(x)', 'a/b.bench.ts', true],
    ['**/*.{test,spec}-d.?(c|m)[jt]s?(x)', 'a/b.test-d.ts', true],
    ['**/package.json', 'package.json', true], ['**/package.json', 'a/b/package.json', true],
    ['**/{vitest,vite}.config.*', 'vite.config.ts', true], ['**/{vitest,vite}.config.*', 'a/vitest.config.mts', true],
    ['**/*.timestamp-*', 'a/vite.config.ts.timestamp-123.mjs', true], ['**/virtual:*', 'a/virtual:x', true],
    ['src/**', 'src/a/b.ts', true], ['src/**', 'srcx/a.ts', false], ['src/*.ts', 'src/a/b.ts', false],
    ['src/*.ts', 'src/a.ts', true], ['**/*', 'a/b/c', true], ['*', 'a/b', false],
  ];
  return T.map(([p, s, e]) => [p, s, e === undefined ? {} : {}, e]).map(([p, s, o, e], i) => ({ id: 'G1:' + i, pattern: p, input: s, opts: i === 10 ? {} : {}, expected: e }));
}

function G1dot() { // with dot:true as tinyglobby passes for ignore
  return [['**/.git/**', '.git/config', true], ['**/.git/**', 'a/.git/x', true], ['**/node_modules/**', '.x/node_modules/a', true]]
    .map(([p, s, e], i) => ({ id: 'G1dot:' + i, pattern: p, input: s, opts: { dot: true }, expected: e }));
}

function G4() { // slash-class witnesses; expected true/false from language definition
  const T = [];
  for (const o of [{}, { dot: true }, { windows: true }, { capture: true }])
    for (const s of ['a/b', 'a/b/a', 'aba/', '//']) T.push(['+([ab/]*)', s, o, true]);
  T.push(['+([ab/]*a)', 'aa/a', {}, true], ['+([ab/]a*)', 'aa/a', {}, true], ['+(*[ab/]a)', '/aaa', {}, true],
    ['+(a[ab/]*)', 'aaa/', {}, true], ['+([ab/]*[ab/])', 'aa/a', {}, true],
    ['+([ab/]*[ab/])', '///', {}, false], ['+([ab/]*[ab/])', '////', {}, true],
    ['+([ab/]*)', 'a/c', {}, true] /* CORRECTED: [ab/] consumes '/', '*' consumes 'c' in iteration 2 */, ['+(*a)', 'aba', {}, true], ['+(*a)', 'abb', {}, false],
    ['*([ab/]*)', '', {}, false] /* CORRECTED: picomatch never matches the empty string */, ['*([ab/]*)', 'a/b/', {}, true]);
  return T.map(([p, s, o, e], i) => ({ id: 'G4:' + i, pattern: p, input: s, opts: o, expected: e }));
}

const P2 = ['+(*)', '+(*a)', '*(*a)', '+(a*)', '+(a*b)', '*(a*b)c', '+(a*b*c)', 'x+(*a)y', '+(a?)', '+([ab]*)', '+(\\*a)', '+(foo|bar)', '**/*.ts', '**.ts', '[!a]', 'a/**/b', '*(*.js)', '!(*.ts)'];
const O2 = [{}, { dot: true }, { bash: true }, { windows: true }, { nocase: true }, { capture: true }, { maxExtglobRecursion: false }];
function G2() { const I = gen(['a', 'b', '.', '/'], 4), out = []; let i = 0;
  for (const p of P2) for (const o of O2) for (const s of I) out.push({ id: 'G2:' + i++, pattern: p, input: s, opts: o }); return out; }

const CLS = ['[ab/]', '[ab]', '[^a]', '[^/]', '[a/]', '[a\\\\]', '[!/]', '[/]', '[a\n]'];
const O3 = [{}, { dot: true }, { windows: true }, { capture: true }, { bash: true }, { literalBrackets: true }, { literalBrackets: false }, { windows: true, capture: true }, { bash: true, capture: true }, { nocase: true }, { bash: true, flags: 's' }, { bash: true, capture: true, flags: 's' }];
function G3() { const pats = CLS.flatMap(c => [`+(${c}*)`, `*(${c}*)`, `+(*${c})`, `*(*${c})`, `x+(${c}*)y`, `+(${c}*)!`]);
  const I = ['', 'a/b', 'a/b/a', 'aba/', '//', '[ab/]a', '[ab/][ab/]', '[/]', '[^/]', 'a\\b', 'a\nb', 'a\rb', 'a b', 'a b'];
  I.push(...gen(['a', 'b', '/', '\\', '\n', '[', ']'], 3)); for (const c of CLS) I.push(c, c + c, 'a' + c + c, c + 'a/b', c + '\n', c + 'a' + c);
  const out = []; let i = 0; for (const p of pats) for (const o of O3) for (const s of I) out.push({ id: 'G3:' + i++, pattern: p, input: s, opts: o }); return out; }

function G6() { // PR55 follow-up witnesses: classes+stars with a trailing/leading literal inside extglob
  const bodies = ['[ab/]*a', '[ab/]a*', '*[ab/]a', 'a[ab/]*', '[ab/]*[ab/]', '[ab]*a', '*a[ab/]', 'a*[ab/]b'];
  const pats = bodies.flatMap(b => [`+(${b})`, `*(${b})`, `@(${b})`, `?(${b})`]);
  const I = gen(['a', 'b', '/'], 6); const out = []; let i = 0;
  for (const p of pats) for (const o of [{}, { dot: true }, { windows: true }, { capture: true }]) for (const s of I) out.push({ id: 'G6:' + i++, pattern: p, input: s, opts: o }); return out; }

function G5() { // families actually listed in picomatch docs, mapped to application relevance
  const P = ['*', '**', '?', 'a/*', 'a/**', '**/a', '**/*.js', '*.{js,ts}', 'a{b,c}d', 'a{1..3}', '{a,b}/{c,d}', '!a', '!(a|b)', '@(a|b)', '?(a|b)', '*(a|b)', '+(a|b)', '+(a|b)c', '@(a|b)*', '*(a|b)*', '[abc]', '[!abc]', '[^abc]', '[a-c]', '[[:alpha:]]', '[[:digit:]]*', '\\*', 'a\\/b', 'a\\*b', '\\!a', '(a|b)', 'a/(b|c)/d', '**/*.{test,spec}.?(c|m)[jt]s?(x)', 'src/**/*.ts', '!**/node_modules/**', './a', 'a/./b', '*/', '**/'];
  const I = ['', 'a', 'b', 'ab', 'ac', 'abd', 'acd', 'a1d', 'a2d', 'a/b', 'a/b/c', 'a/c/d', 'b/c', 'b/d', 'c/d', '.a', 'a/.b', '.a/b', 'a.js', 'a.ts', 'a/b.js', 'x/y/a', 'x/a.test.ts', 'x/a.spec.mjsx', 'src/a/b.ts', 'src/a.ts', 'node_modules/a', 'a/node_modules/b', '*', 'a*b', 'a/b/', '!a', 'A', 'AB', '1', 'z9', './a', 'a/./b', 'a\\b', '(a|b)', 'a\nb'];
  const O = [{}, { dot: true }, { nocase: true }, { windows: true }, { bash: true }, { noext: true }, { nobrace: true }, { posix: true }, { strictBrackets: false }];
  const out = []; let i = 0; for (const p of P) for (const o of O) for (const s of I) out.push({ id: 'G5:' + i++, pattern: p, input: s, opts: o }); return out; }

function G7() { // for the independent reference oracle: patterns in the supported mini-grammar, alphabet {a,b,/}
  const atoms = ['a', '*', '?', '[ab/]', '[^a]', '[/]'];
  const pats = new Set();
  for (const x of atoms) for (const y of atoms) { pats.add(x + y); for (const q of ['+', '*', '@', '?']) pats.add(`${q}(${x}${y})`); }
  for (const x of atoms) for (const y of atoms) for (const z of atoms) { for (const q of ['+', '*']) pats.add(`${q}(${x}${y}${z})`); pats.add(`+(${x}${y})${z}`); pats.add(`${z}+(${x}${y})`); }
  for (const x of atoms) for (const y of atoms) pats.add(`+(${x}|${y})`);
  const I = gen(['a', 'b', '/'], 6); const out = []; let i = 0;
  for (const p of pats) for (const s of I) out.push({ id: 'G7:' + i++, pattern: p, input: s, opts: {} }); return out; }

// ---- independent reference matcher (polynomial: position-set semantics, no regex) ----
function parseMini(p) { let i = 0;
  function seq(stop) { const items = []; while (i < p.length && !stop.includes(p[i])) {
      const c = p[i];
      if ('+*@?'.includes(c) && p[i + 1] === '(') { i += 2; const alts = [seq('|)')]; while (p[i] === '|') { i++; alts.push(seq('|)')); } i++; items.push({ t: 'ext', k: c, alts }); }
      else if (c === '[') { const j = p.indexOf(']', i); let body = p.slice(i + 1, j); let neg = false; if (body[0] === '^' || body[0] === '!') { neg = true; body = body.slice(1); } items.push({ t: 'cls', set: new Set(body), neg }); i = j + 1; }
      else if (c === '*') { items.push({ t: 'star' }); i++; } else if (c === '?') { items.push({ t: 'any' }); i++; } else { items.push({ t: 'lit', c }); i++; } }
    return items; }
  return seq(''); }
function refMatch(pattern, s) { const ast = parseMini(pattern);
  const runSeq = (items, starts) => { let cur = starts; for (const it of items) { const nxt = new Set(); for (const pos of cur) for (const e of step(it, pos)) nxt.add(e); cur = nxt; if (!cur.size) break; } return cur; };
  const step = (it, pos) => { const r = [];
    if (it.t === 'lit') { if (s[pos] === it.c) r.push(pos + 1); }
    else if (it.t === 'any') { if (pos < s.length && s[pos] !== '/') r.push(pos + 1); }
    else if (it.t === 'cls') { if (pos < s.length && (it.set.has(s[pos]) !== it.neg)) r.push(pos + 1); }
    else if (it.t === 'star') { r.push(pos); for (let q = pos; q < s.length && s[q] !== '/'; q++) r.push(q + 1); }
    else { const once = from => { const out = new Set(); for (const a of it.alts) for (const e of runSeq(a, new Set([from]))) out.add(e); return out; };
      if (it.k === '@') return [...once(pos)]; if (it.k === '?') return [pos, ...once(pos)];
      const seen = new Set(), res = new Set(it.k === '*' ? [pos] : []); let frontier = new Set([pos]);
      while (frontier.size) { const nf = new Set(); for (const f of frontier) for (const e of once(f)) { if (!res.has(e) || !seen.has(e)) { res.add(e); } if (!seen.has(e)) { seen.add(e); nf.add(e); } } frontier = nf; }
      return [...res]; }
    return r; };
  return runSeq(ast, new Set([0])).has(s.length); }

module.exports = { G1, G1dot, G2, G3, G4, G5, G6, G7, refMatch, gen };
