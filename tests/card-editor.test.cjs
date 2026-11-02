const test = require('node:test');
const assert = require('node:assert/strict');
const c = require('../static/js/card-editor.js');
const state = (value, start = value.length, end = start) => ({ value, start, end });

test('bold wraps and unwraps selected text', () => {
  const wrapped = c.inline(state('some words', 5, 10), '**');
  assert.deepEqual(wrapped, state('some **words**', 7, 12));
  assert.deepEqual(c.inline(wrapped, '**'), state('some words', 5, 10));
});
test('empty toggle starts a pair and repeated toggle removes it', () => {
  const wrapped = c.inline(state(''), '**');
  assert.deepEqual(wrapped, state('****', 2));
  assert.deepEqual(c.inline(wrapped, '**'), state(''));
});
test('toggle off exits the closing marker without changing the source', () => {
  assert.deepEqual(c.inline(state('**bold**', 6), '**'), state('**bold**', 8));
  assert.deepEqual(c.inline(state('_italic_', 7), '_'), state('_italic_', 8));
});
test('inline code can be wrapped and unwrapped', () => {
  const wrapped = c.inline(state('code', 0, 4), '`');
  assert.deepEqual(c.inline(wrapped, '`'), state('code', 0, 4));
});
test('formatting inside code and math is untouched', () => {
  for (const text of ['```python\nvalue', '~~~text\nvalue', '\\(x_i', '\\[x_i', '$$x_i', '`literal']) {
    assert.deepEqual(c.inline(state(text), '**'), state(text));
  }
});
test('closed fences and math allow formatting afterward', () => {
  for (const text of ['```\ncode\n```\nwords', '\\(x\\) words', '$$x$$ words']) {
    assert.equal(c.protectedAt(text, text.length), false);
  }
});
test('escaped syntax does not activate formatting', () => {
  assert.equal(c.inlineRange(state('\\**literal**', 7), '**'), null);
});
test('bullet toolbar adds required paragraph spacing and toggles markers', () => {
  const result = c.list(state('Intro:\none\ntwo', 7, 14), false);
  assert.equal(result.value, 'Intro:\n\n- one\n- two');
  assert.equal(c.list(state('- one\n- two', 0, 11), false).value, 'one\ntwo');
});
test('numbered toolbar converts existing markers', () => {
  assert.equal(c.list(state('- one\n- two', 0, 11), true).value, '1. one\n2. two');
});
test('list selection ending at next line start leaves that line untouched', () => {
  assert.equal(c.list(state('one\ntwo', 0, 4), false).value, '- one\ntwo');
});
test('typing a list marker inserts spacing only after prose', () => {
  assert.equal(c.spaceTypedList(state('Intro:\n- ')).value, 'Intro:\n\n- ');
  for (const text of ['- ', 'Intro:\n\n- ', '- one\n- ', '```\n- ', '\\[\n- ']) {
    assert.equal(c.spaceTypedList(state(text)).value, text);
  }
});
test('Enter continues bullets and increments numbers', () => {
  assert.equal(c.continueList(state('- one')).value, '- one\n- ');
  assert.equal(c.continueList(state('9. nine')).value, '9. nine\n10. ');
  assert.equal(c.continueList(state('    - nested')).value, '    - nested\n    - ');
});
test('Enter on empty item exits the list', () => {
  assert.deepEqual(c.continueList(state('- one\n- ')), state('- one\n'));
});
test('Enter leaves math and code alone', () => {
  for (const text of ['```\n- one', '\\[\n- one', '$$\n- one']) assert.equal(c.continueList(state(text)), null);
});
test('list toolbar does not modify selected math or fenced code', () => {
  const source = state('```\nhello\n```', 0, 13);
  assert.deepEqual(c.list(source, false), source);
});

test('asterisk italic is recognized and toggled without nesting new markers', () => {
  assert.deepEqual(c.inline(state('*word*', 1, 5), '_'), state('word', 0, 4));
});

// Exercise the same component methods used by Alpine, using in-memory fields.
const vm = require('node:vm');
const fs = require('node:fs');
function editor(value = '') {
  let factory;
  const document = { addEventListener: (event, callback) => callback() };
  vm.runInNewContext(fs.readFileSync(require.resolve('../static/js/card-editor.js'), 'utf8'), {
    window: { document }, document, Alpine: { data: (_name, callback) => { factory = callback; } },
  });
  const component = factory();
  const field = { name: 'front', value, selectionStart: value.length, selectionEnd: value.length,
    focus() {}, setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; } };
  component.$refs = { frontInput: field };
  component.format = 'markdown';
  component.histories.front = { entries: [state(value)], index: 0 };
  return { component, field };
}
test('undo and redo restore toolbar commands, typed text, and selection', () => {
  const { component, field } = editor('Question');
  field.setSelectionRange(0, 8);
  component.formatText('front', '**');
  assert.equal(field.value, '**Question**');
  component.undo('front');
  assert.equal(field.value, 'Question');
  assert.equal(field.selectionEnd, 8);
  component.undo('front', true);
  assert.equal(field.value, '**Question**');
  assert.equal(field.selectionStart, 2);
  assert.equal(field.selectionEnd, 10);
});
test('undo after automatic list spacing returns to the typed marker', () => {
  const { component, field } = editor('Intro:\n-');
  component.beforeInput({ target: field, inputType: 'insertText' });
  field.value += ' '; field.setSelectionRange(field.value.length, field.value.length);
  component.onInput({ target: field, inputType: 'insertText', data: ' ' });
  assert.equal(field.value, 'Intro:\n\n- ');
  component.undo('front');
  assert.equal(field.value, 'Intro:\n-');
});
test('pasted Markdown and plaintext spaces are never automatically rewritten', () => {
  for (const [format, inputType] of [['markdown', 'insertFromPaste'], ['plaintext', 'insertText']]) {
    const { component, field } = editor();
    component.format = format;
    field.value = 'Intro:\n- '; field.setSelectionRange(field.value.length, field.value.length);
    component.onInput({ target: field, inputType, data: ' ' });
    assert.equal(field.value, 'Intro:\n- ');
  }
});
test('equation insertion uses the active face and can be undone', () => {
  const { component, field } = editor('Energy: ');
  component.equationLatex = 'E=mc^2';
  component.insertEquation();
  assert.equal(field.value, 'Energy: \\(E=mc^2\\)');
  component.undo('front');
  assert.equal(field.value, 'Energy: ');
});

test('native keyboard hides actions only after focused viewport reduction', () => {
  const base = {width:390, layoutHeight:844, height:844, editable:false, math:false};
  let s = c.keyboardState(null, base);
  assert.equal(s.open, false);
  s = c.keyboardState(s, {...base, height:760, editable:true});
  assert.equal(s.open, false, 'browser chrome or hardware keyboard focus');
  s = c.keyboardState(s, {...base, height:480, editable:true});
  assert.equal(s.open, true);
  s = c.keyboardState(s, {...base, height:490, editable:false});
  assert.equal(s.open, true, 'blur during dismissal does not flash the footer');
  s = c.keyboardState(s, base);
  assert.equal(s.open, false);
});
test('rotation resets baseline and MathLive independently hides actions', () => {
  let s = c.keyboardState(null, {width:390, layoutHeight:844, height:480, editable:true, math:false});
  assert.equal(s.open, true);
  s = c.keyboardState(s, {width:844, layoutHeight:390, height:390, editable:false, math:false});
  assert.equal(s.open, false);
  assert.equal(s.baseline, 390);
  assert.equal(c.keyboardState(s, {width:844, layoutHeight:390, height:390, editable:false, math:true}).open, true);
});
