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
  const AI_FIELDS = ['tldr', 'motivation', 'method', 'result', 'conclusion'];
  const RAW_FILE = /^(\d{4}-\d{2}-\d{2})\.jsonl$/;
  const AI_FILE = /^(\d{4}-\d{2}-\d{2})_AI_enhanced_([A-Za-z]+)\.jsonl$/;
  const SEPARATOR = '[\\s\\-\\u2010-\\u2014_/]+';

  function hasSummary(record) {
    return Boolean(record && record.AI) &&
      AI_FIELDS.every(f => typeof record.AI[f] === 'string' && record.AI[f].trim() !== '');
  }

  function parseJsonl(text) {
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

  /** Dates (newest first) and, per date, the summary languages available. */
  function parseFileList(text) {
    const languages = new Map();
    const rawDates = new Set();
    (text || '').split('\n').map(s => s.trim()).forEach(name => {
      const raw = name.match(RAW_FILE);
      const ai = name.match(AI_FILE);
      const date = raw ? raw[1] : ai ? ai[1] : null;
      if (!date) return;
      if (!languages.has(date)) languages.set(date, []);
      if (raw) rawDates.add(date);
      if (ai && !languages.get(date).includes(ai[2])) languages.get(date).push(ai[2]);
    });
    const dates = [...languages.keys()].sort().reverse();
    return { dates, languages, rawDates };
  }

  /**
   * One day's records: the raw crawl decides which papers exist and their
   * order; a paper with a complete summary uses the summary record, any
   * other is marked `pending`. Summary records without a raw entry (older
   * days) are kept.
   */
  function mergeDay(rawText, aiText) {
    const summaries = new Map();
    parseJsonl(aiText).forEach(r => {
      if (hasSummary(r) && !summaries.has(r.id)) summaries.set(r.id, r);
    });
    const seen = new Set();
    const records = [];
    parseJsonl(rawText).forEach(r => {
      if (seen.has(r.id)) return;
      seen.add(r.id);
      const summary = summaries.get(r.id);
      records.push(summary ? { ...summary, pending: false } : { ...r, pending: true });
    });
    summaries.forEach((r, id) => {
      if (!seen.has(id)) records.push({ ...r, pending: false });
    });
    return records;
  }

  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /**
   * A keyword as a whole word or phrase: case-insensitive, hyphens and spaces
   * interchangeable, an optional plural "s"/"es". "stereo" does not match
   * "stereotypes"; "PPO" does not match "support".
   */
  function termPattern(term) {
    const words = term.trim().split(/[\s\-‐-—_/]+/).filter(Boolean).map(escapeRegExp);
    return words.length ? `${words.join(SEPARATOR)}(?:e?s)?` : null;
  }

  function keywordRegex(terms, flags) {
    const patterns = terms
      .filter(t => t && t.trim())
      .sort((a, b) => b.length - a.length)
      .map(termPattern)
      .filter(Boolean);
    if (!patterns.length) return null;
    return new RegExp(`(^|[^A-Za-z0-9])(${patterns.join('|')})(?![A-Za-z0-9])`, flags);
  }

  function keywordMatches(text, keyword) {
    const regex = keywordRegex([keyword], 'i');
    return Boolean(text && regex && regex.test(text));
  }

  function highlight(text, terms, className) {
    const regex = text && terms && terms.length ? keywordRegex(terms, 'gi') : null;
    if (!regex) return text;
    return text.replace(regex, (match, before, word) => `${before}<span class="${className}">${word}</span>`);
  }

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return { AI_FIELDS, hasSummary, parseJsonl, parseFileList, mergeDay, keywordMatches, highlight, escapeHtml };
});
