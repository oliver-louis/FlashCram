(function(global) {
  function promptCustomizer() {
    return {
      saved: {}, draft: {}, defaults: {}, busy: false, copyMessage: '', opener: null, oldOverflow: '', timer: null,
      init() {
        this.saved = JSON.parse(this.$root.querySelector('#prompt-options-data').textContent);
        this.defaults = JSON.parse(this.$root.querySelector('#prompt-defaults-data').textContent);
        this.draft = {...this.saved};
        this.resizeHandler = () => {
          if (!this.$refs.drawer.open) return;
          this.$refs.drawer.style.height = (global.visualViewport?.height || global.innerHeight) + 'px';
          this.$refs.drawer.style.top = (global.visualViewport?.offsetTop || 0) + 'px';
        };
        global.visualViewport?.addEventListener('resize', this.resizeHandler);
        global.visualViewport?.addEventListener('scroll', this.resizeHandler);
        global.addEventListener('resize', this.resizeHandler);
      },
      open() {
        this.draft = {...this.saved}; this.$refs.status.replaceChildren(); this.opener = document.activeElement;
        this.oldOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
        this.$refs.drawer.showModal(); this.resizeHandler(); this.$refs.drawer.querySelector('.fc-prompt-drawer-body').scrollTop = 0; this.$refs.drawerHeading.focus({preventScroll:true});
      },
      cancel() { if (!this.busy) { this.draft = {...this.saved}; this.close(); } },
      close() { this.$refs.drawer.close(); document.body.style.overflow = this.oldOverflow; this.opener?.focus({preventScroll:true}); },
      reset() { this.draft = {...this.defaults}; },
      beforeSwap(event) { if (event.detail.xhr.status === 422) { event.detail.shouldSwap = true; event.detail.isError = false; } },
      afterRequest(event) {
        this.busy = false;
        if (event.detail.xhr.status === 422) { this.$nextTick(() => this.$refs.status.focus()); return; }
        if (!event.detail.successful) {
          this.$refs.status.textContent = 'Could not save options. Your changes are still here; please try again.'; return;
        }
        const doc = new DOMParser().parseFromString(event.detail.xhr.responseText, 'text/html');
        const result = doc.querySelector('#saved-prompt-options');
        if (!result) {
          if (event.detail.xhr.status !== 422) this.$refs.status.textContent = 'Could not apply options. Please try again.';
          return;
        }
        this.saved = JSON.parse(result.textContent); this.draft = {...this.saved}; this.copyMessage = ''; this.close();
      },
      async copy() {
        try {
          if (!global.navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
          await global.navigator.clipboard.writeText(this.$root.querySelector('#generation-prompt').textContent);
          this.copyMessage = 'Copied'; clearTimeout(this.timer); this.timer = setTimeout(() => {this.copyMessage = '';}, 2000);
        } catch (_) { this.copyMessage = 'Could not copy. Select and copy the prompt below.'; }
      },
      destroy() { global.visualViewport?.removeEventListener('resize', this.resizeHandler); global.visualViewport?.removeEventListener('scroll', this.resizeHandler); global.removeEventListener('resize', this.resizeHandler); clearTimeout(this.timer); if (this.$refs.drawer.open) document.body.style.overflow = this.oldOverflow; },
    };
  }
  if (typeof module !== 'undefined') module.exports = {promptCustomizer};
  if (global.document) document.addEventListener('alpine:init', () => Alpine.data('promptCustomizer', promptCustomizer));
})(typeof window !== 'undefined' ? window : globalThis);
