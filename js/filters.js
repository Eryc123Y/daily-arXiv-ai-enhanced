/**
 * Which papers the list shows: a topic, then the refinements (arXiv category,
 * "Has code", "Free to read", and the source's type, area and venue), then
 * the search text. Type and area come from the watched venues
 * (Sources.venueIndex of assets/venues.json, passed as `venues`); the type of
 * a venue paper is its kind when the venue is top, else "Other venues". Counts are
 * faceted: each one applies every other active filter but its own, so a
 * number always says how many papers that choice would show. Type and area
 * also leave out the venue, since choosing either resets it. Loaded as the global `Filters`, and by node
 * for tests. Entries are { record, info } with info from Render.describe.
 */
/**
 * The list's filters; the page keeps them on its state object.
 * @typedef {object} FilterState
 * @property {string | null} topic      'matches', 'all', 'authors', a topic name, or null for all
 * @property {string} category          'all', an arXiv category, or 'other'
 * @property {boolean} codeOnly
 * @property {boolean} freeOnly
 * @property {string} type              'all', 'arxiv', 'conference' (top), 'journal' (top) or 'other'
 * @property {string} area              'all' or an area
 * @property {string} source            'all' or a Sources.sourceKey
 * @property {string} [query]
 *
 * @typedef {{ key: string, label: string, count: number }} FilterOption
 */
(function (root, factory) {
  /**
   * A sibling script's global in the browser, or its module under node.
   * @param {string} name
   * @param {string} file
   * @returns {any}
   */
  const load = (name, file) => /** @type {any} */ (root)[name] || (typeof require === 'function' ? require(file) : null);
  const api = factory(load('Render', './render.js'), load('Sources', './sources.js'), load('PaperData', './paper-data.js'));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Filters = api;
  }
})(typeof self !== 'undefined' ? self : this, /**
 * @param {typeof import('./render.js')} Render
 * @param {typeof import('./sources.js')} Sources
 * @param {typeof import('./paper-data.js')} PaperData
 */
function (Render, Sources, PaperData) {
  const OTHER_FIELDS = 'other';
  /** @type {Array<[string, string]>} */
  const TYPES = [['all', 'All'], ['arxiv', 'arXiv preprints'], ['conference', 'Top conferences'], ['journal', 'Top journals'], ['other', 'Other venues']];
  /** @type {Partial<Record<string, string>>} */
  const TYPE_PHRASES = { arxiv: 'arXiv preprints', conference: 'top conferences', journal: 'top journals', other: 'other venues' };
  const FIXED_TOPICS = ['matches', 'all', 'authors'];

  /**
   * The arXiv category group, or null for a paper from another source that has none.
   * @param {AnyRecord} record
   * @param {string[]} mainCategories
   * @returns {string | null}
   */
  function categoryOf(record, mainCategories) {
    /** @type {string | undefined} */
    const primary = (record.categories || [])[0];
    if (!primary && !PaperData.isArxiv(record)) return null;
    return primary && mainCategories.includes(primary) ? primary : OTHER_FIELDS;
  }

  /**
   * @param {PaperInfo} info
   * @param {string | null | undefined} topic
   */
  function inTopic(info, topic) {
    if (!topic || topic === 'all') return true;
    if (topic === 'matches') return info.matched;
    if (topic === 'authors') return info.match.authors.length > 0;
    return info.topics.some(t => t.name === topic);
  }

  /**
   * @param {PageRecord} record
   * @param {string} query
   */
  function matchesQuery(record, query) {
    const text = query.trim().toLowerCase();
    if (!text) return true;
    const ai = record.pending ? {} : record.AI || {};
    const fields = /** @type {{ summary?: string, venue?: string, doi?: string | null }} */ (record);
    return [record.title, fields.summary, fields.venue, fields.doi, (record.authors || []).join(', '), record.id, ...Object.values(ai)]
      .join(' ')
      .toLowerCase()
      .includes(text);
  }

  /** @param {string | null | undefined} value */
  const isAll = value => !value || value === 'all';

  /**
   * Whether an entry passes every filter except those named in `skip` (a name or a list).
   * @param {ListEntry} entry
   * @param {FilterState} filters
   * @param {string[]} mainCategories
   * @param {VenueIndex} venues
   * @param {string | string[]} [skip]
   */
  function passes(entry, filters, mainCategories, venues, skip = []) {
    const { record, info } = entry;
    /** @param {string} name */
    const off = name => skip === name || (Array.isArray(skip) && skip.includes(name));
    return (off('topic') || inTopic(info, filters.topic))
      && (off('category') || filters.category === 'all' || categoryOf(record, mainCategories) === filters.category)
      && (off('code') || !filters.codeOnly || Render.codeKind(record) === 'code')
      && (off('free') || !filters.freeOnly || Sources.isFreeToRead(record))
      && (off('type') || isAll(filters.type) || Sources.typeKey(record, venues) === filters.type)
      && (off('area') || isAll(filters.area) || Sources.sourceArea(record, venues) === filters.area)
      && (off('source') || isAll(filters.source) || Sources.sourceKey(record) === filters.source)
      && matchesQuery(record, filters.query || '');
  }

  /**
   * @param {ListEntry[]} entries
   * @param {FilterState} filters
   * @param {string[]} mainCategories
   * @param {VenueIndex} venues
   */
  function apply(entries, filters, mainCategories, venues) {
    return entries.filter(e => passes(e, filters, mainCategories, venues));
  }

  /**
   * @param {ListEntry[]} entries
   * @param {FilterState} filters
   * @param {string[]} mainCategories
   * @param {string[]} topicNames
   * @param {VenueIndex} venues
   */
  function counts(entries, filters, mainCategories, topicNames, venues) {
    /** @param {string | string[]} skip */
    const without = skip => entries.filter(e => passes(e, filters, mainCategories, venues, skip));
    const byTopic = without('topic');
    const byCategory = without('category');
    // The venue row sits under type and area, and choosing a type or area resets it,
    // so their counts leave the venue choice out.
    const byType = without(['type', 'source']);
    const byArea = without(['area', 'source']);
    const bySource = without('source');

    const topics = new Map([...FIXED_TOPICS, ...topicNames].map(t => /** @type {[string, number]} */ ([t, byTopic.filter(e => inTopic(e.info, t)).length])));
    const categories = new Map([['all', byCategory.length]]);
    byCategory.forEach(e => {
      const key = categoryOf(e.record, mainCategories);
      if (key) categories.set(key, (categories.get(key) || 0) + 1);
    });
    const typeTotals = tally(byType.map(e => Sources.typeKey(e.record, venues)));
    /** @type {Map<string | null, number>} */
    const types = new Map([['all', byType.length], ...TYPES.slice(1).map(([key]) => /** @type {[string, number]} */ ([key, typeTotals.get(key) || 0]))]);
    /** @type {Map<string | null, number>} */
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

  /**
   * @template K
   * @param {K[]} keys
   * @returns {Map<K, number>}
   */
  function tally(keys) {
    /** @type {Map<K, number>} */
    const totals = new Map();
    keys.forEach(key => totals.set(key, (totals.get(key) || 0) + 1));
    return totals;
  }

  /** @param {AnyRecord[]} records */
  function hasVenuePapers(records) {
    return records.some(r => !PaperData.isArxiv(r));
  }

  /**
   * The Type keys the venue list offers: a kind for its top venues, 'other' for the rest.
   * @param {VenueIndex | null | undefined} venues
   * @returns {Set<string>}
   */
  function venueTypes(venues) {
    return new Set([...(venues || new Map()).values()].map(v => (v.top ? v.kind : Sources.OTHER_VENUES)));
  }

  /**
   * @param {VenueIndex | null | undefined} venues
   * @returns {string[]}
   */
  function venueAreas(venues) {
    return [...new Set([...(venues || new Map()).values()].map(v => v.area).filter(/** @returns {a is string} */ a => Boolean(a)))];
  }

  /** @typedef {ReturnType<typeof counts>} FilterCounts */

  /**
   * The Source section's three rows, each [{ key, label, count }] with the
   * faceted counts: Type (All, arXiv preprints when there are any, top
   * conferences and top journals when the venue list has them, and other
   * venues when it has venues not marked top), Area (empty when the list names no areas), and Venue (each venue
   * of the chosen type and area by how many papers it has that day, ties by
   * name; empty when there is none). null when every paper is from arXiv, so
   * an arXiv-only day shows no section.
   * @param {PageRecord[]} records
   * @param {FilterCounts} counts
   * @param {FilterState} filters
   * @param {VenueIndex} venues
   * @returns {{ types: FilterOption[], areas: FilterOption[], venues: FilterOption[] } | null}
   */
  function sourceGroups(records, counts, filters, venues) {
    if (!hasVenuePapers(records)) return null;
    const offered = venueTypes(venues);
    const hasArxiv = records.some(r => PaperData.isArxiv(r));
    /**
     * @param {Map<string | null, number>} map
     * @param {string} key
     * @param {string} label
     * @returns {FilterOption}
     */
    const option = (map, key, label) => ({ key, label, count: map.get(key) || 0 });
    const types = TYPES.filter(([key]) => key === 'all' || (key === Sources.ARXIV ? hasArxiv : offered.has(key)))
      .map(([key, label]) => option(counts.types, key, label));
    const names = venueAreas(venues);
    const areas = names.length ? [option(counts.areas, 'all', 'All'), ...names.map(a => option(counts.areas, a, a))] : [];
    const shown = records.filter(r => !PaperData.isArxiv(r)
      && (isAll(filters.type) || Sources.typeKey(r, venues) === filters.type)
      && (isAll(filters.area) || Sources.sourceArea(r, venues) === filters.area));
    const labels = new Map(shown.map(r => [Sources.sourceKey(r), Sources.sourceLabel(r)]));
    const totals = tally(shown.map(r => Sources.sourceKey(r)));
    const total = (/** @type {string} */ key) => totals.get(key) || 0;
    const label = (/** @type {string} */ key) => labels.get(key) || '';
    const keys = [...totals.keys()].sort((a, b) => total(b) - total(a) || label(a).localeCompare(label(b)));
    const venueRow = keys.length ? [option(counts.sources, 'all', 'All'), ...keys.map(key => option(counts.sources, key, label(key)))] : [];
    return { types, areas, venues: venueRow };
  }

  /**
   * The source choices a newly loaded day can show: a type or area the venue
   * list does not have, or a venue the day does not have, goes back to all;
   * a day without venue papers resets them and "Free to read" too, since it
   * shows neither.
   * @template {FilterState} F
   * @param {F} filters
   * @param {AnyRecord[]} records
   * @param {VenueIndex} venues
   * @returns {F}
   */
  function keepValid(filters, records, venues) {
    if (!hasVenuePapers(records)) return { ...filters, type: 'all', area: 'all', source: 'all', freeOnly: false };
    /** @type {string[]} */
    const types = ['all', Sources.ARXIV, ...venueTypes(venues)];
    const areas = ['all', ...venueAreas(venues)];
    const sources = new Set(['all', ...records.map(r => Sources.sourceKey(r))]);
    return {
      ...filters,
      type: types.includes(filters.type) ? filters.type : 'all',
      area: areas.includes(filters.area) ? filters.area : 'all',
      source: sources.has(filters.source) ? filters.source : 'all',
    };
  }

  /**
   * What the list heading adds after the topic and category: "with code", "free to read", "top journals", the area, "from <venue>".
   * @param {FilterState} filters
   * @param {(key: string) => string} sourceName
   * @returns {string[]}
   */
  function refinementPhrases(filters, sourceName) {
    return [
      filters.codeOnly ? 'with code' : null,
      filters.freeOnly ? 'free to read' : null,
      TYPE_PHRASES[filters.type] || null,
      isAll(filters.area) ? null : filters.area,
      isAll(filters.source) ? null : `from ${sourceName(filters.source)}`,
    ].filter(/** @returns {p is string} */ p => Boolean(p));
  }

  /** @param {FilterState} filters */
  function isRefined(filters) {
    return filters.category !== 'all' || Boolean(filters.codeOnly) || Boolean(filters.freeOnly)
      || !isAll(filters.type) || !isAll(filters.area) || !isAll(filters.source);
  }

  return { OTHER_FIELDS, categoryOf, inTopic, apply, counts, hasVenuePapers, sourceGroups, keepValid, refinementPhrases, isRefined };
});
