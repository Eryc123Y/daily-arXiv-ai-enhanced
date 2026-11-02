/**
 * Where the page gets its data. This implementation reads the `data` branch
 * through raw.githubusercontent.com; a server or database backend only has
 * to provide the same two methods.
 *
 *   listDays()      -> { days: ['2026-10-30', ...] newest first, languages: Map(day -> ['English', ...]),
 *                        categories: crawled categories from assets/site.json, or null }
 *   loadDay(day)    -> [record]  raw papers merged with summaries (PaperData.mergeDay),
 *                      with `hf` (Hugging Face upvotes) where data/<day>_hf.json has them
 *   loadStatus()    -> { log: [run log entries], crawl: latest crawl workflow run or null }
 *                      for the pipeline line; never rejects
 *
 * Both reject with a LoadError when a file that should be there cannot be
 * read, so a failed download is never shown as a day without papers. Files
 * that may legitimately not exist yet (a day's summaries, the day list on a
 * new fork, assets/site.json) read as empty on 404.
 */
(function (root) {
  const PREFERRED_LANGUAGES = ['English', 'Chinese'];

  class LoadError extends Error {
    /** status: the HTTP status, or null when the request never got an answer. */
    constructor(path, status) {
      super(status ? `${path} returned HTTP ${status}` : `${path} could not be reached`);
      this.name = 'LoadError';
      this.path = path;
      this.status = status;
    }
  }

  function parseLines(text) {
    return (text || '').split('\n').flatMap(line => {
      try {
        return line.trim() ? [JSON.parse(line)] : [];
      } catch (error) {
        return [];
      }
    });
  }

  /** url(path): a data-branch file; api(path): the repository on the GitHub REST API (optional). */
  function createStaticSource({ fetch: fetchImpl, url, api }) {
    let languages = new Map();

    async function fetchText(path, { optional = false } = {}) {
      let response;
      try {
        response = await fetchImpl(url(path), { cache: 'no-cache' });
      } catch (error) {
        throw new LoadError(path, null);
      }
      if (response.ok) return response.text();
      if (response.status === 404 && optional) return '';
      throw new LoadError(path, response.status);
    }

    /** Optional extras such as upvotes: any failure just means none. */
    async function fetchSignals(path) {
      try {
        const parsed = JSON.parse((await fetchText(path, { optional: true })) || '{}');
        return parsed && typeof parsed === 'object' ? parsed : {};
      } catch (error) {
        return {};
      }
    }

    async function latestCrawl() {
      if (!api) return null;
      try {
        const response = await fetchImpl(api('actions/workflows/run.yml/runs?per_page=1'), { cache: 'no-cache' });
        if (!response.ok) return null;
        const runs = JSON.parse(await response.text()).workflow_runs || [];
        return runs[0] || null;
      } catch (error) {
        return null;
      }
    }

    function summaryLanguage(day) {
      const available = languages.get(day) || [];
      return PREFERRED_LANGUAGES.find(l => available.includes(l)) || available[0] || PREFERRED_LANGUAGES[0];
    }

    return {
      async listDays() {
        const [listText, siteText] = await Promise.all([
          fetchText('assets/file-list.txt', { optional: true }),
          fetchText('assets/site.json', { optional: true }),
        ]);
        const list = PaperData.parseFileList(listText);
        languages = list.languages;
        let categories = null;
        try {
          categories = siteText ? JSON.parse(siteText).categories || null : null;
        } catch (error) {
          console.error('Ignoring an unreadable assets/site.json:', error);
        }
        return { days: list.dates, languages, categories };
      },
      async loadDay(day) {
        const [raw, ai, hf] = await Promise.all([
          fetchText(`data/${day}.jsonl`),
          fetchText(`data/${day}_AI_enhanced_${summaryLanguage(day)}.jsonl`, { optional: true }),
          fetchSignals(`data/${day}_hf.json`),
        ]);
        return PaperData.mergeDay(raw, ai).map(record => ({ ...record, date: day, ...(hf[record.id] ? { hf: hf[record.id] } : {}) }));
      },
      async loadStatus() {
        const [logText, crawl] = await Promise.all([
          fetchText('logs/summary-runs.jsonl', { optional: true }).catch(() => ''),
          latestCrawl(),
        ]);
        return { log: parseLines(logText), crawl };
      },
    };
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { createStaticSource, LoadError };
    return;
  }

  root.LoadError = LoadError;
  root.DataSource = createStaticSource({
    fetch: (...args) => root.fetch(...args),
    url: path => root.DATA_CONFIG.getDataUrl(path),
    api: path => `https://api.github.com/repos/${root.DATA_CONFIG.repoOwner}/${root.DATA_CONFIG.repoName}/${path}`,
  });
})(typeof self !== 'undefined' ? self : this);
