/**
 * URL JSON mode, for scripts: ?json=<category>&keywords=a,b&author=x prints
 * the newest day's papers (filtered by category, keywords and authors) as
 * JSON instead of the page. Loaded as the global `JsonMode`.
 */
(function (root) {
  /** The request in the query string, or null when it asks for the page. */
  function params(search) {
    const query = new URLSearchParams(search);
    const list = name => (query.get(name) ? query.get(name).split(',').map(s => s.trim()).filter(Boolean) : null);
    const category = query.get('category') || query.get('json');
    const keywords = list('keywords');
    const authors = list('author');
    return category || keywords || authors ? { category: category || 'all', keywords, authors } : null;
  }

  function output(request, records) {
    const papers = records
      .filter(r => request.category === 'all' || (r.categories || [])[0] === request.category)
      .map(r => ({ r, m: Render.matchesFor(r, request.keywords || [], request.authors || []) }))
      .filter(({ m }) => (!request.keywords && !request.authors) || m.keywords.length + m.authors.length > 0)
      .map(({ r, m }) => ({
        id: r.id,
        title: r.title,
        authors: (r.authors || []).join(', '),
        categories: r.categories,
        source: Sources.sourceLabel(r),
        summary: r.AI && !r.pending ? r.AI.tldr : r.summary || null,
        date: r.date,
        url: PaperData.isArxiv(r) ? r.abs || `https://arxiv.org/abs/${r.id}` : Sources.safeUrl(r.oa_url) || Sources.publisherUrl(r),
        reason: [...m.keywords.map(k => `keyword: ${k}`), ...m.authors.map(a => `author: ${a}`)].join(' | ') || null,
      }));
    document.head.innerHTML = '';
    document.body.textContent = JSON.stringify(
      { category: request.category, author: request.authors, keywords: request.keywords, count: papers.length, papers },
      null,
      2
    );
  }

  root.JsonMode = { params, output };
})(typeof self !== 'undefined' ? self : this);
