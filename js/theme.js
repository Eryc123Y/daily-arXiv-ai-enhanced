/**
 * Colour themes. A reader picks a light theme, a dark theme, and whether the
 * page follows the system or stays light or dark. Loaded in <head> so the
 * theme applies before the page paints, and it follows a system switch while
 * the page is open. The palettes live in css/site.css under
 * :root[data-theme="..."].
 */
(function (root) {
  const KEYS = { mode: 'daily-arxiv-appearance', light: 'daily-arxiv-light-theme', dark: 'daily-arxiv-dark-theme' };
  const MODES = [
    { id: 'system', name: 'Follow the system' },
    { id: 'light', name: 'Always light' },
    { id: 'dark', name: 'Always dark' },
  ];
  const LIGHT = [
    { id: 'preprint', name: 'Preprint', note: 'White paper, blue-black ink, arXiv red' },
    { id: 'graphite', name: 'Graphite', note: 'Quiet greys and one cobalt accent' },
  ];
  const DARK = [
    { id: 'lilac', name: 'Lilac', note: 'Deep violet with lilac links and soft pastels' },
    { id: 'lamplight', name: 'Lamplight', note: 'Warm dark with amber links' },
    { id: 'anaglyph', name: 'Anaglyph', note: 'Blue-black with the red and cyan of stereo glasses' },
  ];
  const DEFAULTS = { mode: 'system', light: 'preprint', dark: 'lilac' };
  const CHOICES = { mode: MODES, light: LIGHT, dark: DARK };

  function pick(list, id, fallback) {
    return list.some(item => item.id === id) ? id : fallback;
  }

  function read(storage) {
    const prefs = {};
    for (const slot of Object.keys(DEFAULTS)) {
      let saved = null;
      try {
        saved = storage.getItem(KEYS[slot]);
      } catch (error) {
        saved = null;
      }
      prefs[slot] = pick(CHOICES[slot], saved, DEFAULTS[slot]);
    }
    return prefs;
  }

  function save(storage, prefs) {
    try {
      for (const slot of Object.keys(DEFAULTS)) {
        const value = pick(CHOICES[slot], prefs[slot], DEFAULTS[slot]);
        if (value === DEFAULTS[slot]) storage.removeItem(KEYS[slot]);
        else storage.setItem(KEYS[slot], value);
      }
    } catch (error) {
      console.error('Could not save the theme:', error);
    }
  }

  /** The theme the page shows for these choices, given whether the system is dark. */
  function resolve(prefs, systemDark) {
    const dark = prefs.mode === 'dark' || (prefs.mode === 'system' && systemDark);
    return dark ? prefs.dark : prefs.light;
  }

  function apply(doc, id) {
    doc.documentElement.dataset.theme = id;
  }

  const api = { KEYS, MODES, LIGHT, DARK, DEFAULTS, read, save, resolve, apply };
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
  const media = root.matchMedia ? root.matchMedia('(prefers-color-scheme: dark)') : null;
  const systemDark = () => Boolean(media && media.matches);
  /** Show `prefs` (the saved ones by default); Settings uses it to preview. */
  api.show = prefs => apply(root.document, resolve(prefs || (storage ? read(storage) : DEFAULTS), systemDark()));
  api.show();
  if (media && media.addEventListener) media.addEventListener('change', () => api.show());
})(typeof self !== 'undefined' ? self : this);
