const test=require('node:test');const assert=require('node:assert/strict');
const {promptCustomizer}=require('../static/js/prompt-customizer.js');
test('reset affects only draft and cancel discards it',()=>{
 const c=promptCustomizer();c.saved={emphasis:'moderate'};c.defaults={emphasis:'light'};c.reset();assert.equal(c.draft.emphasis,'light');assert.equal(c.saved.emphasis,'moderate');let closed=false;c.close=()=>{closed=true;};c.cancel();assert.deepEqual(c.draft,c.saved);assert.equal(closed,true);
});
test('pending save prevents cancellation',()=>{const c=promptCustomizer();c.busy=true;c.close=()=>{throw Error('closed during save');};c.cancel();});
test('copy reports clipboard unavailability and preserves displayed content',async()=>{
 const c=promptCustomizer();c.$root={querySelector:()=>({textContent:'Exact prompt\ncontent'})};await c.copy();assert.match(c.copyMessage,/Could not copy/);
});
test('copy sends the exact displayed prompt to clipboard',async()=>{
 const original=Object.getOwnPropertyDescriptor(global,'navigator');let copied;
 Object.defineProperty(global,'navigator',{configurable:true,value:{clipboard:{writeText:async text=>{copied=text;}}}});
 try {const c=promptCustomizer();c.$root={querySelector:()=>({textContent:'  Exact\nprompt  '})};await c.copy();assert.equal(copied,'  Exact\nprompt  ');assert.equal(c.copyMessage,'Copied');clearTimeout(c.timer);} finally {if(original) Object.defineProperty(global,'navigator',original);else delete global.navigator;}
});
test('failed saves retain draft and show recovery feedback',()=>{const c=promptCustomizer();c.draft={guidance:'Keep my draft'};c.busy=true;c.$refs={status:{textContent:''}};c.afterRequest({detail:{successful:false,xhr:{status:500}}});assert.equal(c.busy,false);assert.equal(c.draft.guidance,'Keep my draft');assert.match(c.$refs.status.textContent,/changes are still here/);});
