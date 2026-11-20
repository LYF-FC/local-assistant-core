const pm=require(require('path').resolve(process.argv[2]));
const pats=['**/*.{test,spec}.?(c|m)[jt]s?(x)','**/node_modules/**','**/.git/**','**/*.{bench,benchmark}.?(c|m)[jt]s?(x)','**/{vitest,vite}.config.*','src/**/*.ts','+(*a)','+([ab/]*)','*(a|b)*c','!(*.ts)'];
const dirs=['src','src/components','src/lib/util','node_modules/react/cjs','node_modules/.vite/deps','.git/objects','e2e','test-harness'];
const files=[];for(let i=0;i<1500;i++)files.push(`${dirs[i%dirs.length]}/f${i}${['.ts','.tsx','.test.ts','.spec.mjs','.css','.json','.test.tsx','.js'][i%8]}`);
const run=()=>{let hits=0;for(const p of pats){const m=pm(p,{dot:true});for(const f of files)if(m(f))hits++;}return hits};
const rssBefore=process.memoryUsage().rss;
for(let i=0;i<5;i++)run(); // warm-up
const ts=[];let h;for(let i=0;i<30;i++){const t=process.hrtime.bigint();h=run();ts.push(Number(process.hrtime.bigint()-t)/1e6)}
ts.sort((a,b)=>a-b);const q=x=>ts[Math.min(ts.length-1,Math.floor(x*ts.length))];
console.log(JSON.stringify({hits:h,min:q(0),median:q(.5),p95:q(.95),max:ts[ts.length-1],rssMB:+(process.memoryUsage().rss/1e6).toFixed(1),heapMB:+(process.memoryUsage().heapUsed/1e6).toFixed(1)}));
