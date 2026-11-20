// node redos_driver.cjs <outfile> variants... ; bounded: 3s wall per child, 1.5GB address-space cap via ulimit in spawn shell
const { spawn } = require('child_process'); const fs = require('fs'); const path = require('path');
const V = process.argv.slice(3); const base = path.resolve(__dirname, '../v');
const P = process.env.PATS ? JSON.parse(require('fs').readFileSync(process.env.PATS)) : ['+(*a)', '*(*a)', '+(a*)', '+(a*b)', '*(a*b)c', '+(*)a', '+(*a*)', '+(?*)', '+([ab/]*)!', '*([ab/]*)!', '+(*[ab/])!', '+([^a]*)!', '+(a|aa)', '*(a|a)', '+(a|a)!', '+(+(a))', '*(*(a)*)', '+(+(*a))', '@(+(*a))', '+(*a|b)', '+(*a|*b)', '!(+(*a))', 'x+(*a)y', '*a*a*a*a*a*a*a*a*b', '**/**/**/**/**/**/**/**/b', '+(*/a)', '+(**)a', '+(*.*)b', '+({a,b}*)c', '+([[:alpha:]]*)1'];
const F = ['a', 'slash', 'ab']; const jobs = []; for (const v of V) for (const p of P) for (const f of F) jobs.push({ v, p, f });
const res = []; let idx = 0, active = 0; const MAX = 4;
function next() { if (idx >= jobs.length) { if (!active) { fs.writeFileSync(process.argv[2], JSON.stringify(res)); console.log('done', res.length); } return; }
  const j = jobs[idx++]; active++;
  const c = spawn('bash', ['-c', `ulimit -v 2500000; exec node ${__dirname}/redos_child.cjs "${base}/${j.v}" "$1" ${j.f}`, 'x', j.p], { stdio: ['ignore', 'pipe', 'pipe'] });
  let out = ''; c.stdout.on('data', d => out += d); c.stderr.on('data', d => out += 'ERR ' + d);
  const timer = setTimeout(() => c.kill('SIGKILL'), 3000); const t0 = Date.now();
  c.on('close', code => { clearTimeout(timer); const lines = out.trim().split('\n'); const timed = Date.now() - t0 >= 2990 && code !== 0;
    const pts = lines.filter(l => /^\d+ /.test(l)).map(l => l.split(' ').map(Number)); const last = pts[pts.length - 1];
    res.push({ ...j, timedOut: timed, code, completedN: last ? last[0] : 0, lastMs: last ? last[1] : null, maxMs: pts.length ? Math.max(...pts.map(p => p[1])) : null, compile: (lines[0] || '').slice(0, 50), wall: Date.now() - t0 }); active--; next(); });
}
for (let i = 0; i < MAX; i++) next();
