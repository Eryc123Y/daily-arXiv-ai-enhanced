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
const TIP_PENDING = byId('doi:10.1109/tip.2026.3600001');
const TPAMI_WITH_ARXIV_ID = byId('2605.01234');

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
  assert.equal(RECORDS.length, 9);
  assert.deepEqual(RECORDS.slice(0, 2).map(r => r.id), ['2611.04001', 'doi:10.1109/tcsvt.2026.3400001']);
  assert.equal(TCSVT_OA.venue, 'IEEE TCSVT');
  assert.equal(TCSVT_OA.AI.tldr, 'Converts 2D video to stereo with a disparity-aware network.');
});

test('a non-arXiv paper without a summary is pending only when it has an abstract', () => {
  assert.equal(TCSVT_CLOSED.has_abstract, undefined);
  assert.equal(TCSVT_CLOSED.pending, false);
  assert.equal(TVCG.has_abstract, false);
  assert.equal(TVCG.pending, false);
  assert.equal(TIP_PENDING.pending, true);
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
  assert.deepEqual(Render.summaryProgress(RECORDS), { done: 5, total: 7, linkOnly: true });
  assert.deepEqual(Render.summaryProgress([TIP_PENDING, TVCG]), { done: 0, total: 1, linkOnly: true });
  assert.deepEqual(Render.summaryProgress([ARXIV, TVCG]), { done: 1, total: 1, linkOnly: false });
});

// --- Source keys and labels ----------------------------------------------------

test('each paper has a source key and label: arXiv, or its venue', () => {
  assert.equal(Sources.sourceKey(ARXIV), 'arxiv');
  assert.equal(Sources.sourceKey(TCSVT_OA), 'venue:IEEE TCSVT');
  assert.equal(Sources.sourceLabel(ARXIV), 'arXiv');
  assert.equal(Sources.sourceLabel(ICLR), 'ICLR');
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
  assert.equal(counts.sources.get('venue:ICLR') || 0, 0);
  assert.equal(counts.topics.get('all'), 2);
  assert.equal(counts.topics.get('matches'), 1);
  assert.equal(counts.categories.get('all'), 1);
});

test('the source list is arXiv first, then venues by count, and only on a mixed day', () => {
  const counts = Filters.counts(ENTRIES, base, MAIN, ['Stereo']);
  assert.deepEqual(Filters.sourceOptions(RECORDS, counts).map(o => [o.key, o.label, o.count]), [
    ['all', 'All sources', 9],
    ['arxiv', 'arXiv', 3],
    ['venue:IEEE TCSVT', 'IEEE TCSVT', 2],
    ['venue:ICLR', 'ICLR', 1],
    ['venue:IEEE TIP', 'IEEE TIP', 1],
    ['venue:IEEE TPAMI', 'IEEE TPAMI', 1],
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
  assert.match(Render.renderReader(ICLR, info(ICLR), []), /reader-stamp" aria-hidden="true">ICLR 7 Nov 2026</);
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

// --- has_abstract and a bare arXiv ID on a feed record ------------------------

test('a venue paper with an abstract and no summary yet reads as pending', () => {
  assert.match(Render.renderRow(TIP_PENDING, info(TIP_PENDING), false), /Summary pending/);
  const html = Render.renderReader(TIP_PENDING, info(TIP_PENDING), []);
  assert.match(html, /<p class="pending-note">This paper's summary has not been written yet\.<\/p>/);
  assert.match(html, /The abstract is on the <a href="https:\/\/doi.org\/10.1109\/tip.2026.3600001"/);
  assert.doesNotMatch(html, /Here is its abstract|<h3>Abstract<\/h3>|There is no summary|undefined/);
});

test('a feed record with an arXiv ID looks like a venue paper', () => {
  assert.equal(PaperData.isArxiv(TPAMI_WITH_ARXIV_ID), false);
  assert.equal(Sources.sourceKey(TPAMI_WITH_ARXIV_ID), 'venue:IEEE TPAMI');
  assert.equal(Sources.arxivId(TPAMI_WITH_ARXIV_ID), '2605.01234');
  assert.equal(Sources.arxivId(TCSVT_OA), null);
  assert.equal(Sources.arxivId(ARXIV), '2611.04001');
  assert.match(Render.renderRow(TPAMI_WITH_ARXIV_ID, info(TPAMI_WITH_ARXIV_ID), false), /row-meta is-venue"><span>IEEE TPAMI<\/span><span>6 Nov 2026/);
  assert.match(Render.renderReader(TPAMI_WITH_ARXIV_ID, info(TPAMI_WITH_ARXIV_ID), []), /reader-stamp" aria-hidden="true">IEEE TPAMI doi:10.1109\/tpami.2026.3700001 6 Nov 2026</);
});

test('a feed record with an arXiv ID adds the arXiv or alphaXiv link after the publisher', () => {
  const alpha = Render.links(TPAMI_WITH_ARXIV_ID);
  assert.match(alpha, /^<a class="button-solid" href="https:\/\/doi.org\/10.1109\/tpami.2026.3700001"[^>]*>Open the publisher page<\/a><a class="button-outline" href="https:\/\/www.alphaxiv.org\/abs\/2605.01234"[^>]*>alphaXiv<\/a>$/);
  const arxiv = Render.links(TPAMI_WITH_ARXIV_ID, 'arxiv');
  assert.match(arxiv, /<a class="button-outline" href="https:\/\/arxiv.org\/abs\/2605.01234"[^>]*>arXiv<\/a>$/);
  assert.doesNotMatch(alpha + arxiv, /\/pdf\/|\/html\//);
});

test('the progress line says the abstract may be a link when a pending paper has none here', () => {
  assert.equal(Render.progressText(5, 7), 'Summaries ready for 5 of 7. The rest show their abstract for now.');
  assert.equal(Render.progressText(5, 7, { linkOnly: true }), 'Summaries ready for 5 of 7. The rest show their abstract, or a link to it, for now.');
  assert.equal(Render.progressText(0, 2, { linkOnly: true }), 'Summaries are being written. Each paper shows its abstract, or a link to it, until its summary is ready.');
  assert.equal(Render.summaryProgress(RECORDS).linkOnly, true);
  assert.equal(Render.summaryProgress([byId('2611.04003')]).linkOnly, false);
});
