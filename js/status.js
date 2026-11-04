/**
 * The pipeline's state for a day, as one short line: whether the crawl ran,
 * how far the summaries got and which path wrote them, and whether the daily
 * report was written. Built from logs/summary-runs.jsonl on the data branch
 * and the latest run of the crawl workflow. Pure functions; loaded as the
 * global `Status`, and by node for tests.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Status = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  const PATHS = {
    'claude-code': 'local Claude',
    'local-claude': 'local Claude',
    'local-codex': 'local Codex',
    'local-antigravity': 'local Antigravity',
    api: 'API',
    'api-fallback': 'API fallback',
  };
  const REASON_CHARS = 60;

  function parseLog(text) {
    return (text || '')
      .split('\n')
      .filter(line => line.trim())
      .map(line => {
        try {
          return JSON.parse(line);
        } catch (error) {
          return null;
        }
      })
      .filter(entry => entry && entry.date && entry.path);
  }

  /** The day's latest summary run and latest report entry; `reports` says whether this site writes reports at all. */
  function dayRuns(log, day) {
    const forDay = log.filter(e => e.date === day);
    const last = list => (list.length ? list[list.length - 1] : null);
    return {
      summaries: last(forDay.filter(e => e.path !== 'report' && e.path !== 'crawl')),
      report: last(forDay.filter(e => e.path === 'report')),
      reports: log.some(e => e.path === 'report'),
    };
  }

  /** The weekday the crawl ran for, when it is later than the newest day shown: arXiv has not announced it yet. */
  function unannounced(run, day) {
    const crawled = (run.created_at || '').slice(0, 10);
    const weekday = new Date(`${crawled}T00:00:00Z`).getUTCDay();
    return crawled > day && weekday >= 1 && weekday <= 5 ? crawled : null;
  }

  function longDay(iso) {
    return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', timeZone: 'UTC' });
  }

  function crawlPart(run, day, time) {
    if (!run) return null;
    if (run.status !== 'completed') return { text: 'Crawl running', tone: 'busy' };
    const waiting = run.conclusion === 'success' && unannounced(run, day);
    if (waiting) return { text: `Checked ${time(run.updated_at)}: arXiv has not announced ${longDay(waiting)} yet`, tone: 'busy' };
    if (run.conclusion === 'success') return { text: `Crawled ${time(run.updated_at)}`, tone: 'ok' };
    return { text: `Crawl failed ${time(run.updated_at)}`, tone: 'error', href: run.html_url };
  }

  function summaryPart(entry, time) {
    if (!entry) return null;
    if (entry.path.startsWith('paused')) {
      const reason = entry.reason ? `: ${entry.reason.length > REASON_CHARS ? `${entry.reason.slice(0, REASON_CHARS - 1)}…` : entry.reason}` : '';
      return { text: `Summaries paused ${time(entry.at)}${reason}`, tone: 'warn' };
    }
    const who = PATHS[entry.path] || entry.path;
    const tone = entry.pending ? 'busy' : 'ok';
    return { text: `Summaries ${entry.done}/${entry.total}, ${who}, ${time(entry.at)}`, tone };
  }

  function reportPart(runs, newest, time) {
    if (runs.report) return { text: `Report written ${time(runs.report.at)}`, tone: 'ok' };
    return runs.reports && newest ? { text: 'Report not written yet', tone: 'busy' } : null;
  }

  /** [{text, tone: ok|busy|warn|error, href?}] for the day; the crawl only for the newest day. */
  function statusParts({ log, crawl, day, newest, time }) {
    const runs = dayRuns(log, day);
    return [newest ? crawlPart(crawl, day, time) : null, summaryPart(runs.summaries, time), reportPart(runs, newest, time)].filter(Boolean);
  }

  return { parseLog, dayRuns, statusParts };
});
