const C=require('../h/corpus.cjs'),fs=require('fs');const R=JSON.parse(fs.readFileSync('../res/stock.json'));
(async()=>{const mm=require('minimatch');const zm=(await import('zeptomatch')).default;
const eng={minimatch:(s,p,o)=>mm.minimatch(s,p,{dot:!!o.dot,nocase:!!o.nocase}), zeptomatch:(s,p,o)=>zm(p,s)};
for(const [name,f] of Object.entries(eng)){ const rows=[];
 for(const g of ['G1','G1dot','G4','G2','G3','G5','G6']){ const ok=c=>{const o=c.opts; return Object.keys(o).every(k=>['dot','nocase'].includes(k)) && (name==='minimatch'||!o.dot&&!o.nocase)}; const cs=null; let n=0,mis=0,rej=0,acc=0,thr=0,hand=0;
  const all=C[g](); all.forEach((c,i)=>{ if(!ok(c)) return; n++; let r; try{r=f(c.input,c.pattern,c.opts)}catch{thr++;return} const s=R[g].bits[i]==='1'; if(r!==s){mis++; r?acc++:rej++} if(c.expected!==undefined&&r!==c.expected)hand++; });
  rows.push({g,total:n,mismatchVsStock:mis,rejectsValid:rej,acceptsInvalid:acc,thrown:thr,vsHandExpected:hand}); }
 console.log(name); console.table(rows); } })();
