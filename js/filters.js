/**
 * Which papers the list shows: a topic, then the refinements (arXiv category
 * and "Has code"), then the search text. Counts are faceted: each one applies
 * every other active filter but its own, so a number always says how many
 * papers that choice would show. Loaded as the global `Filters`, and by node
 * for tests. Entries are { record, info } with info from Render.describe.
 */
(function (root, factory) {
  const api = factory(root.Render || (typeof require === 'function' ? require('./render.js') : null));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Filters = api;
  }
})(typeof self !== 'undefined' ? self : this, function (Render) {
  const OTHER_FIELDS = 'other';
  const FIXED_TOPICS = ['matches', 'all', 'authors'];

  function categoryOf(record, mainCategories) {
    const primary = (record.categories || [])[0];
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
    return [record.title, record.summary, (record.authors || []).join(', '), record.id, ...Object.values(ai)]
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
      && matchesQuery(record, filters.query || '');
  }

  function apply(entries, filters, mainCategories) {
    return entries.filter(e => passes(e, filters, mainCategories));
  }

  function counts(entries, filters, mainCategories, topicNames) {
    const byTopic = entries.filter(e => passes(e, filters, mainCategories, 'topic'));
    const byCategory = entries.filter(e => passes(e, filters, mainCategories, 'category'));
    const byCode = entries.filter(e => passes(e, filters, mainCategories, 'code'));

    const topics = new Map([...FIXED_TOPICS, ...topicNames].map(t => [t, byTopic.filter(e => inTopic(e.info, t)).length]));
    const categories = new Map([['all', byCategory.length]]);
    byCategory.forEach(e => {
      const key = categoryOf(e.record, mainCategories);
      categories.set(key, (categories.get(key) || 0) + 1);
    });
    return { topics, categories, code: byCode.filter(e => Render.codeKind(e.record) === 'code').length };
  }

  function isRefined(filters) {
    return filters.category !== 'all' || Boolean(filters.codeOnly);
  }

  return { OTHER_FIELDS, categoryOf, inTopic, apply, counts, isRefined };
});
