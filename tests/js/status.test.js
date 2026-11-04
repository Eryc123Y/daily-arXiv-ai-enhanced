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

test('the run log gives each day its latest summary run and its report', () => {
  const runs = Status.dayRuns(Status.parseLog(LOG), '2026-11-02');
  assert.equal(runs.summaries.path, 'local-claude');
  assert.equal(runs.report.path, 'report');
  assert.deepEqual(Status.dayRuns(Status.parseLog(LOG), '2026-10-29'), { summaries: null, report: null, reports: true });
});

test('a finished day reads as crawl, summaries and report done', () => {
  const crawl = { status: 'completed', conclusion: 'success', updated_at: '2026-11-02T08:07:02Z', html_url: 'https://github.com/x/runs/1' };
  const parts = Status.statusParts({ log: Status.parseLog(LOG), crawl, day: '2026-11-02', newest: true, time });
  assert.deepEqual(parts.map(p => [p.text, p.tone]), [
    ['Crawled 08:07', 'ok'],
    ['Summaries 450/450, local Claude, 13:59', 'ok'],
    ['Report written 14:10', 'ok'],
  ]);
});

test('a paused day says why, and a failed crawl links its run', () => {
  const paused = Status.parseLog(LOG.split('\n')[0]);
  const crawl = { status: 'completed', conclusion: 'failure', updated_at: '2026-11-03T01:20:00Z', html_url: 'https://github.com/x/runs/2' };
  const parts = Status.statusParts({ log: paused, crawl, day: '2026-11-02', newest: true, time });
  assert.deepEqual(parts[0], { text: 'Crawl failed 01:20', tone: 'error', href: 'https://github.com/x/runs/2' });
  assert.equal(parts[1].tone, 'warn');
  assert.match(parts[1].text, /^Summaries paused 08:44: 5h 15%, weekly 96%/);
});

test('older days skip the crawl, and sites without reports never mention them', () => {
  const log = Status.parseLog(LOG.split('\n').slice(3).join('\n'));
  const parts = Status.statusParts({ log, crawl: null, day: '2026-10-30', newest: false, time });
  assert.deepEqual(parts.map(p => p.text), ['Summaries 910/910, local Claude, 11:42']);
  const withReports = Status.parseLog(LOG);
  assert.deepEqual(Status.statusParts({ log: withReports, crawl: null, day: '2026-10-30', newest: false, time }).map(p => p.text), ['Summaries 910/910, local Claude, 11:42']);
});

test('a running crawl and a day still waiting for its report say so', () => {
  const log = Status.parseLog(LOG.split('\n').slice(0, 2).concat(LOG.split('\n')[3]).join('\n') + '\n' + JSON.stringify({ date: '2026-10-30', path: 'report', at: '2026-10-30T12:00:00+00:00' }));
  const parts = Status.statusParts({ log, crawl: { status: 'in_progress', conclusion: null }, day: '2026-11-02', newest: true, time });
  assert.deepEqual(parts.map(p => p.text), ['Crawl running', 'Summaries 450/450, local Claude, 13:59', 'Report not written yet']);
});

test('the crawl entry is not mistaken for a summary run', () => {
  const log = Status.parseLog(LOG + '\n' + JSON.stringify({ date: '2026-11-02', path: 'crawl', at: '2026-11-02T15:00:00+00:00', total: 450, added: 450 }));
  assert.equal(Status.dayRuns(log, '2026-11-02').summaries.path, 'local-claude');
});

test('a crawl on a later weekday that found nothing says arXiv has not announced yet', () => {
  const crawl = { status: 'completed', conclusion: 'success', created_at: '2026-11-03T02:34:14Z', updated_at: '2026-11-03T02:35:00Z' };
  const parts = Status.statusParts({ log: Status.parseLog(LOG), crawl, day: '2026-11-02', newest: true, time });
  assert.deepEqual(parts[0], { text: 'Checked 02:35: arXiv has not announced 3 November yet', tone: 'busy' });
  const saturday = { ...crawl, created_at: '2026-11-07T02:34:14Z', updated_at: '2026-11-07T02:35:00Z' };
  assert.equal(Status.statusParts({ log: Status.parseLog(LOG), crawl: saturday, day: '2026-11-06', newest: true, time })[0].text, 'Crawled 02:35');
});

test('broken log lines are skipped', () => {
  assert.equal(Status.parseLog('{not json\n' + LOG).length, 4);
});
