const test=require('node:test');
const assert=require('node:assert/strict');
const {cardHint}=require('../static/js/card-hint.js');
function hint(){const h=cardHint();h.$nextTick=fn=>fn();h.$root={};h.$watch=(key,fn)=>{assert.equal(key,'revealed');h.onFlip=fn;};h.init();return h;}
test('hints begin hidden and toggle in either direction',()=>{const h=hint();assert.equal(h.shown,false);h.toggle();assert.equal(h.shown,true);h.toggle();assert.equal(h.shown,false);});
test('every flip conceals the hint without persisting state',()=>{const h=hint();h.toggle();h.onFlip(true);assert.equal(h.shown,false);h.toggle();h.onFlip(false);assert.equal(h.shown,false);});
