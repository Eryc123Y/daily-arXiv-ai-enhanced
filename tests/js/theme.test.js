const test = require('node:test');
const assert = require('node:assert/strict');

const Theme = require('../../js/theme.js');

function storage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: key => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value); },
    removeItem: key => { delete data[key]; },
    data,
  };
}

test('themes: the system choice first, each with a name and a note', () => {
  assert.equal(Theme.THEMES[0].id, 'auto');
  assert.deepEqual(Theme.THEMES.map(t => t.id), ['auto', 'preprint', 'lamplight', 'anaglyph', 'graphite']);
  assert.ok(Theme.THEMES.every(t => t.name && t.note));
});

test('a saved theme is read back, and anything unknown or unreadable means auto', () => {
  assert.equal(Theme.read(storage({ [Theme.KEY]: 'anaglyph' })), 'anaglyph');
  assert.equal(Theme.read(storage({ [Theme.KEY]: 'neon' })), 'auto');
  assert.equal(Theme.read({ getItem() { throw new Error('blocked'); } }), 'auto');
});

test('auto is stored as no choice, and applying it removes the attribute', () => {
  const store = storage({ [Theme.KEY]: 'graphite' });
  Theme.save(store, 'auto');
  assert.deepEqual(store.data, {});
  Theme.save(store, 'lamplight');
  assert.equal(store.data[Theme.KEY], 'lamplight');

  const doc = { documentElement: { dataset: {} } };
  Theme.apply(doc, 'preprint');
  assert.equal(doc.documentElement.dataset.theme, 'preprint');
  Theme.apply(doc, 'auto');
  assert.equal('theme' in doc.documentElement.dataset, false);
});
