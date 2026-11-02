/**
 * Colour themes. Loaded in <head> so the saved theme applies before the page
 * paints. "auto" sets no attribute and follows the system: Preprint by day,
 * Lamplight by night. The palettes themselves live in css/site.css under
 * :root[data-theme="..."].
 */
(function (root) {
  const KEY = 'daily-arxiv-theme';
  const THEMES = [
    { id: 'auto', name: 'Match the system', note: 'Preprint by day, Lamplight by night' },
    { id: 'preprint', name: 'Preprint', note: 'White paper, blue-black ink, arXiv red' },
    { id: 'lamplight', name: 'Lamplight', note: 'Warm dark with amber links, for late reading' },
    { id: 'anaglyph', name: 'Anaglyph', note: 'Blue-black with the red and cyan of stereo glasses' },
    { id: 'graphite', name: 'Graphite', note: 'Quiet greys and one cobalt accent' },
  ];

  function valid(id) {
    return THEMES.some(theme => theme.id === id) ? id : 'auto';
  }

  function read(storage) {
    try {
      return valid(storage.getItem(KEY));
    } catch (error) {
      return 'auto';
    }
  }

  function save(storage, id) {
    try {
      if (valid(id) === 'auto') storage.removeItem(KEY);
      else storage.setItem(KEY, id);
    } catch (error) {
      console.error('Could not save the theme:', error);
    }
  }

  function apply(doc, id) {
    if (valid(id) === 'auto') delete doc.documentElement.dataset.theme;
    else doc.documentElement.dataset.theme = id;
  }

  const api = { KEY, THEMES, valid, read, save, apply };
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
    return;
  }
  root.Theme = api;
  let storage = null;
  try {
    storage = root.localStorage;
  } catch (error) {
    storage = null;
  }
  if (storage) apply(root.document, read(storage));
})(typeof self !== 'undefined' ? self : this);
