const test = require('node:test');
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');
const {createDemoStore} = require('../app/static/demo-store.js');
function setup(storage=new Map()) {
 const store=createDemoStore({getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),uuid:randomUUID});
 const snapshot=()=>store.request('/api/snapshot');
 const write=(path,body={},method='POST',key=randomUUID())=>store.request(path,method,body,key);
 const move=(kind='fbs',quantity=3,source_id=1,destination_id)=>write('/api/movements',{kind,quantity,source_id,product_id:1,...(destination_id?{destination_id}:{})});
 const balance=async(w=1)=>(await snapshot()).stocks.find(b=>b.product_id===1&&b.warehouse_id===w);
 return {store,snapshot,write,move,balance,storage};
}
test('seed and persistence across instances',async()=>{
 const a=setup();assert.equal((await a.snapshot()).stocks.reduce((n,b)=>n+b.physical,0),25);
 await a.write('/api/receipts',{product_id:1,warehouse_id:1,quantity:5});assert.equal((await setup(a.storage).balance()).physical,15);
});
test('FBS reserve, cancel, send, deliver and safe repetitions',async()=>{
 const a=setup();let m=await a.move();assert.equal((await a.balance()).available,7);
 await a.write(`/api/movements/${m.id}/cancel`);assert.equal((await a.balance()).available,10);
 m=await a.move();await a.write(`/api/movements/${m.id}/send`);await a.write(`/api/movements/${m.id}/send`);
 assert.equal((await a.balance()).physical,7);assert.equal((await a.balance()).reserved,0);
 await a.write(`/api/movements/${m.id}/receive`);await a.write(`/api/movements/${m.id}/receive`);assert.equal((await a.snapshot()).movements[0].status,'completed');
});
test('transfer receipt adds destination stock once',async()=>{
 const a=setup();const m=await a.move('transfer',4,1,2);assert.equal((await a.balance()).physical,6);assert.equal((await a.balance(2)).physical,6);
 await a.write(`/api/movements/${m.id}/receive`);await a.write(`/api/movements/${m.id}/receive`);assert.equal((await a.balance(2)).physical,10);
});
test('FBO completion does not return stock to FF',async()=>{
 const a=setup();const m=await a.move('fbo',4);await a.write(`/api/movements/${m.id}/receive`);assert.equal((await a.balance()).physical,6);
});
test('local shortage and reserve protection leave failed operations unchanged',async()=>{
 const a=setup();const before=JSON.stringify(await a.snapshot());await assert.rejects(a.move('fbo',12),/доступно 10/);assert.equal(JSON.stringify(await a.snapshot()),before);
 await a.move('fbs',8);await assert.rejects(a.move('transfer',3,1,2),/доступно 2/);
});
test('archive retains stock and old obligations; evacuation allowed',async()=>{
 const a=setup();const m=await a.move();await a.write('/api/warehouses/1',{},'DELETE');assert.equal((await a.balance()).physical,10);
 await a.write(`/api/movements/${m.id}/send`);await assert.rejects(a.move('fbs',1),/Склад удалён/);
 const t=await a.move('transfer',7,1,2);await a.write(`/api/movements/${t.id}/receive`);assert.equal((await a.balance()).physical,0);
});
test('in-flight transfer can arrive into archived destination',async()=>{
 const a=setup();const m=await a.move('transfer',4,1,2);await a.write('/api/warehouses/2',{},'DELETE');await a.write(`/api/movements/${m.id}/receive`);
 assert.equal((await a.balance(2)).physical,10);await assert.rejects(a.move('transfer',1,1,2),/Склад удалён/);
});
test('idempotency and serialized concurrent reservations',async()=>{
 const a=setup();const key=randomUUID(),body={product_id:1,warehouse_id:1,quantity:5};await Promise.all(Array.from({length:4},()=>a.write('/api/receipts',body,'POST',key)));
 assert.equal((await a.balance()).physical,15);await assert.rejects(a.write('/api/receipts',{...body,quantity:6},'POST',key),/ключ/);
 const b=setup();const results=await Promise.allSettled([b.move('fbs',7),b.move('fbs',7)]);assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal((await b.balance()).reserved,7);
});
test('names validated; history labels frozen',async()=>{
 const a=setup();await a.snapshot();await a.write('/api/warehouses/1',{name:'Северный'},'PATCH');assert.ok((await a.snapshot()).events.some(e=>e.action==='receipt'&&e.destination_label==='Север'));
 await assert.rejects(a.write('/api/warehouses',{name:'Северный'}),/уже существует/);await assert.rejects(a.write('/api/warehouses',{name:'   '}),/название/);
});
test('invalid quantities and state transitions rejected',async()=>{
 const a=setup();for(const q of [0,-1,1.5,'3',true,1000001])await assert.rejects(a.move('fbs',q),/целыми/);
 const m=await a.move();await assert.rejects(a.write(`/api/movements/${m.id}/receive`),/недоступно/);assert.equal((await a.balance()).reserved,3);
});
test('reset, corrupt persistence and quota errors',async()=>{
 const a=setup();await a.move();await a.store.reset();assert.equal((await a.balance()).available,10);assert.equal((await a.snapshot()).movements.length,0);
 const bad=createDemoStore({getItem:()=>'{broken',setItem:()=>{},uuid:randomUUID});await assert.rejects(bad.request('/api/snapshot'),/повреждены/);
 const blocked=createDemoStore({getItem:()=>null,setItem:()=>{throw Error('quota');},uuid:randomUUID});await assert.rejects(blocked.request('/api/snapshot'),/сохранить/);
});
