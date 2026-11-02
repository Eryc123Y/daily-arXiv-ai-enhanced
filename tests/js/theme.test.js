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

test('light and dark themes are listed separately, each with a name and a note', () => {
  assert.deepEqual(Theme.LIGHT.map(t => t.id), ['preprint', 'graphite']);
  assert.deepEqual(Theme.DARK.map(t => t.id), ['lilac', 'lamplight', 'anaglyph']);
  assert.deepEqual(Theme.MODES.map(m => m.id), ['system', 'light', 'dark']);
  assert.ok([...Theme.LIGHT, ...Theme.DARK, ...Theme.MODES].every(t => t.name));
});

test('defaults: follow the system, Preprint by day, Lilac by night', () => {
  assert.deepEqual(Theme.read(storage()), { mode: 'system', light: 'preprint', dark: 'lilac' });
  assert.deepEqual(Theme.read({ getItem() { throw new Error('blocked'); } }), { mode: 'system', light: 'preprint', dark: 'lilac' });
});

test('saved choices are read back, and a theme in the wrong slot falls back to the default', () => {
  const store = storage();
  Theme.save(store, { mode: 'dark', light: 'graphite', dark: 'anaglyph' });
  assert.deepEqual(Theme.read(store), { mode: 'dark', light: 'graphite', dark: 'anaglyph' });
  store.data[Theme.KEYS.dark] = 'preprint';
  assert.equal(Theme.read(store).dark, 'lilac');
});

test('the page theme follows the mode and the system', () => {
  const prefs = { mode: 'system', light: 'graphite', dark: 'lamplight' };
  assert.equal(Theme.resolve(prefs, false), 'graphite');
  assert.equal(Theme.resolve(prefs, true), 'lamplight');
  assert.equal(Theme.resolve({ ...prefs, mode: 'light' }, true), 'graphite');
  assert.equal(Theme.resolve({ ...prefs, mode: 'dark' }, false), 'lamplight');

  const doc = { documentElement: { dataset: {} } };
  Theme.apply(doc, 'lilac');
  assert.equal(doc.documentElement.dataset.theme, 'lilac');
});
