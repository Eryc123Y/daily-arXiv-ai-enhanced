/**
 * HTML for the three-pane reading page: list rows and the reading pane.
 * Pure functions over merged day records (PaperData.mergeDay); loaded as the
 * global `Render`, and by node for tests.
 */
(function (root, factory) {
  const api = factory(root.PaperData || (typeof require === 'function' ? require('./paper-data.js') : null));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Render = api;
  }
})(typeof self !== 'undefined' ? self : this, function (PaperData) {
  const esc = PaperData.escapeHtml;
  const FIELDS = [
    ['motivation', 'Motivation'],
    ['method', 'Method'],
    ['result', 'Result'],
    ['conclusion', 'Conclusion'],
  ];

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

  function renderRow(paper, info, selected) {
    const ai = paper.pending ? null : paper.AI;
    const lead = ai ? ai.tldr : paper.summary;
    return `<li><button type="button" class="row${selected ? ' is-selected' : ''}" data-id="${esc(paper.id)}"${selected ? ' aria-current="true"' : ''}>
  <span class="row-head">${topicLabel(info, paper)}${paper.pending ? '<span class="row-pending">Summary pending</span>' : ''}</span>
  <span class="row-title">${esc(paper.title)}</span>
  <span class="row-authors">${esc(authorLine(paper.authors, 3))}</span>
  <span class="row-lead">${esc(lead || '')}</span>
  <span class="row-meta"><span>${esc((paper.categories || []).slice(0, 2).join(', '))}</span><span>${esc(paper.id)}</span></span>
</button></li>`;
  }

  function links(paper, primaryLink = 'alphaxiv') {
    const abs = paper.abs || `https://arxiv.org/abs/${paper.id}`;
    const alphaxiv = `https://www.alphaxiv.org/abs/${encodeURIComponent(paper.id)}`;
    const sites = primaryLink === 'arxiv'
      ? [[abs, 'Open on arXiv', 'button-solid'], [alphaxiv, 'alphaXiv', 'button-outline']]
      : [[alphaxiv, 'Open on alphaXiv', 'button-solid'], [abs, 'arXiv', 'button-outline']];
    const items = [
      ...sites,
      [paper.pdf || abs.replace('/abs/', '/pdf/'), 'PDF', 'button-outline'],
      [abs.replace('/abs/', '/html/'), 'HTML', 'button-outline'],
    ];
    if (paper.code_url) items.push([paper.code_url, 'Code', 'button-outline']);
    return items
      .map(([href, label, cls]) => `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener">${label}</a>`)
      .join('');
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
    const body = ai
      ? `<section class="tldr" aria-labelledby="tldrHeading"><h3 id="tldrHeading">TL;DR</h3><p>${mark(ai.tldr, terms)}</p></section>
<div class="fields">${FIELDS.map(([key, label]) => `<section><h3>${label}</h3><p>${mark(ai[key], terms)}</p></section>`).join('')}</div>
<details class="abstract"><summary>Show the abstract</summary><p>${mark(paper.summary, terms)}</p></details>`
      : `<p class="pending-note">This paper's summary has not been written yet. Here is its abstract.</p>
<section class="abstract-open"><h3>Abstract</h3><p>${mark(paper.summary, terms)}</p></section>`;
    return `<article class="reader-body" aria-labelledby="readerTitle">
<p class="reader-kicker">${topicLine}${matches}</p>
<h2 class="reader-title" id="readerTitle">${mark(paper.title, terms)}</h2>
<p class="reader-authors">${PaperData.highlight(esc(authorLine(paper.authors, 12)), info.match.authors, 'hl')}</p>
<p class="reader-meta"><span>${esc((paper.categories || []).join(', '))}</span><span>arXiv ${esc(paper.id)}</span>${paper.comment ? `<span>${esc(paper.comment)}</span>` : ''}</p>
<p class="reader-links">${links(paper, options.primaryLink)}</p>
${body}
</article>`;
  }

  function daySentence(total, matched, hasInterests) {
    const papers = `${total.toLocaleString('en-GB')} new paper${total === 1 ? '' : 's'}`;
    if (!hasInterests) return `${papers}.`;
    return `${papers}, ${matched === 0 ? 'none' : matched} matching your interests.`;
  }

  function progressText(done, total) {
    if (done === 0) return `Summaries are being written. Each paper shows its abstract until its summary is ready.`;
    return `Summaries ready for ${done.toLocaleString('en-GB')} of ${total.toLocaleString('en-GB')}. The rest show their abstract for now.`;
  }

  return {
    formatDay,
    formatRange,
    authorLine,
    matchesFor,
    topicsFor,
    topicNames,
    describe,
    renderRow,
    renderReader,
    daySentence,
    progressText,
  };
});
