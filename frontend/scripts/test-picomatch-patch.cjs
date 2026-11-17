'use strict';
// Test the installed package, not a detached copy of the proposed fix.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');

const frontend = path.resolve(__dirname, '..');
const entry = require.resolve('picomatch');
const installed = path.dirname(entry);
const matcher = require(entry);
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
const source = fs.readFileSync(path.join(installed, 'lib/parse.js'), 'utf8');
assert.equal(digest(source), '6924cea42aff5a624d01f67991a5db661d9ca0678adc08453c2f2fcb053b8d38');
assert.equal(require(path.join(installed, 'package.json')).version, '4.0.7');
assert.equal(digest(fs.readFileSync(path.join(frontend, 'vendor/picomatch/picomatch-4.0.7-upstream-254.tgz'))),
  '30d3e22fdd64db323b10836c2e792ca1eb4febb4d2cd618f479155a9fa779543');

// All installed consumers must resolve the same reviewed bytes.
for (const consumer of ['vite', 'vitest', 'tinyglobby', 'fdir']) {
  const resolve = createRequire(path.join(frontend, 'node_modules', consumer, 'package.json'));
  assert.equal(resolve.resolve('picomatch'), entry, consumer);
}

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'butler-picomatch-control-'));
try {
  fs.cpSync(installed, temporary, { recursive: true });
  const start = source.indexOf('    // A single wildcard branch is closed under concatenation:');
  const end = source.indexOf('    let rest;', start);
  assert(start !== -1 && end > start);
  const original = source.slice(0, start) +
    "    let output = token.close + (opts.capture ? ')' : '');\n" + source.slice(end);
  assert.equal(digest(original), '4e1e05447668aa1e94366c5516a2bcd8f5fff800cc92b1d0cd7d77703b8618c4');
  fs.writeFileSync(path.join(temporary, 'lib/parse.js'), original);
  const baseline = require(path.join(temporary, 'index.js'));

  // Prove the new assertions detect the previous upstream-only candidate.
  const localStart = source.indexOf('    // Local compatibility correction:');
  assert(localStart > start && end > localStart);
  const upstreamSource = source.slice(0, localStart) + source.slice(end);
  assert.equal(digest(upstreamSource), 'ccbcc9bb1333c4e03324fef8c729ea20979ef4f7b99d8f75c941abfec04b1cfd');
  const upstreamDirectory = path.join(temporary, 'upstream-control');
  fs.cpSync(installed, upstreamDirectory, { recursive: true });
  fs.writeFileSync(path.join(upstreamDirectory, 'lib/parse.js'), upstreamSource);
  const upstream = require(path.join(upstreamDirectory, 'index.js'));
  for (const option of [{}, { dot: true }, { windows: true }, { capture: true }]) {
    for (const input of ['a/b', 'a/b/a', 'aba/', '//']) {
      assert.equal(baseline.isMatch(input, '+([ab/]*)', option), true);
      assert.equal(upstream.isMatch(input, '+([ab/]*)', option), false);
      assert.equal(matcher.isMatch(input, '+([ab/]*)', option), true);
    }
  }

  // The original defect must time out in a killable process; never run it on the test thread.
  for (const pattern of ['+(*a)', '+([ab/]*)!']) {
    const attack = "const p=require(process.argv[1]);p.isMatch('a'.repeat(40)+'?', process.argv[2]);";
    const control = spawnSync(process.execPath, ['-e', attack, temporary, pattern], { timeout: 2000 });
    assert.equal(control.error && control.error.code, 'ETIMEDOUT', 'unpatched sensitivity control: ' + pattern);
  }
  const hardened = spawnSync(process.execPath, ['-e',
    "const p=require(process.argv[1]);for(const pattern of ['+(*)a','+(*a)','*(a*)b','+(a*b)c'])" +
    "p.isMatch('a'.repeat(10000)+'!',pattern);", installed], { timeout: 2000 });
  assert.ifError(hardened.error);
  assert.equal(hardened.status, 0, hardened.stderr.toString());

  // Restoring the old nested quantifier would preserve matches but reintroduce ReDoS.
  // Include literal-bracket words, both star positions, plus/star extglobs and failures.
  const compatibilityAttack = spawnSync(process.execPath, ['-e',
    "const assert=require('node:assert/strict'),p=require(process.argv[1]);" +
    "for(const o of [{},{windows:true},{capture:true},{bash:true},{literalBrackets:true},{literalBrackets:false}])" +
    "for(const pat of ['+([ab/]*)!','*([ab/]*)!','+(*[ab/])!','*(*[ab/])!','+([^a]*)!','+(*[^a])!'])" +
    "for(const s of ['a'.repeat(10000)+'?','[ab/]'.repeat(2000)+'?','a/'.repeat(5000)+'?'])" +
    "assert.equal(p.isMatch(s,pat,o),false);", installed], { timeout: 2000 });
  assert.ifError(compatibilityAttack.error);
  assert.equal(compatibilityAttack.status, 0, compatibilityAttack.stderr.toString());

  // Short-input differential checks are safe even for the original backtracking expressions.
  const inputs = [''];
  let level = [''];
  for (let length = 1; length <= 4; length++) {
    level = level.flatMap(prefix => ['a', 'b', '.', '/'].map(char => prefix + char));
    inputs.push(...level);
  }
  const patterns = ['+(*)', '+(*a)', '*(*a)', '+(a*)', '+(a*b)', '*(a*b)c',
    '+(a*b*c)', 'x+(*a)y', '+(a?)', '+([ab]*)', '+(\\*a)', '+(foo|bar)',
    '**/*.ts', '**.ts', '[!a]', 'a/**/b', '*(*.js)', '!(*.ts)'];
  const options = [{}, { dot: true }, { bash: true }, { windows: true },
    { nocase: true }, { capture: true }, { maxExtglobRecursion: false }];
  let comparisons = 0;
  for (const pattern of patterns) for (const option of options) for (const input of inputs) {
    assert.equal(matcher.isMatch(input, pattern, option), baseline.isMatch(input, pattern, option),
      JSON.stringify({ pattern, input, option }));
    comparisons++;
  }
  // Upstream explicitly documents this affected capture detail; boolean matching is preserved.
  assert.deepEqual(matcher.makeRe('+(*a)', { capture: true }).exec('aba').slice(1), ['aba', 'ab']);
  assert(matcher.makeRe('+(*a)', { maxExtglobRecursion: false }).source.includes(')+'));
  // Brackets can admit slash, Windows separators or (with bash stars) line endings.
  // The default bracket also accepts its literal multi-character spelling.
  const classes = ['[ab/]', '[ab]', '[^a]', '[^/]', '[a/]', '[a\\\\]', '[!/]', '[/]', '[a\n]'];
  const bracketPatterns = classes.flatMap(c =>
    [`+(${c}*)`, `*(${c}*)`, `+(*${c})`, `*(*${c})`, `x+(${c}*)y`, `+(${c}*)!`]);
  const bracketOptions = [{}, { dot: true }, { windows: true }, { capture: true },
    { bash: true }, { literalBrackets: true }, { literalBrackets: false },
    { windows: true, capture: true }, { bash: true, capture: true }, { nocase: true },
    { bash: true, flags: 's' }, { bash: true, capture: true, flags: 's' }];
  const bracketInputs = ['', 'a/b', 'a/b/a', 'aba/', '//', '[ab/]a', '[ab/][ab/]',
    '[/]', '[^/]', 'a\\b', 'a\nb', 'a\rb', 'a\u2028b', 'a\u2029b'];
  level = [''];
  for (let length = 1; length <= 3; length++) {
    level = level.flatMap(prefix => ['a', 'b', '/', '\\', '\n', '[', ']'].map(c => prefix + c));
    bracketInputs.push(...level);
  }
  for (const c of classes) bracketInputs.push(c, c + c, 'a' + c + c, c + 'a/b', c + '\n', c + 'a' + c);
  let bracketComparisons = 0;
  for (const pattern of bracketPatterns) for (const option of bracketOptions) for (const input of bracketInputs) {
    assert.equal(matcher.isMatch(input, pattern, option), baseline.isMatch(input, pattern, option),
      JSON.stringify({ pattern, input, option }));
    bracketComparisons++;
  }
  console.log('picomatch patch: pinned bytes, all consumers, vulnerable control, isolated deadline, ' +
    comparisons + ' existing and ' + bracketComparisons + ' bracket matching comparisons passed; ' +
    '16 prior-candidate counterexamples detected; bracket attack deadline passed; capture limit retained');
} finally {
  fs.rmSync(temporary, { recursive: true, force: true });
}
