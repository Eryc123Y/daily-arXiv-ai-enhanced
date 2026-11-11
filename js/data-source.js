/**
 * Where the page gets its data. This implementation reads the `data` branch
 * through raw.githubusercontent.com; a server or database backend only has
 * to provide the same two methods.
 *
 *   listDays()      -> { days: ['2026-10-30', ...] newest first, languages: Map(day -> ['English', ...]),
 *                        categories: crawled categories from assets/site.json, or null,
 *                        venues: the watched venues [{name, kind, area}] from assets/venues.json, or null }
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
 * new fork, assets/site.json) read as empty on 404; assets/venues.json is
 * optional in every way (any failure means no venue grouping).
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

  /** url(path): a data-branch file. */
  function createStaticSource({ fetch: fetchImpl, url }) {
    let languages = new Map();
    const loadedDays = new Map();
    const venueLists = new Map();

    /** cache.get(key), else make() kept under key unless it rejects. */
    function remember(cache, key, make) {
      if (!cache.has(key)) {
        const promise = make();
        cache.set(key, promise);
        promise.catch(() => cache.delete(key));
      }
      return cache.get(key);
    }

    const venueNames = records => records.filter(r => !PaperData.isArxiv(r)).map(r => (typeof r.venue === 'string' && r.venue.trim()) || '');

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

    /** assets/venues.json, the watched venues; null when it is missing, unreadable or not a list. */
    async function fetchVenues() {
      try {
        const parsed = JSON.parse((await fetchText('assets/venues.json', { optional: true })) || 'null');
        return Array.isArray(parsed) ? parsed : null;
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
        const [listText, siteText, venues] = await Promise.all([
          fetchText('assets/file-list.txt', { optional: true }),
          fetchText('assets/site.json', { optional: true }),
          fetchVenues(),
        ]);
        const list = PaperData.parseFileList(listText);
        languages = list.languages;
        let categories = null;
        try {
          categories = siteText ? JSON.parse(siteText).categories || null : null;
        } catch (error) {
          console.error('Ignoring an unreadable assets/site.json:', error);
        }
        return { days: list.dates, languages, categories, venues };
      },
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
      venuePapers(day) {
        if (loadedDays.has(day)) return loadedDays.get(day).then(venueNames);
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
    fetch: (...args) => root.fetch(...args),
    url: path => root.DATA_CONFIG.getDataUrl(path),
  });
})(typeof self !== 'undefined' ? self : this);
