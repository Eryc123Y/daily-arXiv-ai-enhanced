// The Source selectors on a mixed day: Type, Area and Venue, and "Free to read" under Refine.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const PaperData = require('../../js/paper-data.js');
const Sources = require('../../js/sources.js');
const Render = require('../../js/render.js');
const Filters = require('../../js/filters.js');

const FIXTURE = path.join(__dirname, 'fixtures', 'mixed-day');
const read = name => fs.readFileSync(path.join(FIXTURE, name), 'utf8');
const RECORDS = PaperData.mergeDay(read('data/2026-11-10.jsonl'), read('data/2026-11-10_AI_enhanced_English.jsonl'));
// The fixture's list leaves out IEEE TPAMI on purpose: a venue paper whose venue is not watched.
const VENUES = Sources.venueIndex(JSON.parse(read('assets/venues.json')));
const MAIN = ['cs.CV', 'cs.AI', 'cs.LG', 'cs.CL', 'stat.ML', 'cs.GR'];
const TOPICS = [{ name: 'Stereo', keywords: ['stereo', 'disparity'] }];
const ENTRIES = RECORDS.map((record, index) => ({ record, index, info: Render.describe(record, ['stereo', 'disparity'], [], TOPICS) }));
const base = { topic: 'all', category: 'all', codeOnly: false, freeOnly: false, type: 'all', area: 'all', source: 'all', query: '' };
const ids = (filters, venues = VENUES, entries = ENTRIES) => Filters.apply(entries, filters, MAIN, venues).map(e => e.record.id);
const counts = (filters, venues = VENUES, entries = ENTRIES) => Filters.counts(entries, filters, MAIN, ['Stereo'], venues);
const byId = id => RECORDS.find(r => r.id === id);

const ARXIV = ['2611.04001', '2611.04002', '2611.04003'];
const TCSVT = ['doi:10.1109/tcsvt.2026.3400001', 'doi:10.1109/tcsvt.2026.3400002'];
const ICLR = 'openreview:AbCdEf123';
const TVCG = 'doi:10.1109/tvcg.2026.3500001';
const TIP = 'doi:10.1109/tip.2026.3600001';
const TPAMI = '2605.01234';

// --- Venue index ------------------------------------------------------------------

test('the venue index keeps well-formed entries by name', () => {
  const index = Sources.venueIndex([
    { name: 'ACM TOG', kind: 'journal', area: 'Graphics and VR' },
    { name: ' CVPR ', kind: 'conference', area: null },
    { name: 'X', kind: 'magazine', area: 'Y' },
    { kind: 'journal' },
    'TIP',
  ]);
  assert.deepEqual([...index], [['ACM TOG', { kind: 'journal', area: 'Graphics and VR', top: true }], ['CVPR', { kind: 'conference', area: null, top: true }]]);
  assert.equal(Sources.venueIndex(null).size, 0);
  assert.equal(Sources.venueIndex({ name: 'ACM TOG' }).size, 0);
});

test('a venue is top unless the list says top: false (lists written before the flag had only top venues)', () => {
  const index = Sources.venueIndex([
    { name: 'ACL', kind: 'conference', area: 'NLP', top: true },
    { name: 'EACL', kind: 'conference', area: 'NLP', top: false },
    { name: 'CVPR', kind: 'conference', area: 'ML' },
  ]);
  assert.deepEqual([...index].map(([name, v]) => [name, v.top]), [['ACL', true], ['EACL', false], ['CVPR', true]]);
});

test('each paper has a type and an area from the venue list', () => {
  assert.equal(Sources.sourceType(byId(ARXIV[0]), VENUES), 'arxiv');
  assert.equal(Sources.sourceType(byId(TCSVT[0]), VENUES), 'journal');
  assert.equal(Sources.sourceType(byId(ICLR), VENUES), 'conference');
  assert.equal(Sources.sourceType(byId(TPAMI), VENUES), null);
  assert.equal(Sources.sourceArea(byId(TVCG), VENUES), 'Graphics and VR');
  assert.equal(Sources.sourceArea(byId(ARXIV[0]), VENUES), null);
  assert.equal(Sources.sourceArea(byId(TPAMI), VENUES), null);
});

test('an arXiv paper published in a watched journal is still an arXiv preprint', () => {
  const published = { ...byId(ARXIV[0]), venue: 'IEEE TVCG' };
  assert.equal(Sources.sourceType(published, VENUES), 'arxiv');
  assert.equal(Sources.sourceArea(published, VENUES), null);
});

test('free to read: arXiv papers and venue papers with an open-access copy', () => {
  assert.deepEqual(RECORDS.filter(Sources.isFreeToRead).map(r => r.id), ['2611.04001', TCSVT[0], '2611.04002', ICLR, '2611.04003']);
  assert.equal(Sources.isFreeToRead({ ...byId(TIP), oa_url: 'javascript:alert(1)' }), false);
});

// --- Filters ----------------------------------------------------------------------

test('type keeps arXiv preprints, top conferences or top journals; an unwatched venue only under All', () => {
  assert.equal(ids(base).length, 9);
  assert.deepEqual(ids({ ...base, type: 'arxiv' }), ARXIV);
  assert.deepEqual(ids({ ...base, type: 'conference' }), [ICLR]);
  assert.deepEqual(ids({ ...base, type: 'journal' }), [TCSVT[0], TCSVT[1], TVCG, TIP]);
  assert.ok(ids(base).includes(TPAMI));
});

test('area keeps the venue papers of one area; arXiv papers have none', () => {
  assert.deepEqual(ids({ ...base, area: 'ML and vision' }), [TCSVT[0], TCSVT[1], ICLR, TIP]);
  assert.deepEqual(ids({ ...base, area: 'Graphics and VR' }), [TVCG]);
  assert.deepEqual(ids({ ...base, area: 'Vision science' }), []);
});

test('type, area, venue, free to read, topic and category combine', () => {
  assert.deepEqual(ids({ ...base, type: 'journal', area: 'Graphics and VR' }), [TVCG]);
  assert.deepEqual(ids({ ...base, type: 'journal', source: 'venue:IEEE TCSVT', freeOnly: true }), [TCSVT[0]]);
  assert.deepEqual(ids({ ...base, freeOnly: true, topic: 'matches' }), ['2611.04001', TCSVT[0]]);
  assert.deepEqual(ids({ ...base, freeOnly: true, category: 'cs.CV' }), ['2611.04001']);
  assert.deepEqual(ids({ ...base, type: 'arxiv', category: 'cs.LG', codeOnly: true }), []);
  assert.deepEqual(ids({ ...base, type: 'journal', category: 'cs.CV' }), []);
});

test('without a venue list every venue paper is ungrouped but still reachable by venue', () => {
  const none = Sources.venueIndex(null);
  assert.deepEqual(ids({ ...base, type: 'journal' }, none), []);
  assert.deepEqual(ids({ ...base, type: 'arxiv' }, none), ARXIV);
  assert.deepEqual(ids({ ...base, source: 'venue:IEEE TVCG' }, none), [TVCG]);
  assert.deepEqual(ids(base, undefined).length, 9);
});

// --- Counts -----------------------------------------------------------------------

test('type, area, venue and free counts apply every other active filter but their own', () => {
  const c = counts({ ...base, topic: 'matches', type: 'journal', area: 'ML and vision', freeOnly: true });
  // Topic "matches" holds 2611.04001, the open-access TCSVT paper and TVCG.
  assert.deepEqual([...c.types], [['all', 1], ['arxiv', 0], ['conference', 0], ['journal', 1], ['other', 0]]);
  assert.deepEqual([...c.areas], [['all', 1], ['ML and vision', 1]]);
  assert.equal(c.free, 1);
  assert.equal(c.sources.get('all'), 1);
  assert.equal(c.sources.get('venue:IEEE TCSVT'), 1);
  assert.equal(c.topics.get('matches'), 1);
  assert.equal(c.topics.get('all'), 1);
});

test('plain counts are the day totals', () => {
  const c = counts(base);
  assert.deepEqual([...c.types], [['all', 9], ['arxiv', 3], ['conference', 1], ['journal', 4], ['other', 0]]);
  assert.deepEqual([...c.areas], [['all', 9], ['ML and vision', 4], ['Graphics and VR', 1]]);
  assert.equal(c.free, 5);
});

test('a free-to-read choice changes the other counts', () => {
  const c = counts({ ...base, freeOnly: true });
  assert.deepEqual([...c.types], [['all', 5], ['arxiv', 3], ['conference', 1], ['journal', 1], ['other', 0]]);
  assert.equal(c.categories.get('all'), 5);
  assert.equal(c.code, 1);
});

// --- The rows ---------------------------------------------------------------------

const rows = (filters, venues = VENUES, records = RECORDS) =>
  Filters.sourceGroups(records, counts(filters, venues, ENTRIES.filter(e => records.includes(e.record))), filters, venues);
const triples = options => options.map(o => [o.key, o.label, o.count]);

test('the three rows on a mixed day', () => {
  const groups = rows(base);
  assert.deepEqual(triples(groups.types), [
    ['all', 'All', 9], ['arxiv', 'arXiv preprints', 3], ['conference', 'Top conferences', 1], ['journal', 'Top journals', 4],
  ]);
  assert.deepEqual(triples(groups.areas), [
    ['all', 'All', 9], ['ML and vision', 'ML and vision', 4], ['Graphics and VR', 'Graphics and VR', 1], ['Vision science', 'Vision science', 0],
  ]);
  assert.deepEqual(triples(groups.venues), [
    ['all', 'All', 9],
    ['venue:IEEE TCSVT', 'IEEE TCSVT', 2],
    ['venue:ICLR', 'ICLR', 1],
    ['venue:IEEE TIP', 'IEEE TIP', 1],
    ['venue:IEEE TPAMI', 'IEEE TPAMI', 1],
    ['venue:IEEE TVCG', 'IEEE TVCG', 1],
  ]);
});

test('the venue row holds only the venues of the chosen type and area', () => {
  assert.deepEqual(rows({ ...base, type: 'journal' }).venues.map(o => o.key), ['all', 'venue:IEEE TCSVT', 'venue:IEEE TIP', 'venue:IEEE TVCG']);
  assert.deepEqual(rows({ ...base, type: 'journal', area: 'Graphics and VR' }).venues.map(o => o.key), ['all', 'venue:IEEE TVCG']);
  assert.deepEqual(rows({ ...base, type: 'arxiv' }).venues, []);
});

test('without a venue list: All and arXiv preprints, no area row, every venue', () => {
  const groups = rows(base, Sources.venueIndex(null));
  assert.deepEqual(triples(groups.types), [['all', 'All', 9], ['arxiv', 'arXiv preprints', 3]]);
  assert.deepEqual(groups.areas, []);
  assert.equal(groups.venues.length, 6);
});

test('an arXiv-only day has no source rows', () => {
  const arxivOnly = RECORDS.filter(r => PaperData.isArxiv(r));
  assert.equal(rows(base, VENUES, arxivOnly), null);
  assert.equal(Filters.hasVenuePapers(arxivOnly), false);
  assert.equal(Filters.hasVenuePapers(RECORDS), true);
});

// --- Heading, clearing and day switches -------------------------------------------

test('every new selector counts as a refinement', () => {
  assert.equal(Filters.isRefined(base), false);
  for (const change of [{ type: 'journal' }, { area: 'Graphics and VR' }, { source: 'venue:ICLR' }, { freeOnly: true }]) {
    assert.equal(Filters.isRefined({ ...base, ...change }), true, JSON.stringify(change));
  }
});

test('the heading names the active refinements in order', () => {
  const name = key => key.replace(/^venue:/, '');
  assert.deepEqual(Filters.refinementPhrases(base, name), []);
  assert.deepEqual(Filters.refinementPhrases({ ...base, type: 'journal', area: 'Graphics and VR' }, name), ['top journals', 'Graphics and VR']);
  assert.deepEqual(
    Filters.refinementPhrases({ ...base, codeOnly: true, freeOnly: true, type: 'arxiv', source: 'venue:ACM TOG' }, name),
    ['with code', 'free to read', 'arXiv preprints', 'from ACM TOG'],
  );
  assert.deepEqual(Filters.refinementPhrases({ ...base, type: 'conference' }, name), ['top conferences']);
});

test('a new day keeps the choices it can show and resets the rest', () => {
  const chosen = { ...base, type: 'journal', area: 'Graphics and VR', source: 'venue:IEEE TVCG', freeOnly: true };
  assert.deepEqual(Filters.keepValid(chosen, RECORDS, VENUES), chosen);
  const noTvcg = RECORDS.filter(r => r.id !== TVCG);
  assert.deepEqual(Filters.keepValid(chosen, noTvcg, VENUES), { ...chosen, source: 'all' });
  assert.deepEqual(Filters.keepValid({ ...chosen, type: 'magazine', area: 'Astronomy' }, RECORDS, VENUES), { ...chosen, type: 'all', area: 'all' });
  const arxivOnly = RECORDS.filter(r => PaperData.isArxiv(r));
  assert.deepEqual(Filters.keepValid(chosen, arxivOnly, VENUES), { ...base });
});

test('type and area counts ignore the chosen venue, which sits under them', () => {
  const c = counts({ ...base, source: 'venue:IEEE TVCG' });
  assert.deepEqual([...c.types], [['all', 9], ['arxiv', 3], ['conference', 1], ['journal', 4], ['other', 0]]);
  assert.deepEqual([...c.areas], [['all', 9], ['ML and vision', 4], ['Graphics and VR', 1]]);
  assert.equal(c.sources.get('venue:IEEE TCSVT'), 2);
  assert.equal(c.free, 0);
});

// --- Top venues and the rest ------------------------------------------------------

// The fixture's list with IEEE TIP and IEEE TVCG not marked top.
const TIERED = Sources.venueIndex(JSON.parse(read('assets/venues.json'))
  .map(v => (['IEEE TIP', 'IEEE TVCG'].includes(v.name) ? { ...v, top: false } : v)));

test('the type key: a top venue by its kind, any other watched venue as other, unwatched none', () => {
  assert.equal(Sources.typeKey(byId(ARXIV[0]), TIERED), 'arxiv');
  assert.equal(Sources.typeKey(byId(TCSVT[0]), TIERED), 'journal');
  assert.equal(Sources.typeKey(byId(ICLR), TIERED), 'conference');
  assert.equal(Sources.typeKey(byId(TIP), TIERED), 'other');
  assert.equal(Sources.typeKey(byId(TPAMI), TIERED), null);
  assert.equal(Sources.sourceType(byId(TIP), TIERED), 'journal');
});

test('top journals leave out the venues not marked top; other venues hold them', () => {
  assert.deepEqual(ids({ ...base, type: 'journal' }, TIERED), TCSVT);
  assert.deepEqual(ids({ ...base, type: 'other' }, TIERED), [TVCG, TIP]);
  assert.deepEqual(ids({ ...base, type: 'other', area: 'Graphics and VR' }, TIERED), [TVCG]);
});

test('the type row adds other venues when the list has venues not marked top', () => {
  const groups = rows(base, TIERED);
  assert.deepEqual(triples(groups.types), [
    ['all', 'All', 9], ['arxiv', 'arXiv preprints', 3], ['conference', 'Top conferences', 1], ['journal', 'Top journals', 2], ['other', 'Other venues', 2],
  ]);
  assert.deepEqual(rows({ ...base, type: 'other' }, TIERED).venues.map(o => o.key), ['all', 'venue:IEEE TIP', 'venue:IEEE TVCG']);
  assert.deepEqual(rows(base).types.map(o => o.key), ['all', 'arxiv', 'conference', 'journal']);
});

test('other venues read as a refinement and survive a day switch only while the list has them', () => {
  const name = key => key.replace(/^venue:/, '');
  assert.deepEqual(Filters.refinementPhrases({ ...base, type: 'other' }, name), ['other venues']);
  assert.equal(Filters.isRefined({ ...base, type: 'other' }), true);
  assert.equal(Filters.keepValid({ ...base, type: 'other' }, RECORDS, TIERED).type, 'other');
  assert.equal(Filters.keepValid({ ...base, type: 'other' }, RECORDS, VENUES).type, 'all');
});
