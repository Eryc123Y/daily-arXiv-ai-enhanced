const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const PaperData = require('../../js/paper-data.js');
const Sources = require('../../js/sources.js');
const Render = require('../../js/render.js');
const Filters = require('../../js/filters.js');

const FIXTURE = path.join(__dirname, 'fixtures', 'mixed-day', 'data');
const read = name => fs.readFileSync(path.join(FIXTURE, name), 'utf8');
const RECORDS = PaperData.mergeDay(read('2026-11-10.jsonl'), read('2026-11-10_AI_enhanced_English.jsonl'))
  .map(r => ({ ...r, date: '2026-11-10' }));
const byId = id => RECORDS.find(r => r.id === id);
const TCSVT_OA = byId('doi:10.1109/tcsvt.2026.3400001');
const TCSVT_CLOSED = byId('doi:10.1109/tcsvt.2026.3400002');
const ICLR = byId('openreview:AbCdEf123');
const TVCG = byId('doi:10.1109/tvcg.2026.3500001');
const ARXIV = byId('2611.04001');

const MAIN = ['cs.CV', 'cs.AI', 'cs.LG', 'cs.CL', 'stat.ML', 'cs.GR'];
const TOPICS = [{ name: 'Stereo', keywords: ['stereo', 'disparity'] }];
const KEYWORDS = ['stereo', 'disparity'];
const ENTRIES = RECORDS.map((record, index) => ({ record, index, info: Render.describe(record, KEYWORDS, [], TOPICS) }));
const base = { topic: 'all', category: 'all', codeOnly: false, query: '', source: 'all' };
const ids = filters => Filters.apply(ENTRIES, filters, MAIN).map(e => e.record.id);

// --- Records -------------------------------------------------------------------

test('a missing source means arXiv', () => {
  assert.equal(PaperData.isArxiv(ARXIV), true);
  assert.equal(PaperData.isArxiv({ id: 'x', source: 'arxiv' }), true);
  assert.equal(PaperData.isArxiv(TCSVT_OA), false);
  assert.equal(PaperData.isArxiv(ICLR), false);
});

test('a mixed day keeps every paper in crawl order, with its venue', () => {
  assert.equal(RECORDS.length, 7);
  assert.deepEqual(RECORDS.slice(0, 2).map(r => r.id), ['2611.04001', 'doi:10.1109/tcsvt.2026.3400001']);
  assert.equal(TCSVT_OA.venue, 'IEEE TCSVT');
  assert.equal(TCSVT_OA.AI.tldr, 'Converts 2D video to stereo with a disparity-aware network.');
});

test('a non-arXiv paper without a summary is not pending; an arXiv one is', () => {
  assert.equal(TCSVT_CLOSED.pending, false);
  assert.equal(TVCG.pending, false);
  assert.equal(byId('2611.04003').pending, true);
  assert.equal(TCSVT_OA.pending, false);
});

test('a summary record keeps the raw fields it does not repeat', () => {
  const raw = JSON.stringify({ id: 'doi:10.1/x', source: 'crossref', title: 'T', venue: 'IJCV', url: 'https://doi.org/10.1/x' });
  const ai = JSON.stringify({ id: 'doi:10.1/x', title: 'T', AI: { tldr: 't', motivation: 'm', method: 'x', result: 'r', conclusion: 'c' } });
  const [record] = PaperData.mergeDay(raw, ai);
  assert.equal(record.venue, 'IJCV');
  assert.equal(record.source, 'crossref');
  assert.equal(record.pending, false);
});

test('progress counts only papers that can get a summary', () => {
  assert.deepEqual(Render.summaryProgress(RECORDS), { done: 4, total: 5 });
  assert.deepEqual(Render.summaryProgress([ARXIV, TVCG]), { done: 1, total: 1 });
});

// --- Source keys and labels ----------------------------------------------------

test('each paper has a source key and label: arXiv, or its venue', () => {
  assert.equal(Sources.sourceKey(ARXIV), 'arxiv');
  assert.equal(Sources.sourceKey(TCSVT_OA), 'venue:IEEE TCSVT');
  assert.equal(Sources.sourceLabel(ARXIV), 'arXiv');
  assert.equal(Sources.sourceLabel(ICLR), 'ICLR 2027');
  assert.equal(Sources.sourceLabel({ id: 'doi:10.1/y', source: 'openreview' }), 'OpenReview');
  assert.equal(Sources.sourceLabel({ id: 'doi:10.1/y', source: 'crossref' }), 'Journal or conference');
});

test('the publication date reads as a short English date', () => {
  assert.equal(Sources.publishedLabel(TCSVT_OA), '9 Nov 2026');
  assert.equal(Sources.publishedLabel({ published: 'not a date' }), '');
  assert.equal(Sources.publishedLabel({}), '');
});

test('only http and https links are kept', () => {
  assert.equal(Sources.safeUrl('https://doi.org/10.1/x'), 'https://doi.org/10.1/x');
  assert.equal(Sources.safeUrl('javascript:alert(1)'), null);
  assert.equal(Sources.safeUrl(null), null);
});

// --- Filters and counts --------------------------------------------------------

test('the source filter keeps arXiv or one venue', () => {
  assert.deepEqual(ids({ ...base, source: 'arxiv' }), ['2611.04001', '2611.04002', '2611.04003']);
  assert.deepEqual(ids({ ...base, source: 'venue:IEEE TCSVT' }), ['doi:10.1109/tcsvt.2026.3400001', 'doi:10.1109/tcsvt.2026.3400002']);
  assert.deepEqual(ids({ ...base, source: 'venue:IEEE TCSVT', topic: 'matches' }), ['doi:10.1109/tcsvt.2026.3400001']);
});

test('papers without arXiv categories are not counted as other fields', () => {
  assert.equal(Filters.categoryOf(TCSVT_OA, MAIN), null);
  assert.deepEqual(ids({ ...base, category: 'cs.CV' }), ['2611.04001']);
  assert.deepEqual(ids({ ...base, category: 'other' }), []);
});

test('source counts apply every other active filter but their own', () => {
  const counts = Filters.counts(ENTRIES, { ...base, topic: 'matches', source: 'venue:IEEE TCSVT' }, MAIN, ['Stereo']);
  assert.equal(counts.sources.get('all'), 3);
  assert.equal(counts.sources.get('arxiv'), 1);
  assert.equal(counts.sources.get('venue:IEEE TCSVT'), 1);
  assert.equal(counts.sources.get('venue:IEEE TVCG'), 1);
  assert.equal(counts.sources.get('venue:ICLR 2027') || 0, 0);
  assert.equal(counts.topics.get('all'), 2);
  assert.equal(counts.topics.get('matches'), 1);
  assert.equal(counts.categories.get('all'), 1);
});

test('the source list is arXiv first, then venues by count, and only on a mixed day', () => {
  const counts = Filters.counts(ENTRIES, base, MAIN, ['Stereo']);
  assert.deepEqual(Filters.sourceOptions(RECORDS, counts).map(o => [o.key, o.label, o.count]), [
    ['all', 'All sources', 7],
    ['arxiv', 'arXiv', 3],
    ['venue:IEEE TCSVT', 'IEEE TCSVT', 2],
    ['venue:ICLR 2027', 'ICLR 2027', 1],
    ['venue:IEEE TVCG', 'IEEE TVCG', 1],
  ]);
  const arxivOnly = ENTRIES.filter(e => PaperData.isArxiv(e.record));
  assert.deepEqual(Filters.sourceOptions(arxivOnly.map(e => e.record), Filters.counts(arxivOnly, base, MAIN, [])), []);
});

test('a source choice counts as a refinement', () => {
  assert.equal(Filters.isRefined({ ...base, source: 'arxiv' }), true);
  assert.equal(Filters.isRefined(base), false);
});

// --- Search and matching without an abstract ---------------------------------

test('search works on papers without an abstract, including venue and DOI', () => {
  assert.deepEqual(ids({ ...base, query: 'rate control' }), ['doi:10.1109/tcsvt.2026.3400002']);
  assert.deepEqual(ids({ ...base, query: 'weak labels' }), ['openreview:AbCdEf123']);
  assert.deepEqual(ids({ ...base, query: 'tvcg' }), ['doi:10.1109/tvcg.2026.3500001']);
});

test('keyword and topic matching use title and TL;DR when there is no abstract', () => {
  assert.deepEqual(Render.matchesFor(TVCG, KEYWORDS, []).keywords, ['stereo']);
  assert.deepEqual(Render.matchesFor(TCSVT_OA, KEYWORDS, []).keywords, ['stereo', 'disparity']);
  assert.deepEqual(Render.describe(TCSVT_OA, KEYWORDS, [], TOPICS).topics, [{ name: 'Stereo', index: 0 }]);
});

// --- Links -----------------------------------------------------------------------

test('a non-arXiv paper opens its open-access copy, with the publisher page beside it', () => {
  const html = Render.links(TCSVT_OA);
  assert.match(html, /<a class="button-solid" href="https:\/\/arxiv.org\/abs\/2604.01234"[^>]*>Open the open-access copy<\/a>/);
  assert.match(html, /<a class="button-outline" href="https:\/\/doi.org\/10.1109\/tcsvt.2026.3400001"[^>]*>Publisher page<\/a>/);
  assert.doesNotMatch(html, /alphaxiv|huggingface|\/pdf\/|\/html\//);
});

test('without an open-access copy the main button opens the publisher page', () => {
  for (const primary of ['alphaxiv', 'arxiv']) {
    const html = Render.links(TCSVT_CLOSED, primary);
    assert.match(html, /<a class="button-solid" href="https:\/\/doi.org\/10.1109\/tcsvt.2026.3400002"[^>]*>Open the publisher page<\/a>/);
    assert.doesNotMatch(html, /alphaxiv|arxiv\.org/);
  }
});

test('a link that is not http or https is dropped', () => {
  const html = Render.links({ ...TCSVT_OA, oa_url: 'javascript:alert(1)' });
  assert.doesNotMatch(html, /javascript/);
  assert.match(html, /class="button-solid" href="https:\/\/doi.org\/10.1109\/tcsvt.2026.3400001"/);
});

test('arXiv papers keep the alphaXiv-or-arXiv setting', () => {
  assert.match(Render.links(ARXIV), /class="button-solid" href="https:\/\/www.alphaxiv.org\/abs\/2611.04001"/);
  assert.match(Render.links(ARXIV, 'arxiv'), /class="button-solid" href="https:\/\/arxiv.org\/abs\/2611.04001"/);
});

// --- Rows and the reader ----------------------------------------------------------

const info = paper => Render.describe(paper, KEYWORDS, [], TOPICS);

test('a row shows the venue and date where arXiv rows show categories and ID', () => {
  const html = Render.renderRow(TCSVT_CLOSED, info(TCSVT_CLOSED), false);
  assert.match(html, /<span class="row-meta is-venue"><span>IEEE TCSVT<\/span><span>8 Nov 2026<\/span><\/span>/);
  assert.doesNotMatch(html, /Summary pending/);
  assert.doesNotMatch(html.replace(/data-id="[^"]*"/, ""), /doi:10/);
  assert.match(Render.renderRow(ARXIV, info(ARXIV), false), /<span class="row-meta"><span>cs.CV, cs.GR<\/span><span>2611.04001<\/span><\/span>/);
});

test('the reader stamp shows venue and DOI when there is no arXiv ID', () => {
  assert.match(Render.renderReader(TCSVT_OA, info(TCSVT_OA), []), /reader-stamp" aria-hidden="true">IEEE TCSVT doi:10.1109\/tcsvt.2026.3400001 9 Nov 2026</);
  assert.match(Render.renderReader(ICLR, info(ICLR), []), /reader-stamp" aria-hidden="true">ICLR 2027 7 Nov 2026</);
});

test('a summarised non-arXiv paper shows its summary and points to the abstract on the publisher page', () => {
  const html = Render.renderReader(TCSVT_OA, info(TCSVT_OA), KEYWORDS);
  assert.match(html, /class="tldr"/);
  assert.match(html, /<p class="reader-meta"><span>IEEE TCSVT<\/span><span>Published 9 Nov 2026<\/span><span>DOI 10.1109\/tcsvt.2026.3400001<\/span><\/p>/);
  assert.match(html, /<p class="abstract-elsewhere">The abstract is on the <a href="https:\/\/doi.org\/10.1109\/tcsvt.2026.3400001"[^>]*>publisher's page<\/a>\.<\/p>/);
  assert.doesNotMatch(html, /Show the abstract|undefined/);
});

test('a paper with neither abstract nor summary shows title, authors, venue and link, not "pending"', () => {
  const html = Render.renderReader(TVCG, info(TVCG), KEYWORDS);
  assert.match(html, /Comfort limits for <mark class="hl">stereo<\/mark> displays in VR/);
  assert.match(html, /Sofia Rossi, Jun Tanaka/);
  assert.match(html, /<span>IEEE TVCG<\/span>/);
  assert.match(html, /Open the publisher page/);
  assert.match(html, /There is no summary of this paper\. The abstract is on the <a href="https:\/\/doi.org\/10.1109\/tvcg.2026.3500001"/);
  assert.doesNotMatch(html, /not been written yet|class="tldr"|<h3>Abstract<\/h3>|undefined/);
});

test('an arXiv paper published in a venue names it in the reader', () => {
  const p = { ...ARXIV, venue: 'IEEE TCSVT', doi: '10.1109/x' };
  assert.match(Render.renderReader(p, info(p), []), /<span>arXiv 2611.04001<\/span><span>Published in IEEE TCSVT<\/span>/);
});
