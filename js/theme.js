/**
 * Colour themes. A reader picks a light theme, a dark theme, and whether the
 * page follows the system or stays light or dark. Loaded in <head> so the
 * theme applies before the page paints, and it follows a system switch while
 * the page is open. The palettes live in css/site.css under
 * :root[data-theme="..."].
 */
/**
 * A reader's choices: the mode ('system', 'light' or 'dark') and the theme id for each.
 * @typedef {{ mode: string, light: string, dark: string }} ThemePrefs
 * @typedef {keyof ThemePrefs} ThemeSlot
 */
(function (root) {
  /** @type {ThemePrefs} */
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
  /** @type {ThemePrefs} */
  const DEFAULTS = { mode: 'system', light: 'preprint', dark: 'lilac' };
  /** @type {Record<ThemeSlot, Array<{ id: string }>>} */
  const CHOICES = { mode: MODES, light: LIGHT, dark: DARK };
  const SLOTS = /** @type {ThemeSlot[]} */ (Object.keys(DEFAULTS));

  /**
   * @param {Array<{ id: string }>} list
   * @param {string | null | undefined} id
   * @param {string} fallback
   * @returns {string}
   */
  function pick(list, id, fallback) {
    return typeof id === 'string' && list.some(item => item.id === id) ? id : fallback;
  }

  /**
   * @param {Pick<Storage, 'getItem'>} storage
   * @returns {ThemePrefs}
   */
  function read(storage) {
    const prefs = { ...DEFAULTS };
    for (const slot of SLOTS) {
      /** @type {string | null} */
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

  /**
   * @param {Pick<Storage, 'setItem' | 'removeItem'>} storage
   * @param {Partial<ThemePrefs>} prefs
   */
  function save(storage, prefs) {
    try {
      for (const slot of SLOTS) {
        const value = pick(CHOICES[slot], prefs[slot], DEFAULTS[slot]);
        if (value === DEFAULTS[slot]) storage.removeItem(KEYS[slot]);
        else storage.setItem(KEYS[slot], value);
      }
    } catch (error) {
      console.error('Could not save the theme:', error);
    }
  }

  /**
   * The theme the page shows for these choices, given whether the system is dark.
   * @param {ThemePrefs} prefs
   * @param {boolean} systemDark
   */
  function resolve(prefs, systemDark) {
    const dark = prefs.mode === 'dark' || (prefs.mode === 'system' && systemDark);
    return dark ? prefs.dark : prefs.light;
  }

  /**
   * @param {Document} doc
   * @param {string} id
   */
  function apply(doc, id) {
    doc.documentElement.dataset.theme = id;
  }

  const api = { KEYS, MODES, LIGHT, DARK, DEFAULTS, read, save, resolve, apply };
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
    return;
  }
  /** @type {Storage | null} */
  let storage = null;
  try {
    storage = root.localStorage;
  } catch (error) {
    storage = null;
  }
  const media = root.matchMedia ? root.matchMedia('(prefers-color-scheme: dark)') : null;
  const systemDark = () => Boolean(media && media.matches);
  /**
   * Show `prefs` (the saved ones by default); Settings uses it to preview.
   * @param {ThemePrefs} [prefs]
   */
  const show = prefs => apply(root.document, resolve(prefs || (storage ? read(storage) : DEFAULTS), systemDark()));
  root.Theme = Object.assign(api, { show });
  show();
  if (media && media.addEventListener) media.addEventListener('change', () => show());
})(typeof self !== 'undefined' ? self : this);
