/**
 * Which papers the list shows: a topic, then the refinements (arXiv category,
 * "Has code" and source), then the search text. Counts are faceted: each one applies
 * every other active filter but its own, so a number always says how many
 * papers that choice would show. Loaded as the global `Filters`, and by node
 * for tests. Entries are { record, info } with info from Render.describe.
 */
(function (root, factory) {
  const load = (name, file) => root[name] || (typeof require === 'function' ? require(file) : null);
  const api = factory(load('Render', './render.js'), load('Sources', './sources.js'), load('PaperData', './paper-data.js'));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Filters = api;
  }
})(typeof self !== 'undefined' ? self : this, function (Render, Sources, PaperData) {
  const OTHER_FIELDS = 'other';
  const FIXED_TOPICS = ['matches', 'all', 'authors'];

  /** The arXiv category group, or null for a paper from another source that has none. */
  function categoryOf(record, mainCategories) {
    const primary = (record.categories || [])[0];
    if (!primary && !PaperData.isArxiv(record)) return null;
    return mainCategories.includes(primary) ? primary : OTHER_FIELDS;
  }

  function inTopic(info, topic) {
    if (!topic || topic === 'all') return true;
    if (topic === 'matches') return info.matched;
    if (topic === 'authors') return info.match.authors.length > 0;
    return info.topics.some(t => t.name === topic);
  }

  function matchesQuery(record, query) {
    const text = query.trim().toLowerCase();
    if (!text) return true;
    const ai = record.pending ? {} : record.AI || {};
    return [record.title, record.summary, record.venue, record.doi, (record.authors || []).join(', '), record.id, ...Object.values(ai)]
      .join(' ')
      .toLowerCase()
      .includes(text);
  }

  /** Whether an entry passes every filter except the one named in `skip`. */
  function passes(entry, filters, mainCategories, skip) {
    const { record, info } = entry;
    return (skip === 'topic' || inTopic(info, filters.topic))
      && (skip === 'category' || filters.category === 'all' || categoryOf(record, mainCategories) === filters.category)
      && (skip === 'code' || !filters.codeOnly || Render.codeKind(record) === 'code')
      && (skip === 'source' || !filters.source || filters.source === 'all' || Sources.sourceKey(record) === filters.source)
      && matchesQuery(record, filters.query || '');
  }

  function apply(entries, filters, mainCategories) {
    return entries.filter(e => passes(e, filters, mainCategories));
  }

  function counts(entries, filters, mainCategories, topicNames) {
    const byTopic = entries.filter(e => passes(e, filters, mainCategories, 'topic'));
    const byCategory = entries.filter(e => passes(e, filters, mainCategories, 'category'));
    const byCode = entries.filter(e => passes(e, filters, mainCategories, 'code'));
    const bySource = entries.filter(e => passes(e, filters, mainCategories, 'source'));

    const topics = new Map([...FIXED_TOPICS, ...topicNames].map(t => [t, byTopic.filter(e => inTopic(e.info, t)).length]));
    const categories = new Map([['all', byCategory.length]]);
    byCategory.forEach(e => {
      const key = categoryOf(e.record, mainCategories);
      if (key) categories.set(key, (categories.get(key) || 0) + 1);
    });
    const sources = tally(bySource.map(e => Sources.sourceKey(e.record)));
    sources.set('all', bySource.length);
    return { topics, categories, sources, code: byCode.filter(e => Render.codeKind(e.record) === 'code').length };
  }

  function tally(keys) {
    const totals = new Map();
    keys.forEach(key => totals.set(key, (totals.get(key) || 0) + 1));
    return totals;
  }

  /**
   * The Source group: all sources, arXiv, then each venue by how many papers
   * it has that day (ties by name), with the faceted counts. Empty when every
   * paper is from arXiv, so an arXiv-only day shows no group.
   */
  function sourceOptions(records, counts) {
    if (records.every(r => PaperData.isArxiv(r))) return [];
    const labels = new Map(records.map(r => [Sources.sourceKey(r), Sources.sourceLabel(r)]));
    const totals = tally(records.map(r => Sources.sourceKey(r)));
    const keys = [...totals.keys()].sort((a, b) =>
      (b === Sources.ARXIV) - (a === Sources.ARXIV) || totals.get(b) - totals.get(a) || labels.get(a).localeCompare(labels.get(b)));
    const count = key => counts.sources.get(key) || 0;
    return [{ key: 'all', label: 'All sources', count: count('all') }, ...keys.map(key => ({ key, label: labels.get(key), count: count(key) }))];
  }

  function isRefined(filters) {
    return filters.category !== 'all' || Boolean(filters.codeOnly) || Boolean(filters.source && filters.source !== 'all');
  }

  return { OTHER_FIELDS, categoryOf, inTopic, apply, counts, sourceOptions, isRefined };
});
