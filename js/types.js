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
 * A paper from a journal or conference, found through OpenAlex, Crossref,
 * OpenReview, the ACL Anthology, PMLR, JMLR or DataCite. The publisher's
 * abstract is not published (Q3), so there is no `summary`, `abs` or `pdf`.
 * @typedef {object} VenueRecord
 * @property {string} id               "doi:<doi>", "openreview:<forum id>", "url:<url>", or a bare arXiv ID
 *                                     when the paper has an arXiv version (then `source` still
 *                                     decides how it looks; the arXiv link is added as a secondary link)
 * @property {'openalex' | 'crossref' | 'openreview' | 'acl-anthology' | 'pmlr' | 'datacite' | 'jmlr'} source
 * @property {string} title
 * @property {string[]} authors
 * @property {string} venue            stable watch-list name, e.g. "IEEE TCSVT" or "ICLR" (no year)
 * @property {string} published        YYYY-MM-DD
 * @property {string | null} doi       without the https://doi.org/ prefix
 * @property {string | null} oa_url    a lawful open-access copy (OpenAlex or Unpaywall)
 * @property {string} url              the publisher's page, usually https://doi.org/<doi>
 * @property {string[]} categories     always empty
 * @property {boolean} [has_abstract]  the pipeline holds the abstract, so a summary will come;
 *                                     missing means false
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
 * arXiv paper, or a VenueRecord with `has_abstract: true`, still waiting
 * for its summary; any other VenueRecord without `AI` will never get one.
 * @typedef {(ArxivRecord | VenueRecord) & {
 *   AI?: AiSummary,
 *   pending: boolean,
 *   date?: string,
 *   hf?: number,
 * }} PageRecord
 */

/**
 * One entry of assets/venues.json, the public part of the watch list
 * (summaries/watchlist.json). The page groups venue papers by it: a venue
 * that is not listed counts as neither a top conference nor a top journal.
 * @typedef {object} VenueSummary
 * @property {string} name             the record's `venue` exactly, e.g. "ACM TOG"
 * @property {'conference' | 'journal'} kind
 * @property {string | null} area      e.g. "Graphics and VR"
 * @property {boolean} top             a flagship venue; false lists it under "Other venues".
 *                                     Files written before the flag have none (Sources.venueIndex reads that as true)
 */

/**
 * A line of a day's raw or summary file as parsed (PaperData.parseJsonl).
 * @typedef {ArxivRecord | VenueRecord | SummaryRecord} RawRecord
 */

/**
 * A raw or merged record, for helpers that take either.
 * @typedef {RawRecord | PageRecord} AnyRecord
 */

/**
 * What the page knows about a watched venue (Sources.venueIndex).
 * @typedef {object} VenueInfo
 * @property {'conference' | 'journal'} kind
 * @property {string | null} area
 * @property {boolean} top
 */

/** @typedef {Map<string, VenueInfo>} VenueIndex */

/**
 * A link button: [url, label, CSS class].
 * @typedef {[string, string, string]} LinkButton
 */

/**
 * A row of the paper list: the record, its place in the day's file, and
 * what Render.describe found in it.
 * @typedef {{ record: PageRecord, index: number, info: PaperInfo }} ListEntry
 */

/** @typedef {ReturnType<typeof import('./render.js').describe>} PaperInfo */

/**
 * A venue's papers in the weekly list (Streams.venueGroups).
 * @typedef {object} VenueGroup
 * @property {string} key
 * @property {string} label
 * @property {string | null} kind
 * @property {string | null} area
 * @property {ListEntry[]} entries
 */

/**
 * An interest topic: a name and its keywords (js/interest-presets.js, or the
 * reader's own keywords grouped by Render.topicsFor).
 * @typedef {{ name: string, keywords: string[] }} Topic
 */
