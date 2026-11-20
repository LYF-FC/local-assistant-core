const pm=require(require('path').resolve(process.argv[2])); const pat=process.argv[3]; const opts=JSON.parse(process.argv[4]||'{}'); const n=+process.argv[5];
const t=process.hrtime.bigint(); const r=pm.isMatch('a'.repeat(n)+'?',pat,opts); console.log(r,(Number(process.hrtime.bigint()-t)/1e6).toFixed(1));
