/* Optional Mermaid rendering: source is untrusted; only generated image SVG is displayed. */
(() => {
  const moduleUrl = document.currentScript.dataset.mermaidModule;
  let library, serial = 0;
  const urls = new Map();
  function load() {
    return library ||= import(moduleUrl).then(({default: mermaid}) => {
      mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'dark',
        htmlLabels: false, flowchart: {htmlLabels: false}, maxTextSize: 10000, maxEdges: 100,
        suppressErrorRendering: true, deterministicIds: true,
        secure: ['secure', 'securityLevel', 'startOnLoad', 'maxTextSize', 'maxEdges', 'htmlLabels', 'theme', 'flowchart']});
      return mermaid;
    });
  }
  function imageSvg(svg) {
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
    if (doc.querySelector('parsererror') || doc.documentElement.localName !== 'svg') throw new Error('Invalid SVG');
    doc.querySelectorAll('script, foreignObject, image, a').forEach(el => el.remove());
    for (const el of doc.querySelectorAll('*')) for (const attr of [...el.attributes]) {
      if (/^on/i.test(attr.name) || (/href$/i.test(attr.name) && !attr.value.startsWith('#'))) el.removeAttribute(attr.name);
    }
    return new XMLSerializer().serializeToString(doc.documentElement);
  }
  function failure(node, message) {
    node.dataset.mermaid = 'error';
    node.querySelector('[role=status]').textContent = message;
  }
  async function render(node) {
    if (node.dataset.mermaid !== 'pending' || !node.getClientRects().length) return;
    node.dataset.mermaid = 'rendering';
    ['click', 'keydown'].forEach(type => node.addEventListener(type, event => event.stopPropagation()));
    const source = node.querySelector('code').textContent;
    try {
      const mermaid = await load();
      if (!node.isConnected) return;
      const {svg} = await mermaid.render(`fc-diagram-${++serial}`, source);
      if (!node.isConnected) return;
      const url = URL.createObjectURL(new Blob([imageSvg(svg)], {type: 'image/svg+xml'}));
      urls.set(node, url);
      const title = source.match(/^\s*accTitle\s*:\s*(.+)$/m)?.[1] || 'Card diagram';
      const description = source.match(/^\s*accDescr\s*:\s*(.+)$/m)?.[1];
      const image = document.createElement('img'); image.src = url; image.alt = description ? `${title}: ${description}` : title;
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'fc-diagram-open'; button.setAttribute('aria-label', `Enlarge ${title}`); button.append(image);
      const dialog = document.createElement('dialog'); dialog.className = 'fc-diagram-dialog'; dialog.setAttribute('aria-label', title);
      const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Close diagram'; close.className = 'btn btn-primary';
      close.addEventListener('click', () => dialog.close());
      const large = image.cloneNode(); dialog.append(close, large);
      dialog.addEventListener('close', () => button.focus({preventScroll:true}));
      button.addEventListener('click', () => dialog.showModal());
      // Keep source available for correction, never interpret it as HTML.
      const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Diagram source';
      details.append(summary, node.querySelector('pre')); node.querySelector('[role=status]').remove();
      node.append(button, details, dialog); node.dataset.mermaid = 'ready';
      window.flashcramRefitMath?.();
    } catch (_) { if (node.isConnected) failure(node, 'Could not render diagram. Check its source below.'); }
  }
  function scan(root = document) {
    if (root.matches?.('[data-mermaid=pending]')) render(root);
    root.querySelectorAll?.('[data-mermaid=pending]').forEach(render);
    for (const [node, url] of urls) if (!node.isConnected) { URL.revokeObjectURL(url); urls.delete(node); }
  }
  window.flashcramRenderDiagrams = scan;
  document.addEventListener('DOMContentLoaded', () => scan());
  document.addEventListener('htmx:afterSwap', event => scan(event.detail.target));
  // Alpine toggles hidden faces via style changes; render only once visible.
  new MutationObserver(() => scan()).observe(document.documentElement, {subtree:true, childList:true, attributes:true, attributeFilter:['style']});
})();
