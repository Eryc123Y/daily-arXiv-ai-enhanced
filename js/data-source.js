/**
 * Where the page gets its data. This implementation reads the `data` branch
 * through raw.githubusercontent.com; a server or database backend only has
 * to provide the same two methods.
 *
 *   listDays()      -> { days: ['2026-10-30', ...] newest first, languages: Map(day -> ['English', ...]),
 *                        categories: crawled categories from assets/site.json, or null,
 *                        venues: the watched venues [{name, kind, area}] from assets/venues.json, or null,
 *                        venueDays: Map(day -> journal and conference papers that day) from
 *                        assets/venue-days.json, or null when the branch has none (the page then counts) }
 *   loadDay(day)    -> [record]  raw papers merged with summaries (PaperData.mergeDay),
 *                      with `hf` (Hugging Face upvotes) where data/<day>_hf.json has them
 *   venuePapers(day) -> the venue of each journal or conference paper in the day's
 *                      file (['ACM TOG', 'ACM TOG', 'ICLR']), for the weekly stream's
 *                      counts; reads only data/<day>.jsonl, or the day already loaded
 *   loadStatus()    -> { log: [run log entries] } (crawl, summary and report runs)
 *                      for the pipeline line; never rejects
 *
 * Days and counts are kept for the page's lifetime, so switching streams or
 * weeks does not download a day twice; a failed download is not kept.
 *
 * Both reject with a LoadError when a file that should be there cannot be
 * read, so a failed download is never shown as a day without papers. Files
 * that may legitimately not exist yet (a day's summaries, the day list on a
 * new fork, assets/site.json) read as empty on 404; assets/venues.json and
 * assets/venue-days.json are optional in every way (any failure means no
 * venue grouping, and counting venue papers from the day files).
 */
(function (root) {
  const PREFERRED_LANGUAGES = ['English', 'Chinese'];

  class LoadError extends Error {
    /**
     * status: the HTTP status, or null when the request never got an answer.
     * @param {string} path
     * @param {number | null} status
     */
    constructor(path, status) {
      super(status ? `${path} returned HTTP ${status}` : `${path} could not be reached`);
      this.name = 'LoadError';
      this.path = path;
      this.status = status;
    }
  }

  /**
   * @param {string | null | undefined} text
   * @returns {any[]}
   */
  function parseLines(text) {
    return (text || '').split('\n').flatMap(line => {
      try {
        return line.trim() ? [JSON.parse(line)] : [];
      } catch (error) {
        return [];
      }
    });
  }

  /**
   * url(path): a data-branch file.
   * @param {{
   *   fetch: (url: string, init: RequestInit) => Promise<{ ok: boolean, status: number, text(): Promise<string> }>,
   *   url: (path: string) => string,
   * }} options
   */
  function createStaticSource({ fetch: fetchImpl, url }) {
    /** @type {Map<string, string[]>} */
    let languages = new Map();
    /** @type {Map<string, Promise<PageRecord[]>>} */
    const loadedDays = new Map();
    /** @type {Map<string, Promise<string[]>>} */
    const venueLists = new Map();

    /**
     * cache.get(key), else make() kept under key unless it rejects.
     * @template T
     * @param {Map<string, Promise<T>>} cache
     * @param {string} key
     * @param {() => Promise<T>} make
     * @returns {Promise<T>}
     */
    function remember(cache, key, make) {
      if (!cache.has(key)) {
        const promise = make();
        cache.set(key, promise);
        promise.catch(() => cache.delete(key));
      }
      return /** @type {Promise<T>} */ (cache.get(key));
    }

    /** @param {AnyRecord[]} records */
    const venueNames = records => records.flatMap(r => (PaperData.isArxiv(r) ? [] : [(typeof r.venue === 'string' && r.venue.trim()) || '']));

    /**
     * @param {string} path
     * @param {{ optional?: boolean }} [options]
     * @returns {Promise<string>}
     */
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

    /**
     * Optional extras such as upvotes: any failure just means none.
     * @param {string} path
     * @returns {Promise<Record<string, number>>}
     */
    async function fetchSignals(path) {
      try {
        const parsed = JSON.parse((await fetchText(path, { optional: true })) || '{}');
        return parsed && typeof parsed === 'object' ? parsed : {};
      } catch (error) {
        return {};
      }
    }

    /**
     * assets/venues.json, the watched venues; null when it is missing, unreadable or not a list.
     * @returns {Promise<unknown[] | null>}
     */
    async function fetchVenues() {
      try {
        const parsed = JSON.parse((await fetchText('assets/venues.json', { optional: true })) || 'null');
        return Array.isArray(parsed) ? parsed : null;
      } catch (error) {
        return null;
      }
    }

    /**
     * assets/venue-days.json as a Map; null unless it is a {day: positive whole number} object.
     * @returns {Promise<Map<string, number> | null>}
     */
    async function fetchVenueDays() {
      try {
        const parsed = JSON.parse((await fetchText('assets/venue-days.json', { optional: true })) || 'null');
        const entries = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? Object.entries(parsed) : null;
        const valid = entries && entries.every(([day, n]) => /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isInteger(n) && n > 0);
        return valid ? new Map(/** @type {[string, number][]} */ (entries)) : null;
      } catch (error) {
        return null;
      }
    }

    /** @param {string} day */
    function summaryLanguage(day) {
      const available = languages.get(day) || [];
      return PREFERRED_LANGUAGES.find(l => available.includes(l)) || available[0] || PREFERRED_LANGUAGES[0];
    }

    return {
      async listDays() {
        const [listText, siteText, venues, venueDays] = await Promise.all([
          fetchText('assets/file-list.txt', { optional: true }),
          fetchText('assets/site.json', { optional: true }),
          fetchVenues(),
          fetchVenueDays(),
        ]);
        const list = PaperData.parseFileList(listText);
        languages = list.languages;
        /** @type {string[] | null} */
        let categories = null;
        try {
          categories = siteText ? JSON.parse(siteText).categories || null : null;
        } catch (error) {
          console.error('Ignoring an unreadable assets/site.json:', error);
        }
        return { days: list.dates, languages, categories, venues, venueDays };
      },
      /**
       * @param {string} day
       * @returns {Promise<PageRecord[]>}
       */
      loadDay(day) {
        return remember(loadedDays, day, async () => {
          const [raw, ai, hf] = await Promise.all([
            fetchText(`data/${day}.jsonl`),
            fetchText(`data/${day}_AI_enhanced_${summaryLanguage(day)}.jsonl`, { optional: true }),
            fetchSignals(`data/${day}_hf.json`),
          ]);
          return PaperData.mergeDay(raw, ai).map(record => ({ ...record, date: day, ...(hf[record.id] ? { hf: hf[record.id] } : {}) }));
        });
      },
      /**
       * @param {string} day
       * @returns {Promise<string[]>}
       */
      venuePapers(day) {
        const loaded = loadedDays.get(day);
        if (loaded) return loaded.then(venueNames);
        return remember(venueLists, day, async () => venueNames(PaperData.parseJsonl(await fetchText(`data/${day}.jsonl`))));
      },
      async loadStatus() {
        const logText = await fetchText('logs/summary-runs.jsonl', { optional: true }).catch(() => '');
        return { log: parseLines(logText) };
      },
    };
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { createStaticSource, LoadError };
    return;
  }

  root.LoadError = LoadError;
  root.DataSource = createStaticSource({
    fetch: /** @type {typeof fetch} */ ((...args) => root.fetch(...args)),
    url: /** @param {string} path */ path => root.DATA_CONFIG.getDataUrl(path),
  });
})(typeof self !== 'undefined' ? self : this);
