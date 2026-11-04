/* Visibility belongs to this display only: never part of a review session or save. */
(function (global) {
  function cardHint() {
    return {
      shown: false,
      init() { this.$watch('revealed', () => { this.shown = false; this.refit(); }); },
      refit() { this.$nextTick(() => global.flashcramRenderMath?.(this.$root)); },
      toggle() { this.shown = !this.shown; this.refit(); },
    };
  }
  if (typeof module !== 'undefined') module.exports = {cardHint};
  if (global.document) document.addEventListener('alpine:init', () => Alpine.data('cardHint', cardHint));
})(typeof window !== 'undefined' ? window : globalThis);
