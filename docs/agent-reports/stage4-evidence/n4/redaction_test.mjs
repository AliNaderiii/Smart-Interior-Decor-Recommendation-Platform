process.env.LH_ACCESS_TOKEN='eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhYmMxMjMifQ.Qwsk-AbCdEfGhIjKlMnOpQrStUvWxYz012345';
process.env.LH_REFRESH_TOKEN='refresh_tok_AAAABBBBCCCCDDDDEEEE1111';
process.env.LH_CSRF_TOKEN='csrf_ZZZZYYYYXXXX9999';
const src=await import('fs').then(fs=>fs.readFileSync('frontend/scripts/lighthouse-auth-matrix.mjs','utf8'));
const start=src.indexOf('const SESSION_SECRETS');
const end=src.indexOf('for (const p of PAGES)');
const mod=src.slice(start,end);
const fn=new Function('process',mod+'; return redactSecrets;')(process);

const A=process.env.LH_ACCESS_TOKEN, R=process.env.LH_REFRESH_TOKEN, C=process.env.LH_CSRF_TOKEN;
const report=JSON.stringify({audits:{lcp:{numericValue:2112}},network:[
 {header:`Cookie: access_token=${A}; refresh_token=${R}; csrf_token=${C}`},
 {url:`https://x/api?t=${encodeURIComponent(A)}`}]});
const out=fn(report);
const checks=[
 ['access token gone', !out.includes(A)],
 ['refresh token gone', !out.includes(R)],
 ['csrf token gone', !out.includes(C)],
 ['url-encoded copy gone', !out.includes(encodeURIComponent(A))],
 ['placeholder present', out.includes('[REDACTED-SESSION-TOKEN]')],
 ['perf number preserved', JSON.parse(out).audits.lcp.numericValue===2112],
 ['still valid JSON', (()=>{try{JSON.parse(out);return true}catch{return false}})()],
];
// the sk- pattern that was firing
const PAT=/(BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35})/;
checks.push(['sk- pattern matched BEFORE redaction', PAT.test(report)]);
checks.push(['sk- pattern clean AFTER redaction', !PAT.test(out)]);
let fail=0;
for(const [n,ok] of checks){ console.log((ok?'PASS':'FAIL')+'  '+n); if(!ok)fail++; }
console.log(fail? `\nRESULT: FAIL (${fail})` : '\nRESULT: PASS');
process.exit(fail?1:0);
