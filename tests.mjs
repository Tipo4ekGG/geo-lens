import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';
const source=await fs.readFile('dist/worker.js','utf8');const {default:worker}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const env={PHOTO_API_KEY:'fake-provider-key',ACCESS_TOKEN:'fake-access-code',PHOTO_API_ORIGIN:'https://provider.example',ALLOWED_ORIGIN:'https://tipo4ekgg.github.io'};
function req(data={},headers={}){return new Request('https://worker.example/api/models',{method:'POST',headers:{origin:env.ALLOWED_ORIGIN,'content-type':'application/json',authorization:'Bearer '+env.ACCESS_TOKEN,...headers},body:JSON.stringify({apiPath:'/v1',...data})})}
test('Pages output is complete and has no private keys',async()=>{const s=await fs.readFile('public/index.html','utf8');assert.match(s,/Досье фотографии/);assert.match(s,/backendUrl/);assert.doesNotMatch(s,/sk-fc-|fake-provider-key/)});
test('rejects foreign origin',async()=>assert.equal((await worker.fetch(req({}, {origin:'https://foreign.example'}),env)).status,403));
test('rejects missing access code',async()=>assert.equal((await worker.fetch(req({}, {authorization:''}),env)).status,401));
test('rejects wrong access code',async()=>assert.equal((await worker.fetch(req({}, {authorization:'Bearer wrong'}),env)).status,401));
test('preflight exposes only configured Pages origin',async()=>{const r=await worker.fetch(new Request('https://worker.example/api/models',{method:'OPTIONS',headers:{origin:env.ALLOWED_ORIGIN}}),env);assert.equal(r.status,204);assert.equal(r.headers.get('Access-Control-Allow-Origin'),env.ALLOWED_ORIGIN)});
test('forwards provider key server-side and returns models',async()=>{const original=globalThis.fetch;globalThis.fetch=async(url,init)=>{assert.equal(url,'https://provider.example/v1/models');assert.equal(init.headers.Authorization,'Bearer '+env.PHOTO_API_KEY);assert.equal(init.redirect,'manual');return Response.json({data:[{id:'vision-model'}]})};try{const r=await worker.fetch(req(),env);assert.equal(r.status,200);assert.deepEqual(await r.json(),{models:['vision-model']});assert.equal(r.headers.get('Access-Control-Allow-Origin'),env.ALLOWED_ORIGIN)}finally{globalThis.fetch=original}});
test('rejects malicious upstream path',async()=>{const r=await worker.fetch(req({apiPath:'//foreign.example'}),env);assert.equal(r.status,400)});

for (const status of [301,302,303,307,308]) {
  test('rejects upstream redirect '+status+' without forwarding credentials',async()=>{
    const original=globalThis.fetch;let calls=0;let cancelled=false;
    globalThis.fetch=async(url,init)=>{
      calls++;assert.equal(url,'https://provider.example/v1/models');assert.equal(init.redirect,'manual');
      return new Response(new ReadableStream({cancel(){cancelled=true}}),{status,headers:{Location:'https://other.example/v1/models'}});
    };
    try{const response=await worker.fetch(req(),env);assert.equal(response.status,400);const data=await response.json();assert.match(data.error,/перенаправление/);assert.match(data.error,new RegExp(String(status)));assert.doesNotMatch(data.error,/fake-provider-key|other.example/);assert.equal(calls,1);assert.equal(cancelled,true);}finally{globalThis.fetch=original}
  });
}
test('manual redirects also apply to image analysis requests',async()=>{
  const original=globalThis.fetch;let calls=0;
  globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'https://provider.example/v1/chat/completions');assert.equal(init.method,'POST');assert.equal(init.redirect,'manual');return new Response(null,{status:307,headers:{Location:'https://other.example'}})};
  try{const request=new Request('https://worker.example/api/analyze',{method:'POST',headers:{origin:env.ALLOWED_ORIGIN,'content-type':'application/json',authorization:'Bearer '+env.ACCESS_TOKEN},body:JSON.stringify({apiPath:'/v1',model:'vision',image:'data:image/jpeg;base64,YWJj'})});const response=await worker.fetch(request,env);assert.match((await response.json()).error,/перенаправление/);assert.equal(calls,1);}finally{globalThis.fetch=original}
});
