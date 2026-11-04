const test = require('node:test');
const assert = require('node:assert/strict');
const {largestSize} = require('../static/js/card-fit.js');
test('short content keeps its starting size', () => assert.equal(largestSize(24,16,()=>true),24));
test('search selects largest fitting reflow size within a quarter pixel',()=>{
  let measurements=0;
  const chosen=largestSize(24,16,size=>{measurements++;return size<=19.1;});
  assert.ok(chosen<=19.1 && chosen>18.85);assert.ok(measurements<=8);
});
test('oversized content retains the readable floor instead of reverting',()=>assert.equal(largestSize(24,16,()=>false),16));
test('desktop fitting never exceeds the conservative reduction',()=>assert.equal(largestSize(30,24,()=>false),24));
test('successive fits start fresh rather than progressively shrinking',()=>{
  assert.ok(largestSize(24,16,s=>s<=18)<19);
  assert.equal(largestSize(24,16,()=>true),24);
});
