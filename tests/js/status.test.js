const test = require('node:test');
const assert = require('node:assert/strict');

const Status = require('../../js/status.js');

const LOG = [
  { date: '2026-11-02', path: 'paused-no-key', at: '2026-11-02T08:44:28+00:00', total: 450, done: 0, pending: 450, reason: '5h 15%, weekly 96%; the ANTHROPIC_API_KEY secret is not set' },
  { date: '2026-11-02', path: 'local-claude', at: '2026-11-02T13:59:36+00:00', total: 450, done: 450, pending: 0 },
  { date: '2026-11-02', path: 'report', at: '2026-11-02T14:10:00+00:00', total: 450, done: 450, pending: 0 },
  { date: '2026-10-30', path: 'claude-code', at: '2026-10-30T11:42:32+00:00', total: 910, done: 910, pending: 0 },
].map(e => JSON.stringify(e)).join('\n');
const time = iso => iso.slice(11, 16);

const CRAWL = JSON.stringify({ date: '2026-11-02', path: 'crawl', at: '2026-11-02T08:07:02+00:00', total: 450, added: 450 });

test('the run log gives each day its crawl, latest summary run and report', () => {
  const runs = Status.dayRuns(Status.parseLog(LOG + '\n' + CRAWL), '2026-11-02');
  assert.equal(runs.crawl.path, 'crawl');
  assert.equal(runs.summaries.path, 'local-claude');
  assert.equal(runs.report.path, 'report');
  assert.deepEqual(Status.dayRuns(Status.parseLog(LOG), '2026-10-29'), { crawl: null, summaries: null, report: null, reports: true });
});

test('a finished day reads as crawl, summaries and report done', () => {
  const parts = Status.statusParts({ log: Status.parseLog(LOG + '\n' + CRAWL), day: '2026-11-02', newest: true, time });
  assert.deepEqual(parts.map(p => [p.text, p.tone]), [
    ['Crawled 08:07', 'ok'],
    ['Summaries 450/450, local Claude, 13:59', 'ok'],
    ['Report written 14:10', 'ok'],
  ]);
});

test('a paused day says why', () => {
  const parts = Status.statusParts({ log: Status.parseLog(LOG.split('\n')[0]), day: '2026-11-02', newest: true, time });
  assert.equal(parts[0].tone, 'warn');
  assert.match(parts[0].text, /^Summaries paused 08:44: 5h 15%, weekly 96%/);
});

test('older days skip the crawl, and sites without reports never mention them', () => {
  const log = Status.parseLog(LOG.split('\n').slice(3).join('\n') + '\n' + JSON.stringify({ date: '2026-10-30', path: 'crawl', at: '2026-10-30T02:00:00+00:00' }));
  const parts = Status.statusParts({ log, day: '2026-10-30', newest: false, time });
  assert.deepEqual(parts.map(p => p.text), ['Summaries 910/910, local Claude, 11:42']);
  const withReports = Status.parseLog(LOG);
  assert.deepEqual(Status.statusParts({ log: withReports, day: '2026-10-30', newest: false, time }).map(p => p.text), ['Summaries 910/910, local Claude, 11:42']);
});

test('a day still waiting for its report says so', () => {
  const log = Status.parseLog(LOG.split('\n').slice(0, 2).concat(LOG.split('\n')[3]).join('\n') + '\n' + JSON.stringify({ date: '2026-10-30', path: 'report', at: '2026-10-30T12:00:00+00:00' }));
  const parts = Status.statusParts({ log, day: '2026-11-02', newest: true, time });
  assert.deepEqual(parts.map(p => p.text), ['Summaries 450/450, local Claude, 13:59', 'Report not written yet']);
});

test('the crawl entry is not mistaken for a summary run', () => {
  const log = Status.parseLog(LOG + '\n' + JSON.stringify({ date: '2026-11-02', path: 'crawl', at: '2026-11-02T15:00:00+00:00', total: 450, added: 450 }));
  assert.equal(Status.dayRuns(log, '2026-11-02').summaries.path, 'local-claude');
});

test('broken log lines are skipped', () => {
  assert.equal(Status.parseLog('{not json\n' + LOG).length, 4);
});

test('the summaries part says when the count is, or includes, journal and conference papers', () => {
  const log = Status.parseLog(JSON.stringify({ date: '2026-11-12', path: 'local-claude', at: '2026-11-12T02:40:53+00:00', total: 30, done: 30, pending: 0 }));
  const text = papers => Status.statusParts({ log, day: '2026-11-12', newest: false, time, papers }).map(p => p.text);
  assert.deepEqual(text({ arxiv: 0, venue: 30 }), ['Summaries 30/30 (journal and conference papers; no arXiv papers this day), local Claude, 02:40']);
  assert.deepEqual(text({ arxiv: 500, venue: 30 }), ['Summaries 30/30 (incl. journals and conferences), local Claude, 02:40']);
  assert.deepEqual(text({ arxiv: 500, venue: 0 }), ['Summaries 30/30, local Claude, 02:40']);
  assert.deepEqual(text(undefined), ['Summaries 30/30, local Claude, 02:40']);
});
