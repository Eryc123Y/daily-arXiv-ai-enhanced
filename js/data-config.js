/**
 * Data source configuration.
 *
 * On GitHub Pages (<owner>.github.io/<repo>/) the page reads the `data`
 * branch of the repository it is served from, so a fork needs no edits.
 * Anywhere else (local preview, your own server, a custom domain) it uses
 * FALLBACK_REPO below; change it there when you host the page yourself.
 */
(function (root) {
  const FALLBACK_REPO = { owner: 'Eryc123Y', repo: 'daily-arXiv-ai-enhanced' };

  function repoFromLocation(location, fallback) {
    const host = ((location && location.hostname) || '').toLowerCase();
    if (!host.endsWith('.github.io')) return fallback;
    const owner = host.slice(0, -'.github.io'.length);
    const first = ((location && location.pathname) || '').split('/').filter(Boolean)[0];
    return { owner, repo: first && !first.includes('.') ? first : `${owner}.github.io` };
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { repoFromLocation };
    return;
  }

  const repo = repoFromLocation(root.location, FALLBACK_REPO);

  root.DATA_CONFIG = {
    repoOwner: repo.owner,
    repoName: repo.repo,

    /** Branch holding data/*.jsonl, assets/file-list.txt and assets/site.json */
    dataBranch: 'data',

    /**
     * Categories crawled, used to group cross-lists as "Other fields" when
     * the data branch has no assets/site.json yet.
     */
    mainCategories: ['cs.CV', 'cs.AI', 'cs.LG', 'cs.CL', 'stat.ML', 'cs.GR'],

    /** Main "Open on ..." button in the reading pane: 'alphaxiv' or 'arxiv' */
    primaryLink: 'alphaxiv',

    getDataBaseUrl() {
      return `https://raw.githubusercontent.com/${this.repoOwner}/${this.repoName}/${this.dataBranch}`;
    },

    getDataUrl(filePath) {
      return `${this.getDataBaseUrl()}/${filePath}`;
    },

    repoUrl() {
      return `https://github.com/${this.repoOwner}/${this.repoName}`;
    },
  };

  root.document.addEventListener('DOMContentLoaded', () => {
    root.document.querySelectorAll('a[data-repo-link]').forEach(link => {
      link.href = root.DATA_CONFIG.repoUrl();
    });
  });
})(typeof self !== 'undefined' ? self : this);
