const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const script = fs.readFileSync('static/js/diagrams.js', 'utf8').replace('import(moduleUrl)', 'loadModule(moduleUrl)');
function setup(importer) {
  const nodes = [];
  const document = {currentScript:{dataset:{mermaidModule:'/local/mermaid.mjs'}}, documentElement:{}, addEventListener(){}, querySelectorAll(){return nodes;}};
  const window = {};
  vm.runInNewContext(script, {document, window, loadModule:importer, MutationObserver:class {observe(){}}, URL, Blob});
  const node = (visible=true) => {
    const status={textContent:'Loading'};
    const n={dataset:{mermaid:'pending'}, isConnected:true, addEventListener(){}, getClientRects(){return visible ? [{}] : [];}, querySelector(s){return s==='code' ? {textContent:'flowchart TD\nA --> B'} : status;}, status};
    nodes.push(n); return n;
  };
  return {scan:window.flashcramRenderDiagrams, node};
}
const settle = () => new Promise(resolve=>setImmediate(resolve));
test('ordinary and hidden content do not load Mermaid; load failure is isolated and not retried', async()=>{
  let loads=0;
  const {scan,node}=setup(async()=>{loads++;throw new Error('offline');});
  scan(); node(false); scan(); assert.equal(loads,0);
  const first=node(), second=node(); scan(); await settle();
  assert.equal(loads,1);
  assert.equal(first.dataset.mermaid,'error'); assert.equal(second.dataset.mermaid,'error');
  assert.match(first.status.textContent,/Could not render/);
  scan(); await settle(); assert.equal(loads,1);
});
test('malformed syntax fails once without preventing another diagram attempt',async()=>{
  let renders=0, config;
  const {scan,node}=setup(async()=>({default:{initialize(c){config=c;},async render(){renders++;throw new Error('syntax');}}}));
  const a=node(), b=node(); scan(); await settle();
  assert.equal(renders,2); assert.equal(config.securityLevel,'strict'); assert.equal(config.maxEdges,100);
  assert.equal(a.dataset.mermaid,'error');assert.equal(b.dataset.mermaid,'error');scan();await settle();assert.equal(renders,2);
});
