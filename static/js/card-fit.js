/* Reflow card text at the largest readable size; never transform or clip a face. */
(function (global) {
  function largestSize(base, floor, fits) {
    if (fits(base)) return base;
    if (!fits(floor)) return floor;
    let low = floor, high = base;
    for (let i = 0; i < 6 && high - low > .25; i++) {
      const mid = (low + high) / 2;
      if (fits(mid)) low = mid; else high = mid;
    }
    return low;
  }
  if (typeof module !== 'undefined') module.exports = {largestSize};
  if (!global.document) return;
  let frame = null;
  const observed = new Set();
  const observer = new ResizeObserver(() => schedule());
  function fit(content) {
    if (!content.getClientRects().length || content.clientHeight < 2) return;
    const face = [...content.querySelectorAll('.fc-review-face')].find(el => el.getClientRects().length && getComputedStyle(el).display !== 'none');
    const inner = face?.querySelector('.fc-review-face-inner');
    if (!inner) return;
    // Hinted fronts fill the viewport so their compact hint sits at its bottom.
    inner.style.minHeight = face.querySelector('[data-hint]') ? content.clientHeight + 'px' : '';
    // Pinch zoom should enlarge the current layout, not cause compensating shrinkage.
    if ((window.visualViewport?.scale || 1) > 1.01) return;
    face.style.removeProperty('font-size');
    face.classList.remove('fc-card-compact');
    const base = parseFloat(getComputedStyle(face).fontSize);
    const mobile = window.matchMedia('(max-width: 639px)').matches;
    const floor = mobile ? Math.min(base, Math.max(16, parseFloat(getComputedStyle(document.documentElement).fontSize))) : base * .8;
    const fits = size => {
      face.style.fontSize = size + 'px';
      window.flashcramFitMath?.(face);
      content.querySelectorAll('.fc-table-scroll').forEach(wrapper => {
        wrapper.toggleAttribute('data-no-swipe', wrapper.scrollWidth > wrapper.clientWidth + 1);
      });
      return inner.getBoundingClientRect().height <= content.clientHeight + 1 && inner.scrollWidth <= content.clientWidth + 1;
    };
    if (fits(base)) return;
    if (mobile) face.classList.add('fc-card-compact');
    const size = largestSize(base, floor, fits);
    fits(size); // Leave the DOM at the chosen size, including math fitting.
  }
  function run() {
    frame = null;
    document.querySelectorAll('.fc-review-content').forEach(content => {
      if (!observed.has(content)) { observer.observe(content); observed.add(content); }
      content.querySelectorAll('.fc-rendered-content table').forEach(table => {
        if (table.parentElement.classList.contains('fc-table-scroll')) return;
        const wrapper = document.createElement('div'); wrapper.className = 'fc-table-scroll';
        wrapper.setAttribute('tabindex', '0'); wrapper.setAttribute('role', 'region'); wrapper.setAttribute('aria-label', 'Card table');
        table.before(wrapper); wrapper.append(table);
      });
      fit(content);
    });
    for (const content of observed) if (!content.isConnected) { observer.unobserve(content); observed.delete(content); }
  }
  function schedule() { if (frame === null) frame = window.requestAnimationFrame(run); }
  window.flashcramFitReviewText = schedule;
  document.addEventListener('DOMContentLoaded', schedule);
  document.addEventListener('htmx:afterSwap', schedule);
  document.addEventListener('load', event => { if (event.target.matches?.('.fc-review-content img')) schedule(); }, true);
  window.addEventListener('resize', schedule);
  window.addEventListener('orientationchange', schedule);
  window.visualViewport?.addEventListener('resize', schedule);
  document.fonts?.ready.then(schedule);
  document.fonts?.addEventListener('loadingdone', schedule);
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
})(typeof window !== 'undefined' ? window : globalThis);
