const test = require('node:test');
const assert = require('node:assert/strict');

global.PaperData = require('../../js/paper-data.js');
const { createStaticSource, LoadError } = require('../../js/data-source.js');

const RAW = JSON.stringify({ id: '2610.00001', title: 'T', summary: 'abstract', authors: ['A'], categories: ['cs.CV'] });
const respond = (status, body = '') => Promise.resolve({ ok: status >= 200 && status < 300, status, text: () => Promise.resolve(body) });

function source(routes) {
  const fetchImpl = path => {
    const route = Object.keys(routes).find(key => path.endsWith(key));
    const answer = route ? routes[route] : 404;
    return answer instanceof Error ? Promise.reject(answer) : respond(...[].concat(answer));
  };
  return createStaticSource({ fetch: fetchImpl, url: path => `https://example.test/${path}` });
}

test('a day without summaries yet loads its papers as pending', async () => {
  const day = await source({ 'data/2026-10-30.jsonl': [200, RAW] }).loadDay('2026-10-30');
  assert.equal(day.length, 1);
  assert.equal(day[0].pending, true);
});

test('a missing paper file is an error, not an empty day', async () => {
  await assert.rejects(source({}).loadDay('2026-10-30'), err => err instanceof LoadError && err.status === 404);
});

test('a server error or network failure is an error, not an empty day', async () => {
  await assert.rejects(source({ 'data/2026-10-30.jsonl': 500 }).loadDay('2026-10-30'), err => err instanceof LoadError && err.status === 500);
  await assert.rejects(source({ 'data/2026-10-30.jsonl': new TypeError('Failed to fetch') }).loadDay('2026-10-30'), err => err instanceof LoadError && err.status === null);
});

test('a broken summary file is an error too', async () => {
  await assert.rejects(source({ 'data/2026-10-30.jsonl': [200, RAW], '_English.jsonl': 503 }).loadDay('2026-10-30'), LoadError);
});

test('a fork with no data yet lists no days, but an unreachable list is an error', async () => {
  assert.deepEqual((await source({}).listDays()).days, []);
  await assert.rejects(source({ 'assets/file-list.txt': new TypeError('offline') }).listDays(), LoadError);
});

test('Hugging Face upvotes are attached when the day has them', async () => {
  const day = await source({ 'data/2026-10-30.jsonl': [200, RAW], 'data/2026-10-30_hf.json': [200, '{"2610.00001": 23}'] }).loadDay('2026-10-30');
  assert.equal(day[0].hf, 23);
});

test('upvotes are optional: a missing, broken or unreachable file leaves the day as it is', async () => {
  for (const answer of [404, 503, [200, '{not json'], new TypeError('offline')]) {
    const day = await source({ 'data/2026-10-30.jsonl': [200, RAW], 'data/2026-10-30_hf.json': answer }).loadDay('2026-10-30');
    assert.equal(day.length, 1);
    assert.equal(day[0].hf, undefined);
  }
});

test('the pipeline status reads the run log and tolerates it missing', async () => {
  const log = '{"date":"2026-11-02","path":"crawl","at":"2026-11-02T02:07:02+00:00","total":1,"added":1}\n';
  const status = await source({ 'logs/summary-runs.jsonl': [200, log] }).loadStatus();
  assert.equal(status.log.length, 1);
  const empty = await source({}).loadStatus();
  assert.deepEqual(empty, { log: [] });
});

const VENUES = '[{"name": "ACM TOG", "kind": "journal", "area": "Graphics and VR"}]';

test('the day list carries the watched venues from assets/venues.json', async () => {
  const listing = await source({ 'assets/file-list.txt': [200, '2026-10-30.jsonl\n'], 'assets/venues.json': [200, VENUES] }).listDays();
  assert.deepEqual(listing.venues, [{ name: 'ACM TOG', kind: 'journal', area: 'Graphics and VR' }]);
});

test('the venue list is optional: missing, broken, unreachable or not a list means none', async () => {
  for (const answer of [404, 503, [200, '{not json'], [200, '{"name": "ACM TOG"}'], new TypeError('offline')]) {
    const listing = await source({ 'assets/file-list.txt': [200, '2026-10-30.jsonl\n'], 'assets/venues.json': answer }).listDays();
    assert.deepEqual(listing.days, ['2026-10-30']);
    assert.equal(listing.venues, null);
  }
});

// --- The venue stream's counts --------------------------------------------------

const VENUE_RAW = [
  RAW,
  JSON.stringify({ id: 'doi:10.1145/1', source: 'crossref', venue: 'ACM TOG', title: 'V1', authors: [], categories: [], published: '2026-11-04' }),
  JSON.stringify({ id: 'doi:10.1145/2', source: 'crossref', venue: 'ACM TOG', title: 'V2', authors: [], categories: [], published: '2026-11-05' }),
  JSON.stringify({ id: 'openreview:x', source: 'openreview', venue: 'ICLR', title: 'V3', authors: [], categories: [] }),
].join('\n');

function counting(routes) {
  const asked = [];
  const fetchImpl = path => {
    asked.push(path.replace('https://example.test/', ''));
    const route = Object.keys(routes).find(key => path.endsWith(key));
    const answer = route ? routes[route] : 404;
    return answer instanceof Error ? Promise.reject(answer) : respond(...[].concat(answer));
  };
  return { asked, source: createStaticSource({ fetch: fetchImpl, url: path => `https://example.test/${path}` }) };
}

test('a day\'s venue papers are counted from its paper file alone, once', async () => {
  const { asked, source: s } = counting({ 'data/2026-11-11.jsonl': [200, VENUE_RAW] });
  assert.deepEqual(await s.venuePapers('2026-11-11'), ['ACM TOG', 'ACM TOG', 'ICLR']);
  assert.deepEqual(await s.venuePapers('2026-11-11'), ['ACM TOG', 'ACM TOG', 'ICLR']);
  assert.deepEqual(asked, ['data/2026-11-11.jsonl']);
});

test('a day already loaded is counted without another download, and is loaded once', async () => {
  const { asked, source: s } = counting({ 'data/2026-11-11.jsonl': [200, VENUE_RAW] });
  const day = await s.loadDay('2026-11-11');
  assert.equal(day.length, 4);
  await s.loadDay('2026-11-11');
  assert.deepEqual(await s.venuePapers('2026-11-11'), ['ACM TOG', 'ACM TOG', 'ICLR']);
  assert.equal(asked.filter(p => p === 'data/2026-11-11.jsonl').length, 1);
});

test('a failed download is not remembered, so trying again downloads again', async () => {
  let fail = true;
  const fetchImpl = path => (fail ? Promise.reject(new TypeError('offline')) : respond(path.endsWith('data/2026-11-11.jsonl') ? 200 : 404, VENUE_RAW));
  const s = createStaticSource({ fetch: fetchImpl, url: path => path });
  await assert.rejects(s.loadDay('2026-11-11'), LoadError);
  await assert.rejects(s.venuePapers('2026-11-11'), LoadError);
  fail = false;
  assert.equal((await s.loadDay('2026-11-11')).length, 4);
});
