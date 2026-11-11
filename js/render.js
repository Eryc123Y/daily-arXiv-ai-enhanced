/**
 * HTML for the three-pane reading page: list rows and the reading pane.
 * Pure functions over merged day records (PaperData.mergeDay); loaded as the
 * global `Render`, and by node for tests.
 */
(function (root, factory) {
  const load = (name, file) => root[name] || (typeof require === 'function' ? require(file) : null);
  const api = factory(load('PaperData', './paper-data.js'), load('Sources', './sources.js'));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Render = api;
  }
})(typeof self !== 'undefined' ? self : this, function (PaperData, Sources) {
  const esc = PaperData.escapeHtml;
  const FIELDS = [
    ['motivation', 'Motivation'],
    ['method', 'Method'],
    ['result', 'Result'],
    ['conclusion', 'Conclusion'],
  ];

  const PROJECT_PAGE = /^https?:\/\/[\w-]+\.git(?:hub|lab)\.io(?:\/|$)/i;
  const CODE_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M5.5 4 1.5 8l4 4M10.5 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  /** 'code' for a linked repository, 'page' for a project page, null when the paper links neither. */
  function codeKind(paper) {
    if (!paper.code_url) return null;
    return PROJECT_PAGE.test(paper.code_url) ? 'page' : 'code';
  }

  function codeMark(paper) {
    const kind = codeKind(paper);
    if (kind === 'code') return `<span class="row-code" title="Links its code">${CODE_ICON}Code</span>`;
    if (kind === 'page') return `<span class="row-code is-page" title="Links a project page">Project page</span>`;
    return '';
  }

  /** Upvotes on Hugging Face Daily Papers, when the paper was listed there. */
  function hfMark(paper) {
    return paper.hf ? `<span class="row-hf" title="Upvotes on Hugging Face Daily Papers">▲ ${Number(paper.hf)}</span>` : '';
  }

  function parseDay(day) {
    const [y, m, d] = day.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  }

  function formatDay(day, options = { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) {
    return parseDay(day).toLocaleDateString('en-GB', { ...options, timeZone: 'UTC' });
  }

  function formatRange(start, end) {
    if (start === end) return formatDay(start);
    return `${formatDay(start, { day: 'numeric', month: 'long' })} to ${formatDay(end, { day: 'numeric', month: 'long', year: 'numeric' })}`;
  }

  function authorList(authors) {
    return Array.isArray(authors) ? authors : String(authors || '').split(',').map(a => a.trim()).filter(Boolean);
  }

  function authorLine(authors, max = 6) {
    const list = authorList(authors);
    if (list.length <= max) return list.join(', ');
    const rest = list.length - max;
    return `${list.slice(0, max).join(', ')} and ${rest} other${rest === 1 ? '' : 's'}`;
  }

  /** Which interest keywords and authors a paper matches. */
  function matchesFor(paper, keywords, authors) {
    const ai = paper.pending ? null : paper.AI;
    const text = [paper.title, paper.summary, ai && ai.tldr].filter(Boolean).join(' ');
    const names = authorList(paper.authors).join(', ').toLowerCase();
    return {
      keywords: keywords.filter(k => PaperData.keywordMatches(text, k)),
      authors: authors.filter(a => a.trim() && names.includes(a.trim().toLowerCase())),
    };
  }

  /** The user's keywords grouped into the preset topics; the rest form one extra topic. */
  function topicsFor(keywords, presets) {
    const wanted = new Map(keywords.map(k => [k.toLowerCase(), k]));
    const used = new Set();
    const topics = ((presets && presets.topics) || [])
      .map(topic => ({
        name: topic.name,
        keywords: topic.keywords.filter(k => wanted.has(k.toLowerCase())).map(k => {
          used.add(k.toLowerCase());
          return wanted.get(k.toLowerCase());
        }),
      }))
      .filter(topic => topic.keywords.length);
    const others = keywords.filter(k => !used.has(k.toLowerCase()));
    return others.length ? [...topics, { name: 'Your other keywords', keywords: others }] : topics;
  }

  function topicNames(match, topics) {
    const hit = new Set(match.keywords.map(k => k.toLowerCase()));
    return topics.filter(t => t.keywords.some(k => hit.has(k.toLowerCase()))).map(t => t.name);
  }

  /** Everything the views need to know about a paper's relation to the user's interests. */
  function describe(paper, keywords, authors, topics) {
    const match = matchesFor(paper, keywords, authors);
    const names = new Set(topicNames(match, topics));
    return {
      match,
      matched: match.keywords.length + match.authors.length > 0,
      score: match.keywords.length + 2 * match.authors.length,
      topics: topics.map((t, index) => ({ name: t.name, index })).filter(t => names.has(t.name)),
    };
  }

  function mark(text, terms) {
    return PaperData.highlight(esc(text || ''), terms, 'hl');
  }

  function topicLabel(info, paper) {
    if (info.topics.length) {
      const first = info.topics[0];
      const more = info.topics.length > 1 ? ` <span class="row-more">+${info.topics.length - 1}</span>` : '';
      return `<span class="row-topic topic-${first.index}"><span class="dot"></span>${esc(first.name)}${more}</span>`;
    }
    if (info.match.authors.length) return `<span class="row-topic topic-author"><span class="dot"></span>Your authors</span>`;
    return `<span class="row-topic">${esc((paper.categories || [])[0] || '')}</span>`;
  }

  /** Under the title: categories and arXiv ID, or venue and publication date. */
  function rowMeta(paper) {
    if (PaperData.isArxiv(paper)) {
      return `<span class="row-meta"><span>${esc((paper.categories || []).slice(0, 2).join(', '))}</span><span>${esc(paper.id)}</span></span>`;
    }
    const day = Sources.publishedLabel(paper);
    return `<span class="row-meta is-venue"><span>${esc(Sources.sourceLabel(paper))}</span>${day ? `<span>${esc(day)}</span>` : ''}</span>`;
  }

  function renderRow(paper, info, selected) {
    const ai = paper.pending ? null : paper.AI;
    const lead = ai ? ai.tldr : paper.summary;
    return `<li><button type="button" class="row${selected ? ' is-selected' : ''}" data-id="${esc(paper.id)}"${selected ? ' aria-current="true"' : ''}>
  <span class="row-head">${topicLabel(info, paper)}${paper.pending ? '<span class="row-pending">Summary pending</span>' : ''}${hfMark(paper)}${codeMark(paper)}</span>
  <span class="row-title">${esc(paper.title)}</span>
  <span class="row-authors">${esc(authorLine(paper.authors, 3))}</span>
  <span class="row-lead">${esc(lead || '')}</span>
  ${rowMeta(paper)}
</button></li>`;
  }

  function arxivLinks(paper, primaryLink) {
    const abs = paper.abs || `https://arxiv.org/abs/${paper.id}`;
    const alphaxiv = `https://www.alphaxiv.org/abs/${encodeURIComponent(paper.id)}`;
    const sites = primaryLink === 'arxiv'
      ? [[abs, 'Open on arXiv', 'button-solid'], [alphaxiv, 'alphaXiv', 'button-outline']]
      : [[alphaxiv, 'Open on alphaXiv', 'button-solid'], [abs, 'arXiv', 'button-outline']];
    return [
      ...sites,
      [paper.pdf || abs.replace('/abs/', '/pdf/'), 'PDF', 'button-outline'],
      [abs.replace('/abs/', '/html/'), 'HTML', 'button-outline'],
    ];
  }

  /** The reader's buttons. The alphaXiv-or-arXiv choice applies to arXiv papers only. */
  function links(paper, primaryLink = 'alphaxiv') {
    const arxiv = PaperData.isArxiv(paper);
    const items = arxiv ? arxivLinks(paper, primaryLink) : Sources.venueLinks(paper);
    const kind = codeKind(paper);
    if (kind) items.push([paper.code_url, kind === 'code' ? 'Code' : 'Project page', 'button-outline']);
    if (paper.hf && arxiv) items.push([`https://huggingface.co/papers/${encodeURIComponent(paper.id)}`, `Hugging Face ▲ ${Number(paper.hf)}`, 'button-outline']);
    return items
      .map(([href, label, cls]) => `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener">${label}</a>`)
      .join('');
  }

  /**
   * The vertical line in the left margin of every arXiv PDF: identifier,
   * primary category, date. Without an arXiv ID: venue, DOI, publication date.
   */
  function stamp(paper) {
    if (!PaperData.isArxiv(paper)) {
      return [Sources.sourceLabel(paper), paper.doi ? `doi:${paper.doi}` : '', Sources.publishedLabel(paper)].filter(Boolean).join(' ');
    }
    const primary = (paper.categories || [])[0];
    const day = paper.date ? formatDay(paper.date, { day: 'numeric', month: 'short', year: 'numeric' }) : '';
    return [`arXiv:${paper.id}`, primary ? `[${primary}]` : '', day].filter(Boolean).join(' ');
  }

  function readerMeta(paper) {
    if (!PaperData.isArxiv(paper)) {
      const day = Sources.publishedLabel(paper);
      return [Sources.sourceLabel(paper), day ? `Published ${day}` : '', paper.doi ? `DOI ${paper.doi}` : '']
        .filter(Boolean).map(text => `<span>${esc(text)}</span>`).join('');
    }
    const venue = paper.venue ? `<span>Published in ${esc(paper.venue)}</span>` : '';
    return `<span>${esc((paper.categories || []).join(', '))}</span><span>arXiv ${esc(paper.id)}</span>${venue}${paper.comment ? `<span>${esc(paper.comment)}</span>` : ''}`;
  }

  /** Where the abstract would be, for a paper whose abstract is not published here. */
  function abstractElsewhere(paper, lead = '') {
    const href = Sources.publisherUrl(paper);
    const where = href
      ? `The abstract is on the <a href="${esc(href)}" target="_blank" rel="noopener">publisher's page</a>.`
      : 'The abstract is not available here.';
    return `<p class="abstract-elsewhere">${lead}${where}</p>`;
  }

  function summaryBody(paper, ai, terms) {
    const tail = paper.summary || PaperData.isArxiv(paper)
      ? `<details class="abstract"><summary>Show the abstract</summary><p>${mark(paper.summary, terms)}</p></details>`
      : abstractElsewhere(paper);
    return `<section class="tldr" aria-labelledby="tldrHeading"><h3 id="tldrHeading">TL;DR</h3><p class="provenance">AI summary of the title and abstract, not the full paper</p><p>${mark(ai.tldr, terms)}</p></section>
<div class="fields">${FIELDS.map(([key, label]) => `<section><h3>${label}</h3><p>${mark(ai[key], terms)}</p></section>`).join('')}</div>
${tail}`;
  }

  function readerBody(paper, ai, terms) {
    if (ai) return summaryBody(paper, ai, terms);
    const abstract = `<section class="abstract-open"><h3>Abstract</h3><p>${mark(paper.summary, terms)}</p></section>`;
    if (paper.pending) return `<p class="pending-note">This paper's summary has not been written yet. Here is its abstract.</p>\n${abstract}`;
    return paper.summary ? abstract : abstractElsewhere(paper, 'There is no summary of this paper. ');
  }

  function renderReader(paper, info, terms, options = {}) {
    const ai = paper.pending ? null : paper.AI;
    const topicLine = info.topics
      .map(t => `<span class="reader-topic topic-${t.index}"><span class="dot"></span>${esc(t.name)}</span>`)
      .join('');
    const reasons = [...info.match.keywords, ...info.match.authors];
    const matches = reasons.length
      ? `<span class="reader-matches">matches ${reasons.map(r => `<mark class="hl">${esc(r)}</mark>`).join(' ')}</span>`
      : '';
    const body = readerBody(paper, ai, terms);
    return `<p class="reader-stamp" aria-hidden="true">${esc(stamp(paper))}</p>
<article class="reader-body" aria-labelledby="readerTitle">
<p class="reader-kicker">${topicLine}${matches}</p>
<h2 class="reader-title" id="readerTitle">${mark(paper.title, terms)}</h2>
<p class="reader-authors">${PaperData.highlight(esc(authorLine(paper.authors, 12)), info.match.authors, 'hl')}</p>
<p class="reader-meta">${readerMeta(paper)}</p>
<p class="reader-links">${links(paper, options.primaryLink)}</p>
${body}
</article>`;
  }

  function daySentence(total, matched, hasInterests) {
    const papers = `${total.toLocaleString('en-GB')} new paper${total === 1 ? '' : 's'}`;
    if (!hasInterests) return `${papers}.`;
    return `${papers}, ${matched === 0 ? 'none' : matched} matching your interests.`;
  }

  /** Summaries written, out of the papers that can get one (every arXiv paper, and the others that have one). */
  function summaryProgress(records) {
    const done = records.filter(r => !r.pending && PaperData.hasSummary(r)).length;
    return { done, total: done + records.filter(r => r.pending).length };
  }

  function progressText(done, total) {
    if (done === 0) return `Summaries are being written. Each paper shows its abstract until its summary is ready.`;
    return `Summaries ready for ${done.toLocaleString('en-GB')} of ${total.toLocaleString('en-GB')}. The rest show their abstract for now.`;
  }

  return {
    formatDay,
    formatRange,
    authorLine,
    CODE_ICON,
    codeKind,
    matchesFor,
    topicsFor,
    topicNames,
    describe,
    renderRow,
    links,
    renderReader,
    daySentence,
    summaryProgress,
    progressText,
  };
});
