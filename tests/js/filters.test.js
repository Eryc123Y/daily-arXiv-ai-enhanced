const test = require('node:test');
const assert = require('node:assert/strict');

const Filters = require('../../js/filters.js');

const MAIN = ['cs.CV', 'cs.LG'];
const entry = (id, categories, extra = {}, info = {}) => ({
  record: { id, categories, title: `Paper ${id}`, summary: 'abstract', authors: ['Ada'], ...extra },
  info: { matched: false, match: { keywords: [], authors: [] }, topics: [], ...info },
});
const stereo = { matched: true, match: { keywords: ['stereo'], authors: [] }, topics: [{ name: 'Stereo', index: 0 }] };
const ENTRIES = [
  entry('1', ['cs.CV'], { code_url: 'https://github.com/a/b' }, stereo),
  entry('2', ['cs.CV'], {}, stereo),
  entry('3', ['cs.LG'], { code_url: 'https://github.com/c/d' }),
  entry('4', ['math.OC', 'cs.LG'], { code_url: 'https://a.github.io/p' }),
];
const base = { topic: 'all', category: 'all', codeOnly: false, query: '' };
const ids = filters => Filters.apply(ENTRIES, filters, MAIN).map(e => e.record.id);

test('topic, category, code and search combine', () => {
  assert.deepEqual(ids(base), ['1', '2', '3', '4']);
  assert.deepEqual(ids({ ...base, topic: 'matches' }), ['1', '2']);
  assert.deepEqual(ids({ ...base, topic: 'Stereo', codeOnly: true }), ['1']);
  assert.deepEqual(ids({ ...base, category: 'other' }), ['4']);
  assert.deepEqual(ids({ ...base, codeOnly: true }), ['1', '3']);
  assert.deepEqual(ids({ ...base, query: 'paper 3' }), ['3']);
});

test('a project page does not count as code', () => {
  assert.deepEqual(ids({ ...base, category: 'other', codeOnly: true }), []);
});

test('each count applies every other active filter but its own', () => {
  const counts = Filters.counts(ENTRIES, { ...base, topic: 'matches', codeOnly: true }, MAIN, ['Stereo']);
  assert.equal(counts.code, 1);
  assert.equal(counts.categories.get('all'), 1);
  assert.equal(counts.categories.get('cs.CV'), 1);
  assert.equal(counts.categories.get('cs.LG') || 0, 0);
  assert.equal(counts.topics.get('all'), 2);
  assert.equal(counts.topics.get('matches'), 1);
  assert.equal(counts.topics.get('Stereo'), 1);
});

test('counts without other filters are the plain totals', () => {
  const counts = Filters.counts(ENTRIES, base, MAIN, ['Stereo']);
  assert.equal(counts.code, 2);
  assert.equal(counts.categories.get('all'), 4);
  assert.equal(counts.categories.get('other'), 1);
  assert.equal(counts.topics.get('matches'), 2);
});

test('refinements are active when a category or code filter is set', () => {
  assert.equal(Filters.isRefined(base), false);
  assert.equal(Filters.isRefined({ ...base, category: 'cs.CV' }), true);
  assert.equal(Filters.isRefined({ ...base, codeOnly: true }), true);
});
