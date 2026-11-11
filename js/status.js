/**
 * The pipeline's state for a day, as one short line: whether the crawl ran,
 * how far the summaries got and which path wrote them, and whether the daily
 * report was written. Built from logs/summary-runs.jsonl on the data branch,
 * where the crawl logs a "crawl" entry. Pure functions; loaded as the
 * global `Status`, and by node for tests.
 */
/**
 * One line of logs/summary-runs.jsonl (summaries/datafiles.py record_run and
 * the crawl's entry).
 * @typedef {object} RunLogEntry
 * @property {string} date       the day the run was for
 * @property {string} path       'crawl', 'report', 'paused…', or who wrote the summaries ('local-claude', 'api', ...)
 * @property {string} at         when it ran (ISO time)
 * @property {string} [reason]
 * @property {number} [total]
 * @property {number} [done]
 * @property {number} [pending]
 */

/**
 * A piece of the pipeline line.
 * @typedef {{ text: string, tone: 'ok' | 'busy' | 'warn' | 'error', href?: string }} StatusPart
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Status = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  /** @type {Partial<Record<string, string>>} */
  const PATHS = {
    'claude-code': 'local Claude',
    'local-claude': 'local Claude',
    'local-codex': 'local Codex',
    'local-antigravity': 'local Antigravity',
    api: 'API',
    'api-fallback': 'API fallback',
  };
  const REASON_CHARS = 60;

  /**
   * @param {string | null | undefined} text
   * @returns {RunLogEntry[]}
   */
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

  /** The day's latest crawl, summary run and report entries; `reports` says whether this site writes reports at all. */
  /**
   * @param {RunLogEntry[]} log
   * @param {string} day
   */
  function dayRuns(log, day) {
    const forDay = log.filter(e => e.date === day);
    /** @param {RunLogEntry[]} list */
    const last = list => (list.length ? list[list.length - 1] : null);
    return {
      crawl: last(forDay.filter(e => e.path === 'crawl')),
      summaries: last(forDay.filter(e => e.path !== 'report' && e.path !== 'crawl')),
      report: last(forDay.filter(e => e.path === 'report')),
      reports: log.some(e => e.path === 'report'),
    };
  }

  /** @typedef {(at: string) => string} TimeFormat */

  /**
   * @param {RunLogEntry | null} entry
   * @param {TimeFormat} time
   * @returns {StatusPart | null}
   */
  function crawlPart(entry, time) {
    return entry ? { text: `Crawled ${time(entry.at)}`, tone: 'ok' } : null;
  }

  /**
   * @param {RunLogEntry | null} entry
   * @param {TimeFormat} time
   * @returns {StatusPart | null}
   */
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

  /**
   * @param {ReturnType<typeof dayRuns>} runs
   * @param {boolean} newest
   * @param {TimeFormat} time
   * @returns {StatusPart | null}
   */
  function reportPart(runs, newest, time) {
    if (runs.report) return { text: `Report written ${time(runs.report.at)}`, tone: 'ok' };
    return runs.reports && newest ? { text: 'Report not written yet', tone: 'busy' } : null;
  }

  /**
   * [{text, tone: ok|busy|warn|error, href?}] for the day; the crawl only for the newest day.
   * @param {{ log: RunLogEntry[], day: string, newest: boolean, time: TimeFormat }} options
   * @returns {StatusPart[]}
   */
  function statusParts({ log, day, newest, time }) {
    const runs = dayRuns(log, day);
    return [newest ? crawlPart(runs.crawl, time) : null, summaryPart(runs.summaries, time), reportPart(runs, newest, time)]
      .filter(/** @returns {part is StatusPart} */ part => Boolean(part));
  }

  return { parseLog, dayRuns, statusParts };
});
