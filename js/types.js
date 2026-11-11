/**
 * Record shapes the page reads, as JSDoc types for editors and `checkJs`.
 * Nothing here runs and the page does not load this file; the Python side
 * mirrors these shapes in summaries/shapes.py. See
 * docs/specs/s1-sources-beyond-arxiv.md (R3, Q3, Q4).
 */

/**
 * The five-part AI summary, written from the title and abstract.
 * @typedef {object} AiSummary
 * @property {string} tldr
 * @property {string} motivation
 * @property {string} method
 * @property {string} result
 * @property {string} conclusion
 */

/**
 * A paper from arXiv's /new listing, one line of data/<day>.jsonl. It has no
 * `source` field: a missing source means arXiv, so old days and forks keep
 * working.
 * @typedef {object} ArxivRecord
 * @property {string} id               arXiv ID, e.g. "2611.04001"
 * @property {undefined | 'arxiv'} [source]
 * @property {string} title
 * @property {string[]} authors
 * @property {string[]} categories     primary category first
 * @property {string} summary          the arXiv abstract
 * @property {string} [abs]            https://arxiv.org/abs/<id>
 * @property {string} [pdf]            https://arxiv.org/pdf/<id>
 * @property {string} [comment]        the arXiv comments line
 * @property {string} [code_url]       repository or project page linked from the abstract or comments
 * @property {string} [venue]          set once the paper is published ("published in IEEE TCSVT")
 * @property {string} [doi]
 */

/**
 * A paper from a journal or conference, found through OpenAlex, Crossref or
 * OpenReview. The publisher's abstract is not published (Q3), so there is no
 * `summary`, `abs` or `pdf`.
 * @typedef {object} VenueRecord
 * @property {string} id               "doi:<doi>" or "openreview:<forum id>"
 * @property {'openalex' | 'crossref' | 'openreview'} source
 * @property {string} title
 * @property {string[]} authors
 * @property {string} venue            e.g. "IEEE TCSVT"
 * @property {string} published        YYYY-MM-DD
 * @property {string | null} doi       without the https://doi.org/ prefix
 * @property {string | null} oa_url    a lawful open-access copy (OpenAlex or Unpaywall)
 * @property {string} url              the publisher's page, usually https://doi.org/<doi>
 * @property {string[]} categories     always empty
 * @property {string} [code_url]
 */

/**
 * One line of data/<day>_AI_enhanced_<Language>.jsonl: the raw record plus
 * its summary.
 * @typedef {(ArxivRecord | VenueRecord) & { AI: AiSummary }} SummaryRecord
 */

/**
 * What the page renders (PaperData.mergeDay, then DataSource.loadDay). `AI`
 * is present when the summary is complete. `pending` is true only for an
 * arXiv paper still waiting for its summary; a VenueRecord without `AI` is
 * not pending, because without a published abstract it may never get one.
 * @typedef {(ArxivRecord | VenueRecord) & {
 *   AI?: AiSummary,
 *   pending: boolean,
 *   date?: string,
 *   hf?: number,
 * }} PageRecord
 */
