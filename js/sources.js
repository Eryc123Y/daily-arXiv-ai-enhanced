/**
 * Where a paper comes from: arXiv, or a journal or conference found through
 * OpenAlex, Crossref, OpenReview, the ACL Anthology, PMLR, JMLR or DataCite
 * (docs/specs/s1-sources-beyond-arxiv.md). Keys and labels for the Source
 * filter, the type, area and tier of a watched venue (assets/venues.json),
 * whether a paper is free to read, the
 * publication date, and the links a non-arXiv paper may open. Loaded as the global `Sources`, and by
 * node for tests. Record shapes: js/types.js.
 */
(function (root, factory) {
  const api = factory(root.PaperData || (typeof require === 'function' ? require('./paper-data.js') : null));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Sources = api;
  }
})(typeof self !== 'undefined' ? self : this, /** @param {typeof import('./paper-data.js')} PaperData */ function (PaperData) {
  const ARXIV = 'arxiv';
  const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
  const ARXIV_ID = /^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?$/;
  /** @type {Partial<Record<string, string>>} */
  const SOURCE_NAMES = { openreview: 'OpenReview', 'acl-anthology': 'ACL Anthology', pmlr: 'PMLR', jmlr: 'JMLR', datacite: 'DataCite' };
  const NO_VENUE = 'Journal or conference';

  /**
   * The filter key: 'arxiv', or 'venue:<venue>' for every other paper.
   * @param {AnyRecord} paper
   * @returns {string}
   */
  function sourceKey(paper) {
    return PaperData.isArxiv(paper) ? ARXIV : `venue:${sourceLabel(paper)}`;
  }

  /**
   * The paper's arXiv ID: the id of an arXiv record, or of a feed record
   * whose id is a bare arXiv ID (a journal paper with an arXiv version).
   * @param {AnyRecord} paper
   * @returns {string | null}
   */
  function arxivId(paper) {
    if (PaperData.isArxiv(paper)) return paper.id;
    return ARXIV_ID.test(paper.id || '') ? paper.id : null;
  }

  /**
   * What the page calls the source: "arXiv", the venue, or a fallback when the record has none.
   * @param {AnyRecord} paper
   * @returns {string}
   */
  function sourceLabel(paper) {
    if (PaperData.isArxiv(paper)) return 'arXiv';
    const venue = typeof paper.venue === 'string' ? paper.venue.trim() : '';
    return venue || SOURCE_NAMES[paper.source] || NO_VENUE;
  }

  /**
   * "9 Nov 2026" from `published`, or '' when it is missing or malformed.
   * @param {Partial<VenueRecord> | null | undefined} paper
   */
  function publishedLabel(paper) {
    const match = ISO_DAY.exec((paper && paper.published) || '');
    if (!match) return '';
    const when = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
    if (Number.isNaN(when.getTime())) return '';
    return when.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  }

  /**
   * The URL when it is http or https; anything else (javascript:, data:) is dropped.
   * @param {unknown} url
   * @returns {string | null}
   */
  function safeUrl(url) {
    if (typeof url !== 'string') return null;
    return /^https?:\/\//i.test(url.trim()) ? url.trim() : null;
  }

  /**
   * The publisher's page: `url`, else the DOI resolver.
   * @param {Partial<VenueRecord>} paper
   */
  function publisherUrl(paper) {
    return safeUrl(paper.url) || (paper.doi ? safeUrl(`https://doi.org/${paper.doi}`) : null);
  }

  /**
   * Buttons for a non-arXiv paper: the open-access copy when there is one,
   * labelled as such, with the publisher page beside it; else the publisher
   * page. alphaXiv or arXiv (per the setting) only as a secondary link, and
   * only when the record's id is a real arXiv ID.
   * @param {VenueRecord} paper
   * @param {string} [primaryLink]
   * @returns {LinkButton[]}
   */
  function venueLinks(paper, primaryLink = 'alphaxiv') {
    const openAccess = safeUrl(paper.oa_url);
    const publisher = publisherUrl(paper);
    const main = /** @type {LinkButton[]} */ (openAccess
      ? [
        [openAccess, 'Open the open-access copy', 'button-solid'],
        ...(publisher && publisher !== openAccess ? [[publisher, 'Publisher page', 'button-outline']] : []),
      ]
      : publisher ? [[publisher, 'Open the publisher page', 'button-solid']] : []);
    const id = arxivId(paper);
    if (!id) return main;
    /** @type {[string, string]} */
    const preprint = primaryLink === 'arxiv'
      ? [`https://arxiv.org/abs/${encodeURIComponent(id).replace('%2F', '/')}`, 'arXiv']
      : [`https://www.alphaxiv.org/abs/${encodeURIComponent(id)}`, 'alphaXiv'];
    return [...main, [...preprint, 'button-outline']];
  }

  /** @type {unknown[]} */
  const KINDS = ['conference', 'journal'];
  const OTHER_VENUES = 'other';

  /**
   * The watched venues (assets/venues.json, `[{name, kind, area, top}]`) as a
   * Map from name to { kind, area, top }. Malformed entries are skipped;
   * anything but a list (a missing file) gives an empty Map, so no paper is
   * grouped. A venue is top unless it says `top: false`: lists written before
   * the flag held only top venues.
   * @param {unknown} list
   * @returns {VenueIndex}
   */
  function venueIndex(list) {
    /** @type {VenueIndex} */
    const index = new Map();
    (Array.isArray(list) ? list : []).forEach(venue => {
      const name = venue && typeof venue.name === 'string' ? venue.name.trim() : '';
      if (!name || !KINDS.includes(venue.kind)) return;
      const area = typeof venue.area === 'string' && venue.area.trim() ? venue.area.trim() : null;
      index.set(name, { kind: venue.kind, area, top: venue.top !== false });
    });
    return index;
  }

  /**
   * @param {AnyRecord} paper
   * @param {VenueIndex | null | undefined} index
   */
  function watched(paper, index) {
    return PaperData.isArxiv(paper) || !index ? null : index.get(sourceLabel(paper)) || null;
  }

  /**
   * 'arxiv', the watched venue's kind ('conference' or 'journal'), or null for a venue not on the list.
   * @param {AnyRecord} paper
   * @param {VenueIndex | null | undefined} index
   * @returns {string | null}
   */
  function sourceType(paper, index) {
    if (PaperData.isArxiv(paper)) return ARXIV;
    const venue = watched(paper, index);
    return venue ? venue.kind : null;
  }

  /**
   * The paper's key in the Type selector: 'arxiv'; 'conference' or 'journal'
   * for a top venue of that kind; 'other' for a watched venue not marked top;
   * null for a venue not on the list.
   * @param {AnyRecord} paper
   * @param {VenueIndex | null | undefined} index
   * @returns {string | null}
   */
  function typeKey(paper, index) {
    if (PaperData.isArxiv(paper)) return ARXIV;
    const venue = watched(paper, index);
    if (!venue) return null;
    return venue.top ? venue.kind : OTHER_VENUES;
  }

  /**
   * The watched venue's area, e.g. "Graphics and VR"; null for arXiv papers and unwatched venues.
   * @param {AnyRecord} paper
   * @param {VenueIndex | null | undefined} index
   */
  function sourceArea(paper, index) {
    const venue = watched(paper, index);
    return venue ? venue.area : null;
  }

  /**
   * Whether the paper can be read without a subscription: every arXiv paper, and a venue paper with an open-access copy.
   * @param {AnyRecord} paper
   */
  function isFreeToRead(paper) {
    return PaperData.isArxiv(paper) || Boolean(safeUrl(paper.oa_url));
  }

  return {
    ARXIV, OTHER_VENUES, arxivId, sourceKey, sourceLabel, publishedLabel, safeUrl, publisherUrl, venueLinks,
    venueIndex, sourceType, typeKey, sourceArea, isFreeToRead,
  };
});
