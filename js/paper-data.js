/**
 * Pure helpers for the paper list: which dates exist, merging a day's raw
 * crawl with its summaries, and keyword matching. Loaded in the browser as
 * the global `PaperData`, and by node for tests.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.PaperData = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  /** @type {Array<keyof AiSummary>} */
  const AI_FIELDS = ['tldr', 'motivation', 'method', 'result', 'conclusion'];
  const RAW_FILE = /^(\d{4}-\d{2}-\d{2})\.jsonl$/;
  const AI_FILE = /^(\d{4}-\d{2}-\d{2})_AI_enhanced_([A-Za-z]+)\.jsonl$/;
  const SEPARATOR = '[\\s\\-\\u2010-\\u2014_/]+';

  /**
   * arXiv records carry no `source`; every other source names itself.
   * @template {{ source?: string }} R
   * @param {R | null | undefined} record
   * @returns {record is Extract<R, ArxivRecord>}
   */
  function isArxiv(record) {
    return !!record && (!record.source || record.source === 'arxiv');
  }

  /**
   * @param {object | null | undefined} record
   * @returns {boolean}
   */
  function hasSummary(record) {
    const ai = record && /** @type {{ AI?: Partial<AiSummary> }} */ (record).AI;
    return Boolean(ai) &&
      AI_FIELDS.every(f => { const v = ai && ai[f]; return typeof v === 'string' && v.trim() !== ''; });
  }

  /**
   * The records in a JSONL file; lines that are not records are skipped.
   * @param {string | null | undefined} text
   * @returns {RawRecord[]}
   */
  function parseJsonl(text) {
    /** @type {RawRecord[]} */
    const records = [];
    (text || '').split('\n').forEach(line => {
      if (!line.trim()) return;
      try {
        const record = JSON.parse(line);
        if (record && record.id) records.push(record);
      } catch (error) {
        // Not a record (for example a "404: Not Found" body); skip it.
      }
    });
    return records;
  }

  /**
   * Dates (newest first) and, per date, the summary languages available.
   * @param {string | null | undefined} text
   */
  function parseFileList(text) {
    /** @type {Map<string, string[]>} */
    const languages = new Map();
    /** @type {Set<string>} */
    const rawDates = new Set();
    (text || '').split('\n').map(s => s.trim()).forEach(name => {
      const raw = name.match(RAW_FILE);
      const ai = name.match(AI_FILE);
      const date = raw ? raw[1] : ai ? ai[1] : null;
      if (!date) return;
      if (!languages.has(date)) languages.set(date, []);
      if (raw) rawDates.add(date);
      const dayLanguages = languages.get(date) || [];
      if (ai && !dayLanguages.includes(ai[2])) dayLanguages.push(ai[2]);
    });
    const dates = [...languages.keys()].sort().reverse();
    return { dates, languages, rawDates };
  }

  /**
   * One day's records: the raw crawl decides which papers exist and their
   * order; a paper with a complete summary uses the summary record (over the
   * raw fields it does not repeat), any other arXiv paper is marked
   * `pending`. A paper from another source without a summary is pending only
   * when the pipeline has its abstract (`has_abstract: true`); otherwise it
   * will never get one. Summary records
   * without a raw entry (older days) are kept.
   * @param {string | null | undefined} rawText
   * @param {string | null | undefined} aiText
   * @returns {PageRecord[]}
   */
  function mergeDay(rawText, aiText) {
    /** @type {Map<string, SummaryRecord>} */
    const summaries = new Map();
    parseJsonl(aiText).forEach(r => {
      if (hasSummary(r) && !summaries.has(r.id)) summaries.set(r.id, /** @type {SummaryRecord} */ (r));
    });
    /** @type {Set<string>} */
    const seen = new Set();
    /** @type {PageRecord[]} */
    const records = [];
    parseJsonl(rawText).forEach(r => {
      if (seen.has(r.id)) return;
      seen.add(r.id);
      const summary = summaries.get(r.id);
      records.push(summary ? /** @type {PageRecord} */ ({ ...r, ...summary, pending: false }) : { ...r, pending: isArxiv(r) || r.has_abstract === true });
    });
    summaries.forEach((r, id) => {
      if (!seen.has(id)) records.push({ ...r, pending: false });
    });
    return records;
  }

  /** @param {string} text */
  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /**
   * A one-word keyword with a capital first letter and a lowercase letter
   * after it ("Lean", "BabyLM") is a name and keeps its case.
   * @param {string[]} words
   */
  function isName(words) {
    return words.length === 1 && /^\p{Lu}/u.test(words[0]) && /\p{Ll}/u.test(words[0].slice(1));
  }

  /**
   * `text` as a pattern that matches it in any case, one character class per cased letter.
   * @param {string} text
   */
  function caseless(text) {
    return [...text].map(c => {
      const lower = c.toLowerCase();
      const upper = c.toUpperCase();
      return lower !== upper && lower.length === 1 && upper.length === 1 ? `[${lower}${upper}]` : escapeRegExp(c);
    }).join('');
  }

  /**
   * A keyword as a whole word or phrase: hyphens and spaces interchangeable,
   * an optional plural "s"/"es", any case except for a name (isName).
   * "stereo" does not match "stereotypes"; "PPO" does not match "support";
   * "Lean" does not match "lean".
   * @param {string} term
   * @returns {string | null}
   */
  function termPattern(term) {
    const words = term.trim().split(/[\s\-‐-—_/]+/).filter(Boolean);
    if (!words.length) return null;
    if (isName(words)) return `${escapeRegExp(words[0])}(?:e?s)?`;
    return `${words.map(caseless).join(SEPARATOR)}(?:[eE]?[sS])?`;
  }

  /**
   * One pattern for every term; case is in the pattern, so `flags` never needs "i".
   * @param {string[]} terms
   * @param {string} flags
   */
  function keywordRegex(terms, flags) {
    const patterns = terms
      .filter(t => t && t.trim())
      .sort((a, b) => b.length - a.length)
      .map(termPattern)
      .filter(Boolean);
    if (!patterns.length) return null;
    return new RegExp(`(^|[^A-Za-z0-9])(${patterns.join('|')})(?![A-Za-z0-9])`, flags);
  }

  /**
   * @param {string | null | undefined} text
   * @param {string} keyword
   */
  function keywordMatches(text, keyword) {
    const regex = keywordRegex([keyword], '');
    return Boolean(text && regex && regex.test(text));
  }

  /**
   * `text` with each term wrapped in <mark class="className">.
   * @param {string} text
   * @param {string[] | null | undefined} terms
   * @param {string} className
   * @returns {string}
   */
  function highlight(text, terms, className) {
    const regex = text && terms && terms.length ? keywordRegex(terms, 'g') : null;
    if (!regex) return text;
    return text.replace(regex, (/** @type {string} */ match, /** @type {string} */ before, /** @type {string} */ word) => `${before}<mark class="${className}">${word}</mark>`);
  }

  /** @param {unknown} text */
  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return { AI_FIELDS, isArxiv, hasSummary, parseJsonl, parseFileList, mergeDay, keywordMatches, highlight, escapeHtml };
});
