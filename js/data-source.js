/**
 * Where the page gets its data. This implementation reads the `data` branch
 * through raw.githubusercontent.com; a server or database backend only has
 * to provide the same two methods.
 *
 *   listDays()      -> { days: ['2026-10-30', ...] newest first, languages: Map(day -> ['English', ...]),
 *                        categories: crawled categories from assets/site.json, or null }
 *   loadDay(day)    -> [record]  raw papers merged with summaries (PaperData.mergeDay)
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

  function createStaticSource({ fetch: fetchImpl, url }) {
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
        const [raw, ai] = await Promise.all([
          fetchText(`data/${day}.jsonl`),
          fetchText(`data/${day}_AI_enhanced_${summaryLanguage(day)}.jsonl`, { optional: true }),
        ]);
        return PaperData.mergeDay(raw, ai).map(record => ({ ...record, date: day }));
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
  });
})(typeof self !== 'undefined' ? self : this);
