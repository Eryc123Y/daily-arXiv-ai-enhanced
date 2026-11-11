// The two streams: arXiv by day, journals and conferences by ISO week.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const PaperData = require('../../js/paper-data.js');
const Sources = require('../../js/sources.js');
const Render = require('../../js/render.js');
const Filters = require('../../js/filters.js');
const Streams = require('../../js/streams.js');

const FIXTURE = path.join(__dirname, 'fixtures', 'mixed-day');
const read = name => fs.readFileSync(path.join(FIXTURE, name), 'utf8');
const RECORDS = PaperData.mergeDay(read('data/2026-11-10.jsonl'), read('data/2026-11-10_AI_enhanced_English.jsonl'));
const VENUES = Sources.venueIndex(JSON.parse(read('assets/venues.json')));
const MAIN = ['cs.CV', 'cs.AI', 'cs.LG', 'cs.CL', 'stat.ML', 'cs.GR'];
const TOPICS = [{ name: 'Stereo', keywords: ['stereo', 'disparity'] }];
const entriesOf = records => records.map((record, index) => ({ record, index, info: Render.describe(record, ['stereo', 'disparity'], [], TOPICS) }));
const base = { topic: 'all', category: 'all', codeOnly: false, freeOnly: false, type: 'all', area: 'all', source: 'all', query: '' };

// --- Weeks ------------------------------------------------------------------------

test('a week starts on Monday, and Sunday belongs to the week before it', () => {
  assert.equal(Streams.weekOf('2026-11-09'), '2026-11-09'); // Monday
  assert.equal(Streams.weekOf('2026-11-11'), '2026-11-09');
  assert.equal(Streams.weekOf('2026-11-14'), '2026-11-09'); // Saturday
  assert.equal(Streams.weekOf('2026-11-15'), '2026-11-09'); // Sunday
  assert.equal(Streams.weekOf('2026-11-16'), '2026-11-16');
  assert.equal(Streams.weekOf('2027-01-01'), '2026-12-28'); // across the year
});

test('a week has seven days, and the day list gives the ones with files', () => {
  assert.deepEqual(Streams.weekDays('2026-11-09'), [
    '2026-11-09', '2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13', '2026-11-14', '2026-11-15',
  ]);
  const days = ['2026-11-16', '2026-11-15', '2026-11-11', '2026-11-09', '2026-11-06'];
  assert.deepEqual(Streams.daysInWeek('2026-11-09', days), ['2026-11-09', '2026-11-11', '2026-11-15']);
});

test('weeks with venue papers, newest first, counting weekend files and skipping empty weeks', () => {
  const perDay = new Map([
    ['2026-11-02', 0], ['2026-11-06', 0],
    ['2026-11-09', 4], ['2026-11-11', 187], ['2026-11-15', 3], // Sunday's file is in the week of 9 Nov
    ['2026-11-16', 2], ['not-a-day', 9],
  ]);
  assert.deepEqual([...Streams.venueWeeks(perDay)], [['2026-11-16', 2], ['2026-11-09', 194]]);
  assert.equal(Streams.venueWeeks(new Map()).size, 0);
  assert.equal(Streams.venueWeeks(null).size, 0);
});

test('week labels', () => {
  assert.equal(Streams.weekRange('2026-11-09'), '9–15 Nov 2026');
  assert.equal(Streams.weekRange('2026-11-30'), '30 Nov – 6 Dec 2026');
  assert.equal(Streams.weekRange('2026-12-28'), '28 Dec 2026 – 3 Jan 2027');
  assert.equal(Streams.weekLabel('2026-11-09'), 'Week of 9 Nov 2026');
  assert.equal(Streams.weekSummary(187, 8), '187 papers from 8 venues');
  assert.equal(Streams.weekSummary(1, 1), '1 paper from 1 venue');
});

// --- Which papers each stream shows ------------------------------------------------

test('the arXiv stream shows only arXiv papers, the venue stream only the rest', () => {
  const arxiv = Streams.streamRecords(RECORDS, Streams.ARXIV);
  const venues = Streams.streamRecords(RECORDS, Streams.VENUES);
  assert.deepEqual(arxiv.map(r => r.id), ['2611.04001', '2611.04002', '2611.04003']);
  assert.equal(venues.length, RECORDS.length - 3);
  assert.ok(venues.every(r => !PaperData.isArxiv(r)));
});

test('on an arXiv-only day the arXiv stream is the whole day, and its filters look as before', () => {
  const arxivOnly = RECORDS.filter(r => PaperData.isArxiv(r));
  assert.deepEqual(Streams.streamRecords(arxivOnly, Streams.ARXIV), arxivOnly);
  assert.equal(Filters.sourceGroups(arxivOnly, Filters.counts(entriesOf(arxivOnly), base, MAIN, [], VENUES), base, VENUES), null);
  assert.equal(Filters.hasVenuePapers(arxivOnly), false);
});

test('on a mixed day the arXiv stream has the same counts as an arXiv-only day', () => {
  const shown = Streams.streamRecords(RECORDS, Streams.ARXIV);
  const counts = Filters.counts(entriesOf(shown), base, MAIN, ['Stereo'], VENUES);
  assert.equal(counts.topics.get('all'), 3);
  assert.equal(counts.categories.get('all'), 3);
  assert.equal(Filters.hasVenuePapers(shown), false); // so no Free to read chip and no Source section
});

test('the line under an arXiv day names the week\'s venue papers', () => {
  assert.equal(Streams.weekNote(187, ['journal']), '+ 187 journal papers this week');
  assert.equal(Streams.weekNote(1, ['journal']), '+ 1 journal paper this week');
  assert.equal(Streams.weekNote(4, ['conference']), '+ 4 conference papers this week');
  assert.equal(Streams.weekNote(9, ['journal', 'conference', null]), '+ 9 journal and conference papers this week');
  assert.equal(Streams.weekNote(2, [null]), '+ 2 journal papers this week');
  assert.equal(Streams.weekNote(0, []), '');
});

// --- Venue groups -----------------------------------------------------------------

test('the weekly list is grouped by venue, most papers first, newest paper first in each', () => {
  const venueEntries = entriesOf(Streams.streamRecords(RECORDS, Streams.VENUES));
  const groups = Streams.venueGroups(venueEntries, VENUES);
  assert.deepEqual(groups.map(g => [g.label, g.entries.length]), [
    ['IEEE TCSVT', 2], ['ICLR', 1], ['IEEE TIP', 1], ['IEEE TPAMI', 1], ['IEEE TVCG', 1],
  ]);
  const tcsvt = groups[0];
  assert.equal(tcsvt.key, 'venue:IEEE TCSVT');
  assert.equal(tcsvt.kind, 'journal');
  assert.equal(tcsvt.area, 'ML and vision');
  const published = tcsvt.entries.map(e => e.record.published);
  assert.deepEqual(published, [...published].sort().reverse());
  assert.equal(groups.find(g => g.label === 'IEEE TPAMI').kind, null); // not on the watch list
});

test('papers without a publication date go last in their venue, in file order', () => {
  const records = [
    { id: 'a', source: 'crossref', venue: 'ACM TOG', published: '2026-11-04' },
    { id: 'b', source: 'crossref', venue: 'ACM TOG' },
    { id: 'c', source: 'crossref', venue: 'ACM TOG', published: '2026-11-10' },
    { id: 'd', source: 'crossref', venue: 'ACM TOG' },
  ];
  const groups = Streams.venueGroups(records.map((record, index) => ({ record, index })), VENUES);
  assert.deepEqual(groups[0].entries.map(e => e.record.id), ['c', 'a', 'b', 'd']);
});

test('filters and counts in the venue stream cover only venue papers', () => {
  const shown = Streams.streamRecords(RECORDS, Streams.VENUES);
  const entries = entriesOf(shown);
  const counts = Filters.counts(entries, base, MAIN, ['Stereo'], VENUES);
  assert.equal(counts.topics.get('all'), shown.length);
  assert.equal(counts.types.get('arxiv'), 0);
  assert.equal(counts.types.get('journal'), 4);
  const groups = Filters.sourceGroups(shown, counts, base, VENUES);
  assert.deepEqual(groups.types.map(o => o.key), ['all', 'conference', 'journal']); // no arXiv preprints chip
  const journals = Filters.apply(entries, { ...base, type: 'journal' }, MAIN, VENUES);
  assert.equal(journals.length, 4);
  const tvcg = Filters.apply(entries, { ...base, source: 'venue:IEEE TVCG' }, MAIN, VENUES);
  assert.deepEqual(Streams.venueGroups(tvcg, VENUES).map(g => g.label), ['IEEE TVCG']);
});

test('the venue stream\'s progress counts only venue papers that can get a summary', () => {
  const shown = Streams.streamRecords(RECORDS, Streams.VENUES);
  const progress = Render.summaryProgress(shown);
  const canGet = shown.filter(r => r.pending || PaperData.hasSummary(r)).length;
  assert.equal(progress.total, canGet);
  assert.ok(progress.total < shown.length); // some venue papers will never get one
});

test('an empty week has no groups', () => {
  assert.deepEqual(Streams.venueGroups([], VENUES), []);
  assert.equal(Streams.weekSummary(0, 0), '0 papers from 0 venues');
});

// --- URL state --------------------------------------------------------------------

const WEEKS = new Map([['2026-11-16', 2], ['2026-11-09', 194]]);
const params = text => new URLSearchParams(text);

test('the URL picks the stream and week', () => {
  assert.deepEqual(Streams.readStream(params('day=2026-11-11'), WEEKS), { stream: 'arxiv', week: null });
  assert.deepEqual(Streams.readStream(params('stream=venues&week=2026-11-09'), WEEKS), { stream: 'venues', week: '2026-11-09' });
  assert.deepEqual(Streams.readStream(params('stream=venues&week=2026-11-11'), WEEKS), { stream: 'venues', week: '2026-11-09' });
});

test('a missing or unknown week is the newest one; no venue weeks means the arXiv stream', () => {
  assert.deepEqual(Streams.readStream(params('stream=venues'), WEEKS), { stream: 'venues', week: '2026-11-16' });
  assert.deepEqual(Streams.readStream(params('stream=venues&week=2026-10-05'), WEEKS), { stream: 'venues', week: '2026-11-16' });
  assert.deepEqual(Streams.readStream(params('stream=venues&week=nonsense'), WEEKS), { stream: 'venues', week: '2026-11-16' });
  assert.deepEqual(Streams.readStream(params('stream=venues&week=2026-11-09'), new Map()), { stream: 'arxiv', week: null });
});

// --- Wording and HTML -------------------------------------------------------------

test('the sentence under the week', () => {
  assert.equal(Streams.weekSentence(187, 8, 3, true), '187 papers from 8 venues, 3 matching your interests.');
  assert.equal(Streams.weekSentence(187, 8, 0, true), '187 papers from 8 venues, none matching your interests.');
  assert.equal(Streams.weekSentence(1, 1, 0, false), '1 paper from 1 venue.');
});

test('a venue group header names the venue, quietly its kind and area, and its count', () => {
  const html = Render.groupHead({ key: 'venue:ACM TOG', label: 'ACM TOG', kind: 'journal', area: 'Graphics and VR', entries: [1, 2, 3] });
  assert.match(html, /<h3[^>]*>ACM TOG<\/h3>/);
  assert.match(html, /Journal · Graphics and VR/);
  assert.match(html, /<span class="count">3<\/span>/);
  const unwatched = Render.groupHead({ key: 'venue:<b>', label: '<b>', kind: null, area: null, entries: [1] });
  assert.match(unwatched, /&lt;b&gt;/);
  assert.doesNotMatch(unwatched, /group-meta/);
});
