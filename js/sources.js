/**
 * Where a paper comes from: arXiv, or a journal or conference found through
 * OpenAlex, Crossref or OpenReview (docs/specs/s1-sources-beyond-arxiv.md).
 * Keys and labels for the Source filter, the publication date, and the
 * links a non-arXiv paper may open. Loaded as the global `Sources`, and by
 * node for tests. Record shapes: js/types.js.
 */
(function (root, factory) {
  const api = factory(root.PaperData || (typeof require === 'function' ? require('./paper-data.js') : null));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Sources = api;
  }
})(typeof self !== 'undefined' ? self : this, function (PaperData) {
  const ARXIV = 'arxiv';
  const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
  const ARXIV_ID = /^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?$/;
  const SOURCE_NAMES = { openreview: 'OpenReview' };
  const NO_VENUE = 'Journal or conference';

  /** The filter key: 'arxiv', or 'venue:<venue>' for every other paper. */
  function sourceKey(paper) {
    return PaperData.isArxiv(paper) ? ARXIV : `venue:${sourceLabel(paper)}`;
  }

  /**
   * The paper's arXiv ID: the id of an arXiv record, or of a feed record
   * whose id is a bare arXiv ID (a journal paper with an arXiv version).
   */
  function arxivId(paper) {
    if (PaperData.isArxiv(paper)) return paper.id;
    return ARXIV_ID.test(paper.id || '') ? paper.id : null;
  }

  /** What the page calls the source: "arXiv", the venue, or a fallback when the record has none. */
  function sourceLabel(paper) {
    if (PaperData.isArxiv(paper)) return 'arXiv';
    const venue = typeof paper.venue === 'string' ? paper.venue.trim() : '';
    return venue || SOURCE_NAMES[paper.source] || NO_VENUE;
  }

  /** "9 Nov 2026" from `published`, or '' when it is missing or malformed. */
  function publishedLabel(paper) {
    const match = ISO_DAY.exec((paper && paper.published) || '');
    if (!match) return '';
    const when = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
    if (Number.isNaN(when.getTime())) return '';
    return when.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  }

  /** The URL when it is http or https; anything else (javascript:, data:) is dropped. */
  function safeUrl(url) {
    if (typeof url !== 'string') return null;
    return /^https?:\/\//i.test(url.trim()) ? url.trim() : null;
  }

  /** The publisher's page: `url`, else the DOI resolver. */
  function publisherUrl(paper) {
    return safeUrl(paper.url) || (paper.doi ? safeUrl(`https://doi.org/${paper.doi}`) : null);
  }

  /**
   * Buttons for a non-arXiv paper: the open-access copy when there is one,
   * labelled as such, with the publisher page beside it; else the publisher
   * page. alphaXiv or arXiv (per the setting) only as a secondary link, and
   * only when the record's id is a real arXiv ID.
   */
  function venueLinks(paper, primaryLink = 'alphaxiv') {
    const openAccess = safeUrl(paper.oa_url);
    const publisher = publisherUrl(paper);
    const main = openAccess
      ? [
        [openAccess, 'Open the open-access copy', 'button-solid'],
        ...(publisher && publisher !== openAccess ? [[publisher, 'Publisher page', 'button-outline']] : []),
      ]
      : publisher ? [[publisher, 'Open the publisher page', 'button-solid']] : [];
    const id = arxivId(paper);
    if (!id) return main;
    const preprint = primaryLink === 'arxiv'
      ? [`https://arxiv.org/abs/${encodeURIComponent(id).replace('%2F', '/')}`, 'arXiv']
      : [`https://www.alphaxiv.org/abs/${encodeURIComponent(id)}`, 'alphaXiv'];
    return [...main, [...preprint, 'button-outline']];
  }

  return { ARXIV, arxivId, sourceKey, sourceLabel, publishedLabel, safeUrl, publisherUrl, venueLinks };
});
