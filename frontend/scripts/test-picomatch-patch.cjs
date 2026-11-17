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
assert.equal(digest(source), 'ccbcc9bb1333c4e03324fef8c729ea20979ef4f7b99d8f75c941abfec04b1cfd');
assert.equal(require(path.join(installed, 'package.json')).version, '4.0.7');
assert.equal(digest(fs.readFileSync(path.join(frontend, 'vendor/picomatch/picomatch-4.0.7-upstream-254.tgz'))),
  'e0c1084e3580fab3440d420fbdf79ada687e74e01aa63a7076d61fdaed98843c');

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

  // The original defect must time out in a killable process; never run it on the test thread.
  const attack = "const p=require(process.argv[1]);p.isMatch('a'.repeat(40)+'!', '+(*a)');";
  const control = spawnSync(process.execPath, ['-e', attack, temporary], { timeout: 2000 });
  assert.equal(control.error && control.error.code, 'ETIMEDOUT', 'unpatched sensitivity control');
  const hardened = spawnSync(process.execPath, ['-e',
    "const p=require(process.argv[1]);for(const pattern of ['+(*)a','+(*a)','*(a*)b','+(a*b)c'])" +
    "p.isMatch('a'.repeat(10000)+'!',pattern);", installed], { timeout: 2000 });
  assert.ifError(hardened.error);
  assert.equal(hardened.status, 0, hardened.stderr.toString());

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
  // Known upstream compatibility regression, NOT a claim of preserved semantics.
  // Keep this counterexample visible for independent review of the temporary candidate.
  assert.equal(baseline.isMatch('a/b', '+([ab/]*)'), true);
  assert.equal(matcher.isMatch('a/b', '+([ab/]*)'), false);
  console.log('picomatch patch: pinned bytes, all consumers, vulnerable control, isolated deadline, ' +
    comparisons + ' matching comparisons passed; capture and slash-class differences recorded');
} finally {
  fs.rmSync(temporary, { recursive: true, force: true });
}
