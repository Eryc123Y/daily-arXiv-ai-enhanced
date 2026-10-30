/**
 * Where the page gets its data. This implementation reads the `data` branch
 * through raw.githubusercontent.com; a server or database backend only has
 * to provide the same two methods.
 *
 *   listDays()      -> { days: ['2026-10-30', ...] newest first, languages: Map(day -> ['English', ...]) }
 *   loadDay(day)    -> [record]  raw papers merged with summaries (PaperData.mergeDay)
 */
(function (root) {
  const PREFERRED_LANGUAGES = ['English', 'Chinese'];

  async function fetchText(path) {
    try {
      const response = await fetch(DATA_CONFIG.getDataUrl(path), { cache: 'no-cache' });
      return response.ok ? await response.text() : '';
    } catch (error) {
      console.error('Fetch failed:', path, error);
      return '';
    }
  }

  function createStaticSource() {
    let languages = new Map();

    function summaryLanguage(day) {
      const available = languages.get(day) || [];
      return PREFERRED_LANGUAGES.find(l => available.includes(l)) || available[0] || PREFERRED_LANGUAGES[0];
    }

    return {
      async listDays() {
        const list = PaperData.parseFileList(await fetchText('assets/file-list.txt'));
        languages = list.languages;
        return { days: list.dates, languages };
      },
      async loadDay(day) {
        const [raw, ai] = await Promise.all([
          fetchText(`data/${day}.jsonl`),
          fetchText(`data/${day}_AI_enhanced_${summaryLanguage(day)}.jsonl`),
        ]);
        return PaperData.mergeDay(raw, ai).map(record => ({ ...record, date: day }));
      },
    };
  }

  root.DataSource = createStaticSource();
})(typeof self !== 'undefined' ? self : this);
