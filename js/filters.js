/**
 * Which papers the list shows: a topic, then the refinements (arXiv category,
 * "Has code", "Free to read", and the source's type, area and venue), then
 * the search text. Type and area come from the watched venues
 * (Sources.venueIndex of assets/venues.json, passed as `venues`). Counts are
 * faceted: each one applies every other active filter but its own, so a
 * number always says how many papers that choice would show. Type and area
 * also leave out the venue, since choosing either resets it. Loaded as the global `Filters`, and by node
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
  const TYPES = [['all', 'All'], ['arxiv', 'arXiv preprints'], ['conference', 'Top conferences'], ['journal', 'Top journals']];
  const TYPE_PHRASES = { arxiv: 'arXiv preprints', conference: 'top conferences', journal: 'top journals' };
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

  const isAll = value => !value || value === 'all';

  /** Whether an entry passes every filter except those named in `skip` (a name or a list). */
  function passes(entry, filters, mainCategories, venues, skip = []) {
    const { record, info } = entry;
    const off = name => skip === name || (Array.isArray(skip) && skip.includes(name));
    return (off('topic') || inTopic(info, filters.topic))
      && (off('category') || filters.category === 'all' || categoryOf(record, mainCategories) === filters.category)
      && (off('code') || !filters.codeOnly || Render.codeKind(record) === 'code')
      && (off('free') || !filters.freeOnly || Sources.isFreeToRead(record))
      && (off('type') || isAll(filters.type) || Sources.sourceType(record, venues) === filters.type)
      && (off('area') || isAll(filters.area) || Sources.sourceArea(record, venues) === filters.area)
      && (off('source') || isAll(filters.source) || Sources.sourceKey(record) === filters.source)
      && matchesQuery(record, filters.query || '');
  }

  function apply(entries, filters, mainCategories, venues) {
    return entries.filter(e => passes(e, filters, mainCategories, venues));
  }

  function counts(entries, filters, mainCategories, topicNames, venues) {
    const without = skip => entries.filter(e => passes(e, filters, mainCategories, venues, skip));
    const byTopic = without('topic');
    const byCategory = without('category');
    // The venue row sits under type and area, and choosing a type or area resets it,
    // so their counts leave the venue choice out.
    const byType = without(['type', 'source']);
    const byArea = without(['area', 'source']);
    const bySource = without('source');

    const topics = new Map([...FIXED_TOPICS, ...topicNames].map(t => [t, byTopic.filter(e => inTopic(e.info, t)).length]));
    const categories = new Map([['all', byCategory.length]]);
    byCategory.forEach(e => {
      const key = categoryOf(e.record, mainCategories);
      if (key) categories.set(key, (categories.get(key) || 0) + 1);
    });
    const typeTotals = tally(byType.map(e => Sources.sourceType(e.record, venues)));
    const types = new Map([['all', byType.length], ...TYPES.slice(1).map(([key]) => [key, typeTotals.get(key) || 0])]);
    const areas = new Map([['all', byArea.length], ...tally(byArea.map(e => Sources.sourceArea(e.record, venues)).filter(Boolean))]);
    const sources = tally(bySource.map(e => Sources.sourceKey(e.record)));
    sources.set('all', bySource.length);
    return {
      topics,
      categories,
      types,
      areas,
      sources,
      code: without('code').filter(e => Render.codeKind(e.record) === 'code').length,
      free: without('free').filter(e => Sources.isFreeToRead(e.record)).length,
    };
  }

  function tally(keys) {
    const totals = new Map();
    keys.forEach(key => totals.set(key, (totals.get(key) || 0) + 1));
    return totals;
  }

  function hasVenuePapers(records) {
    return records.some(r => !PaperData.isArxiv(r));
  }

  function venueKinds(venues) {
    return new Set([...(venues || new Map()).values()].map(v => v.kind));
  }

  function venueAreas(venues) {
    return [...new Set([...(venues || new Map()).values()].map(v => v.area).filter(Boolean))];
  }

  /**
   * The Source section's three rows, each [{ key, label, count }] with the
   * faceted counts: Type (All, arXiv preprints, and each kind the venue list
   * has), Area (empty when the list names no areas), and Venue (each venue
   * of the chosen type and area by how many papers it has that day, ties by
   * name; empty when there is none). null when every paper is from arXiv, so
   * an arXiv-only day shows no section.
   */
  function sourceGroups(records, counts, filters, venues) {
    if (!hasVenuePapers(records)) return null;
    const kinds = venueKinds(venues);
    const option = (map, key, label) => ({ key, label, count: map.get(key) || 0 });
    const types = TYPES.filter(([key]) => key === 'all' || key === Sources.ARXIV || kinds.has(key))
      .map(([key, label]) => option(counts.types, key, label));
    const names = venueAreas(venues);
    const areas = names.length ? [option(counts.areas, 'all', 'All'), ...names.map(a => option(counts.areas, a, a))] : [];
    const shown = records.filter(r => !PaperData.isArxiv(r)
      && (isAll(filters.type) || Sources.sourceType(r, venues) === filters.type)
      && (isAll(filters.area) || Sources.sourceArea(r, venues) === filters.area));
    const labels = new Map(shown.map(r => [Sources.sourceKey(r), Sources.sourceLabel(r)]));
    const totals = tally(shown.map(r => Sources.sourceKey(r)));
    const keys = [...totals.keys()].sort((a, b) => totals.get(b) - totals.get(a) || labels.get(a).localeCompare(labels.get(b)));
    const venueRow = keys.length ? [option(counts.sources, 'all', 'All'), ...keys.map(key => option(counts.sources, key, labels.get(key)))] : [];
    return { types, areas, venues: venueRow };
  }

  /**
   * The source choices a newly loaded day can show: a type or area the venue
   * list does not have, or a venue the day does not have, goes back to all;
   * a day without venue papers resets them and "Free to read" too, since it
   * shows neither.
   */
  function keepValid(filters, records, venues) {
    if (!hasVenuePapers(records)) return { ...filters, type: 'all', area: 'all', source: 'all', freeOnly: false };
    const types = ['all', Sources.ARXIV, ...venueKinds(venues)];
    const areas = ['all', ...venueAreas(venues)];
    const sources = new Set(['all', ...records.map(r => Sources.sourceKey(r))]);
    return {
      ...filters,
      type: types.includes(filters.type) ? filters.type : 'all',
      area: areas.includes(filters.area) ? filters.area : 'all',
      source: sources.has(filters.source) ? filters.source : 'all',
    };
  }

  /** What the list heading adds after the topic and category: "with code", "free to read", "top journals", the area, "from <venue>". */
  function refinementPhrases(filters, sourceName) {
    return [
      filters.codeOnly ? 'with code' : null,
      filters.freeOnly ? 'free to read' : null,
      TYPE_PHRASES[filters.type] || null,
      isAll(filters.area) ? null : filters.area,
      isAll(filters.source) ? null : `from ${sourceName(filters.source)}`,
    ].filter(Boolean);
  }

  function isRefined(filters) {
    return filters.category !== 'all' || Boolean(filters.codeOnly) || Boolean(filters.freeOnly)
      || !isAll(filters.type) || !isAll(filters.area) || !isAll(filters.source);
  }

  return { OTHER_FIELDS, categoryOf, inTopic, apply, counts, hasVenuePapers, sourceGroups, keepValid, refinementPhrases, isRefined };
});
