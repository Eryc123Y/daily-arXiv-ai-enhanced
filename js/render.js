/**
 * HTML for the reading page. Pure functions over merged day records
 * (see PaperData.mergeDay); loaded as the global `Render`, and by node for tests.
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
  const MAX_AUTHORS = 6;

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

  function authorLine(authors) {
    const list = authorList(authors);
    if (list.length <= MAX_AUTHORS) return list.join(', ');
    const rest = list.length - MAX_AUTHORS;
    return `${list.slice(0, MAX_AUTHORS).join(', ')} and ${rest} other${rest === 1 ? '' : 's'}`;
  }

  /** Which of the interest keywords and authors a paper matches. */
  function matchesFor(paper, keywords, authors) {
    const ai = paper.pending ? null : paper.AI;
    const text = [paper.title, paper.summary, ai && ai.tldr].filter(Boolean).join(' ');
    const names = authorList(paper.authors).join(', ').toLowerCase();
    return {
      keywords: keywords.filter(k => PaperData.keywordMatches(text, k)),
      authors: authors.filter(a => a.trim() && names.includes(a.trim().toLowerCase())),
    };
  }

  function mark(text, terms) {
    return PaperData.highlight(esc(text || ''), terms, 'hl');
  }

  function paperLinks(paper) {
    const abs = paper.abs || `https://arxiv.org/abs/${paper.id}`;
    const links = [
      [abs, 'arXiv'],
      [paper.pdf || abs.replace('/abs/', '/pdf/'), 'PDF'],
      [abs.replace('/abs/', '/html/'), 'HTML'],
    ];
    if (paper.code_url) links.push([paper.code_url, 'Code']);
    return links.map(([href, label]) => `<a href="${esc(href)}" target="_blank" rel="noopener">${label}</a>`).join('');
  }

  function renderPaper(paper, match, terms) {
    const ai = paper.pending ? null : paper.AI;
    const matched = match.keywords.length + match.authors.length > 0;
    const reasons = [...match.keywords, ...match.authors].map(esc).join(', ');
    const authorTerms = match.authors;
    const categories = (paper.categories || []).map(esc).join(', ');
    const lead = ai
      ? `<p class="paper-tldr">${mark(ai.tldr, terms)}</p>`
      : `<p class="paper-abstract is-clamped">${mark(paper.summary, terms)}</p><p class="paper-pending">Summary not written yet; this is the abstract.</p>`;
    const fields = ai
      ? `<dl class="paper-fields">${FIELDS.map(([key, label]) => `<dt>${label}</dt><dd>${mark(ai[key], terms)}</dd>`).join('')}</dl>`
      : '';
    const more = ai
      ? `<details class="paper-more"><summary>Full summary and abstract</summary>${fields}<h4>Abstract</h4><p class="paper-abstract">${mark(paper.summary, terms)}</p></details>`
      : '';
    return `<article class="paper${matched ? ' is-match' : ''}${paper.pending ? ' is-pending' : ''}" id="paper-${esc(paper.id)}">
  ${matched ? `<p class="paper-match">Matches ${reasons}</p>` : ''}
  <h3 class="paper-title"><a href="${esc(paper.abs || `https://arxiv.org/abs/${paper.id}`)}" target="_blank" rel="noopener">${mark(paper.title, terms)}</a></h3>
  <p class="paper-meta"><span class="paper-authors">${PaperData.highlight(esc(authorLine(paper.authors)), authorTerms, 'hl')}</span><span class="paper-cats">${categories}</span><span class="paper-id">${esc(paper.id)}</span></p>
  ${lead}
  ${more}
  <nav class="paper-links" aria-label="Links for ${esc(paper.id)}">${paperLinks(paper)}</nav>
</article>`;
  }

  function renderSection(title, entries, terms) {
    if (!entries.length) return '';
    return `<section class="paper-section"><h2 class="section-title">${esc(title)} <span class="count">${entries.length}</span></h2>${entries
      .map(e => renderPaper(e.paper, e.match, terms))
      .join('')}</section>`;
  }

  function daySentence(total, matched, hasInterests) {
    const papers = `${total.toLocaleString('en-GB')} new paper${total === 1 ? '' : 's'}`;
    if (!hasInterests) return `${papers}.`;
    if (matched === 0) return `${papers}; none match your interests.`;
    return `${papers}; ${matched} match${matched === 1 ? 'es' : ''} your interests.`;
  }

  function progressText(done, total) {
    if (done === 0) return `Summaries for these ${total.toLocaleString('en-GB')} papers are still being written. Each paper shows its abstract until its summary is ready.`;
    return `Summaries are ready for ${done.toLocaleString('en-GB')} of ${total.toLocaleString('en-GB')} papers. The rest show their abstract until theirs is written.`;
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

  return { formatDay, formatRange, authorLine, matchesFor, renderPaper, renderSection, daySentence, progressText, topicsFor, topicNames };
});
