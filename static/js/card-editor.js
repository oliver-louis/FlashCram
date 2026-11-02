/* Card authoring helpers. Markdown remains the stored source of truth. */
(function (global) {
  'use strict';
  const snapshot = el => ({ value: el.value, start: el.selectionStart, end: el.selectionEnd });
  const replace = (state, start, end, value, selectionStart, selectionEnd = selectionStart) => ({
    value: state.value.slice(0, start) + value + state.value.slice(end), start: selectionStart, end: selectionEnd,
  });
  const escaped = (text, index) => {
    let slashes = 0;
    while (index > 0 && text[--index] === '\\') slashes++;
    return slashes % 2 === 1;
  };
  function protectedAt(text, cursor, includeCode = true) {
    let fence = null, math = null;
    for (const line of text.slice(0, cursor).split('\n')) {
      const match = line.match(/^\s*(`{3,}|~{3,})/);
      if (match && !math) {
        if (!fence) fence = match[1];
        else if (match[1][0] === fence[0] && match[1].length >= fence.length) fence = null;
      }
      if (fence) continue;
      for (let i = 0; i < line.length; i++) {
        if (escaped(line, i)) continue;
        const token = line.slice(i, i + 2);
        if (!math && ['\\(', '\\[', '$$'].includes(token)) { math = token === '\\(' ? '\\)' : token === '\\[' ? '\\]' : '$$'; i++; }
        else if (math && token === math) { math = null; i++; }
      }
    }
    if (fence || math) return true;
    if (includeCode) {
      const line = text.slice(text.lastIndexOf('\n', cursor - 1) + 1, cursor);
      const ticks = line.match(/(?<!\\)`+/g) || [];
      let open = null;
      ticks.forEach(t => { if (!open) open = t; else if (t === open) open = null; });
      if (open) return true;
    }
    return false;
  }
  function inlineRange(state, token) {
    const { value, start, end } = state;
    const lineStart = value.lastIndexOf('\n', Math.max(0, start - 1)) + 1;
    let lineEnd = value.indexOf('\n', end);
    if (lineEnd < 0) lineEnd = value.length;
    let opening = null;
    for (let i = lineStart; i <= lineEnd - token.length; i++) {
      if (value.slice(i, i + token.length) !== token || escaped(value, i)) continue;
      if (token === '*' && (value[i - 1] === '*' || value[i + 1] === '*')) continue;
      if (token === '_' && /\w/.test(value[i - 1] || '') && /\w/.test(value[i + 1] || '')) continue;
      if (opening === null) opening = i;
      else {
        if (start >= opening + token.length && end <= i) return { opening, closing: i, token };
        opening = null;
      }
      i += token.length - 1;
    }
    return null;
  }
  function inline(state, token) {
    if (token === '_' && inlineRange(state, '*')) token = '*';
    if (protectedAt(state.value, state.start, token !== '`')) return state;
    const range = inlineRange(state, token);
    if (range) {
      if (state.start === state.end) {
        if (range.closing === range.opening + token.length) return replace(state, range.opening, range.closing + token.length, '', range.opening);
        return { ...state, start: range.closing + token.length, end: range.closing + token.length };
      }
      const inner = state.value.slice(range.opening + token.length, range.closing);
      return replace(state, range.opening, range.closing + token.length, inner, state.start - token.length, state.end - token.length);
    }
    const selected = state.value.slice(state.start, state.end);
    if (selected.startsWith(token) && selected.endsWith(token) && selected.length >= token.length * 2) {
      return replace(state, state.start, state.end, selected.slice(token.length, -token.length), state.start, state.end - token.length * 2);
    }
    return replace(state, state.start, state.end, token + selected + token, state.start + token.length, state.end + token.length);
  }
  function list(state, ordered) {
    const start = state.value.lastIndexOf('\n', Math.max(0, state.start - 1)) + 1;
    let end = state.value.indexOf('\n', state.end > state.start && state.value[state.end - 1] === '\n' ? state.end - 1 : state.end);
    if (end < 0) end = state.value.length;
    const lines = state.value.slice(start, end).split('\n');
    let offset = start;
    if (lines.some(line => { const blocked = protectedAt(state.value, offset); offset += line.length + 1; return blocked || /^\s*(`{3,}|~{3,}|\\\[|\$\$)/.test(line); })) return state;
    const wanted = ordered ? /^\s*\d+\. / : /^\s*[-+*] /;
    const remove = lines.every(line => wanted.test(line));
    let text = lines.map((line, i) => {
      const [, indent, body] = line.match(/^(\s*)(.*)$/);
      const clean = body.replace(/^(?:[-+*]|\d+\.) /, '');
      return indent + (remove ? '' : ordered ? `${i + 1}. ` : '- ') + clean;
    }).join('\n');
    if (!remove && start > 0) {
      const prev = state.value.slice(0, start - 1).split('\n').pop();
      if (prev.trim() && !/^\s*(?:[-+*]|\d+\.) /.test(prev)) text = '\n' + text;
    }
    return replace(state, start, end, text, start, start + text.length);
  }
  function continueList(state) {
    if (state.start !== state.end || protectedAt(state.value, state.start)) return null;
    const start = state.value.lastIndexOf('\n', Math.max(0, state.start - 1)) + 1;
    const line = state.value.slice(start, state.start);
    const match = line.match(/^(\s*)([-+*]|\d+\.)( )([\s\S]*)$/);
    if (!match) return null;
    if (!match[4].trim()) return replace(state, start, state.end, '', start);
    const marker = /\d/.test(match[2]) ? `${parseInt(match[2], 10) + 1}.` : match[2];
    const text = '\n' + match[1] + marker + ' ';
    return replace(state, state.start, state.end, text, state.start + text.length);
  }
  function spaceTypedList(state) {
    const start = state.value.lastIndexOf('\n', Math.max(0, state.start - 1)) + 1;
    if (!start || protectedAt(state.value, start) || !/^(?:[-+*]|\d+\.) $/.test(state.value.slice(start, state.start))) return state;
    const prev = state.value.slice(0, start - 1).split('\n').pop();
    if (!prev.trim() || /^\s*(?:[-+*]|\d+\.) /.test(prev)) return state;
    return replace(state, start, start, '\n', state.start + 1);
  }
  const commands = { inline, inlineRange, list, continueList, spaceTypedList, protectedAt };
  if (typeof module !== 'undefined') module.exports = commands;
  if (!global.document) return;

  document.addEventListener('alpine:init', () => {
    Alpine.data('cardEditor', () => ({
      modal: false, format: 'plaintext', focusedFace: 'front', equationMode: 'inline', equationLatex: '',
      imageName: '', imageUrl: '', removeExisting: false, preview: false, busy: false, intent: 'save',
      revision: 0, histories: {}, baseline: '', opener: null, objectUrl: null, previewScroll: 0,
      init() {
        this.modal = this.$root.dataset.modal === 'true';
        this.opener = document.activeElement;
        this.format = this.$refs.form.querySelector('[name=content_format]:checked').value;
        this.imageUrl = this.$refs.existingImage?.content.textContent.trim() || '';
        this.imageName = this.imageUrl ? 'Current image' : '';
        for (const face of ['front', 'back']) this.histories[face] = { entries: [snapshot(this.field(face))], index: 0 };
        this.baseline = this.fingerprint();
        this.unloadHandler = event => { if (this.dirty()) { event.preventDefault(); event.returnValue = ''; } };
        this.focusHandler = event => {
          if (this.modal && !this.$root.contains(event.target) && !event.target.closest?.('.ML__keyboard')) this.field(this.focusedFace).focus();
        };
        this.settleHandler = event => {
          if (this.pendingFocus && ['card-editor-errors', 'card-list'].includes(event.detail.target?.id)) {
            this.field(this.pendingFocus).focus({ preventScroll: true });
            this.pendingFocus = null;
          }
        };
        this.resizeHandler = () => {
          if (!this.modal) return;
          const viewport = window.visualViewport;
          let height = viewport?.height || window.innerHeight;
          const top = viewport?.offsetTop || 0;
          // Use the panel height, not its animated top edge. MathLive may emit
          // geometry events before the show transition has completed.
          const keyboard = document.querySelector('.ML__keyboard.is-visible .MLK__plate');
          if (keyboard) height -= keyboard.getBoundingClientRect().height;
          this.$root.style.height = Math.max(160, height) + 'px';
          this.$root.style.top = top + 'px';
          this.$root.style.setProperty('--fc-editor-height', Math.max(160, height) + 'px');
        };
        this.keyboardToggleHandler = () => window.requestAnimationFrame(() => {
          if (!this.$root.isConnected) return;
          this.resizeHandler();
          if (window.mathVirtualKeyboard?.visible) this.$refs.mathField.scrollIntoView({ block: 'nearest' });
        });
        window.visualViewport?.addEventListener('resize', this.resizeHandler);
        window.visualViewport?.addEventListener('scroll', this.resizeHandler);
        customElements.whenDefined('math-field').then(() => {
          if (!this.$root.isConnected) return;
          window.mathVirtualKeyboard?.addEventListener('geometrychange', this.resizeHandler);
          window.mathVirtualKeyboard?.addEventListener('virtual-keyboard-toggle', this.keyboardToggleHandler);
          this.resizeHandler();
        });
        this.keyboardObserver = new MutationObserver(records => {
          if (records.some(record => record.target === document.body || record.target.closest?.('.ML__keyboard'))) this.resizeHandler();
        });
        this.keyboardObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
        document.addEventListener('htmx:afterSettle', this.settleHandler);
        window.addEventListener('beforeunload', this.unloadHandler);
        document.addEventListener('focusin', this.focusHandler);
        if (this.modal) {
          this.oldOverflow = document.body.style.overflow;
          document.body.style.overflow = 'hidden';
        }
        this.$nextTick(() => { this.baseline = this.fingerprint(); this.field('front').focus({ preventScroll: true }); });
      },
      destroy() {
        this.keyboardObserver?.disconnect();
        window.visualViewport?.removeEventListener('resize', this.resizeHandler);
        window.visualViewport?.removeEventListener('scroll', this.resizeHandler);
        window.mathVirtualKeyboard?.removeEventListener('geometrychange', this.resizeHandler);
        window.mathVirtualKeyboard?.removeEventListener('virtual-keyboard-toggle', this.keyboardToggleHandler);
        document.removeEventListener('htmx:afterSettle', this.settleHandler);
        window.removeEventListener('beforeunload', this.unloadHandler);
        document.removeEventListener('focusin', this.focusHandler);
        if (this.modal) document.body.style.overflow = this.oldOverflow;
        if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
      },
      field(face) { return this.$refs[face + 'Input']; },
      fingerprint() {
        return JSON.stringify(Array.from(new FormData(this.$refs.form), ([key, value]) => [key, value instanceof File ? (value.name ? [value.name, value.size, value.lastModified] : null) : value]));
      },
      dirty() { return this.fingerprint() !== this.baseline; },
      changed() { this.revision++; },
      selectionChanged(face) { this.focusedFace = face; this.revision++; },
      active(face, token) {
        void this.revision;
        const state = snapshot(this.field(face));
        return !protectedAt(state.value, state.start, token !== '`') && !!(inlineRange(state, token) || (token === '_' && inlineRange(state, '*')));
      },
      listActive(face, ordered) {
        void this.revision;
        const state = snapshot(this.field(face));
        const line = state.value.slice(state.value.lastIndexOf('\n', state.start - 1) + 1, state.start);
        return !protectedAt(state.value, state.start) && (ordered ? /^\s*\d+\. / : /^\s*[-+*] /).test(line);
      },
      rememberCursor(face) {
        const h = this.histories[face], state = snapshot(this.field(face));
        if (h.entries[h.index].value === state.value) h.entries[h.index] = state;
      },
      record(face) {
        const h = this.histories[face], state = snapshot(this.field(face));
        if (h.entries[h.index].value !== state.value) {
          h.entries.splice(h.index + 1);
          h.entries.push(state);
          if (h.entries.length > 200) h.entries.shift();
          h.index = h.entries.length - 1;
        }
        this.changed();
      },
      apply(face, state) {
        const el = this.field(face);
        this.rememberCursor(face);
        el.value = state.value;
        el.focus({ preventScroll: true });
        el.setSelectionRange(state.start, state.end);
        this.record(face);
      },
      undo(face, redo = false) {
        this.rememberCursor(face);
        const h = this.histories[face];
        h.index = Math.max(0, Math.min(h.entries.length - 1, h.index + (redo ? 1 : -1)));
        const state = h.entries[h.index], el = this.field(face);
        el.value = state.value;
        el.setSelectionRange(state.start, state.end);
        this.changed();
      },
      beforeInput(event) {
        const face = event.target.name;
        if (!['front', 'back'].includes(face)) return;
        if (['historyUndo', 'historyRedo'].includes(event.inputType)) { event.preventDefault(); this.undo(face, event.inputType === 'historyRedo'); }
        else this.rememberCursor(face);
      },
      onInput(event) {
        const face = event.target.name;
        if (['front', 'back'].includes(face)) {
          if (this.format === 'markdown' && !event.isComposing && event.inputType === 'insertText' && event.data === ' ') {
            const state = spaceTypedList(snapshot(event.target));
            event.target.value = state.value;
            event.target.setSelectionRange(state.start, state.end);
          }
          this.record(face);
        }
        if (face === 'image_upload') this.updateImage();
        this.changed();
      },
      formatText(face, token) { if (this.format === 'markdown') this.apply(face, inline(snapshot(this.field(face)), token)); },
      formatList(face, ordered) { if (this.format === 'markdown') this.apply(face, list(snapshot(this.field(face)), ordered)); },
      onKeydown(event) {
        if (event.isComposing || event.defaultPrevented) return;
        const face = event.target.name;
        if (['front', 'back'].includes(face)) {
          const modifier = (event.ctrlKey || event.metaKey) && !event.altKey;
          const key = event.key.toLowerCase();
          if (modifier && (key === 'z' || key === 'y')) { event.preventDefault(); this.undo(face, key === 'y' || event.shiftKey); return; }
          if (this.format === 'markdown') {
            if (modifier && ['b', 'i'].includes(key)) { event.preventDefault(); this.formatText(face, key === 'b' ? '**' : '_'); return; }
            if (event.key === 'Enter' && !event.shiftKey && !modifier) {
              const next = continueList(snapshot(event.target));
              if (next) { event.preventDefault(); this.apply(face, next); return; }
            }
          }
        }
        if (event.key === 'Escape') {
          if (document.querySelector('.ML__keyboard.is-visible') || event.target.closest('math-field')) {
            event.preventDefault();
            window.mathVirtualKeyboard?.hide();
            this.field(this.focusedFace).focus({ preventScroll: true });
            return;
          }
          if (this.$root.querySelector('[data-image-zoom]:not([style*="display: none"])')) return;
          event.preventDefault();
          if (this.preview) this.backToEditing(); else this.close();
        }
        if (event.key === 'Tab' && this.modal) {
          const nodes = Array.from(this.$root.querySelectorAll('button, a[href], input, textarea, select, math-field, summary, [tabindex="0"]')).filter(el => !el.disabled && el.getClientRects().length);
          const first = nodes[0], last = nodes[nodes.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      },
      insertEquation() {
        const latex = this.equationLatex || this.$refs.mathField?.value || '';
        if (!latex.trim()) return;
        const state = snapshot(this.field(this.focusedFace));
        let wrapped = this.equationMode === 'display' ? '\\[' + latex + '\\]' : '\\(' + latex + '\\)';
        if (this.equationMode === 'display') {
          if (state.start && state.value[state.start - 1] !== '\n') wrapped = '\n\n' + wrapped;
          if (state.end < state.value.length && state.value[state.end] !== '\n') wrapped += '\n\n';
        }
        this.apply(this.focusedFace, replace(state, state.start, state.end, wrapped, state.start + wrapped.length));
      },
      addTag(tag) {
        const input = this.$refs.tagsInput;
        const tags = input.value.split(/[\s,]+/).map(v => v.toLowerCase()).filter(Boolean);
        if (!tags.includes(tag)) tags.push(tag);
        input.value = tags.join(', ');
        this.changed();
      },
      updateImage() {
        const file = this.$refs.imageInput.files[0];
        if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
        this.objectUrl = file ? URL.createObjectURL(file) : null;
        this.imageUrl = this.objectUrl || (!this.removeExisting ? this.$refs.existingImage?.content.textContent.trim() : '') || '';
        this.imageName = file?.name || (this.imageUrl ? 'Current image' : '');
        if (file) this.removeExisting = false;
        this.changed();
      },
      removeImage() { this.$refs.imageInput.value = ''; this.removeExisting = !!this.$refs.existingImage?.content.textContent.trim(); this.updateImage(); },
      assignImageFiles(files) {
        if (!files?.length || this.busy || this.preview) return;
        const transfer = new DataTransfer(); transfer.items.add(files[0]);
        this.$refs.imageInput.files = transfer.files;
        this.updateImage();
      },
      onPaste(event) {
        if (this.preview) return;
        const files = Array.from(event.clipboardData?.files || []).filter(file => file.type.startsWith('image/'));
        if (files.length) { event.preventDefault(); this.assignImageFiles(files); }
      },
      beforeRequest(event) {
        if (event.detail.elt !== this.$refs.form && !event.detail.elt.hasAttribute('data-editor-preview')) return;
        if (this.busy) { event.preventDefault(); return; }
        this.busy = true;
        this.requestIsPreview = event.detail.elt.hasAttribute('data-editor-preview');
        this.$refs.notice.textContent = '';
        // Freeze the draft while it is sent; re-enable fields without replacing them.
        this.$refs.fields.inert = true;
        if (this.requestIsPreview) this.previewScroll = this.$refs.body.scrollTop;
      },
      beforeSwap(event) {
        if (event.detail.xhr.status === 422) {
          event.detail.shouldSwap = true;
          event.detail.isError = false;
          event.detail.target = this.$root.querySelector('#card-editor-errors');
          event.detail.swapOverride = 'innerHTML';
        }
      },
      afterRequest(event) {
        if (event.detail.elt !== this.$refs.form && !event.detail.elt.hasAttribute('data-editor-preview')) return;
        this.busy = false;
        this.$refs.fields.inert = false;
        const xhr = event.detail.xhr;
        if (xhr.status === 422) {
          if (this.preview) this.backToEditing();
          this.$nextTick(() => {
            const errors = this.$root.querySelector('#card-editor-errors');
            if (errors.querySelector('[data-error-field="status"]')) this.$refs.options.open = true;
            errors.focus();
          });
          return;
        }
        if (!event.detail.successful) {
          this.$refs.notice.textContent = 'Request failed. Your draft is still here; please try again.';
          return;
        }
        if (xhr.getResponseHeader('X-Card-Saved') === 'true') {
          const tags = this.$root.querySelector('[data-saved-tags]')?.dataset.savedTags || '';
          this.baseline = this.fingerprint();
          const filters = document.querySelector('#card-filter-form');
          if (filters) {
            htmx.ajax('GET', filters.getAttribute('hx-get'), {
              source: filters, target: '#card-list', swap: 'outerHTML',
              values: { ...Object.fromEntries(new FormData(filters)), refresh_meta: '1' },
            }).catch(() => { document.querySelector('#card-save-notice').textContent = 'Card saved. Reload the deck to refresh the list.'; });
          }
          const notice = document.querySelector('#card-save-notice');
          if (notice) notice.textContent = 'Card saved.';
          if (xhr.getResponseHeader('X-Card-Continue') === 'true') this.resetDraft(tags);
          else this.close(true);
        } else if (this.requestIsPreview) {
          this.$root.querySelector('#card-editor-errors').replaceChildren();
          this.preview = true;
          window.mathVirtualKeyboard?.hide();
          this.$nextTick(() => { this.$refs.body.scrollTop = 0; this.$refs.backToEditing.focus(); window.flashcramRenderMath(this.$root.querySelector('#card-editor-preview')); });
        }
      },
      backToEditing() {
        this.preview = false;
        this.$nextTick(() => { this.field(this.focusedFace).focus({ preventScroll: true }); this.$refs.body.scrollTop = this.previewScroll; });
      },
      resetDraft(tags) {
        this.preview = false;
        this.pendingFocus = 'front';
        for (const face of ['front', 'back']) {
          this.field(face).value = '';
          this.histories[face] = { entries: [snapshot(this.field(face))], index: 0 };
        }
        this.$refs.tagsInput.value = tags;
        this.$refs.form.elements.status.value = 'normal';
        this.$refs.form.elements.image_face.value = 'back';
        this.removeImage(); this.removeExisting = false;
        this.equationLatex = ''; this.$refs.mathField.value = '';
        this.focusedFace = 'front';
        this.$root.querySelector('#card-editor-errors').replaceChildren();
        this.$root.querySelector('#card-editor-preview').replaceChildren();
        this.$refs.notice.textContent = 'Card saved. Ready for another.';
        this.$nextTick(() => { this.baseline = this.fingerprint(); this.$refs.body.scrollTop = 0; this.field('front').focus({ preventScroll: true }); });
      },
      close(saved = false) {
        if (this.busy) return;
        if (!saved && this.dirty() && !window.confirm('Discard your unsaved changes?')) return;
        this.baseline = this.fingerprint();
        window.mathVirtualKeyboard?.hide();
        if (this.modal) {
          const opener = this.opener;
          this.$root.remove();
          if (opener?.isConnected) opener.focus({ preventScroll: true });
          else document.querySelector('[data-add-card]')?.focus({ preventScroll: true });
        } else window.location.assign(this.$root.dataset.deckUrl);
      },
    }));
  });
})(typeof window !== 'undefined' ? window : globalThis);
