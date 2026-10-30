/**
 * Daily arXiv reading page: loads a day (or a range of days) from the data
 * branch, merges raw papers with their summaries, and renders them with
 * interest matches first. Keyword and author lists live in localStorage
 * under the same keys upstream used.
 */
const KEYWORDS_KEY = 'preferredKeywords';
const AUTHORS_KEY = 'preferredAuthors';
const PULL_KEY = 'pullMatchesFirst';
const PREFERRED_LANGUAGES = ['English', 'Chinese'];

const state = {
  days: [],
  languages: new Map(),
  records: [],
  category: 'all',
  topic: 'all',
  topics: [],
  query: '',
  keywords: [],
  authors: [],
  pullMatches: true,
};

const $ = id => document.getElementById(id);

function readList(key, fallback) {
  try {
    const saved = localStorage.getItem(key);
    return saved ? JSON.parse(saved) : fallback;
  } catch (error) {
    return fallback;
  }
}

function writeList(key, list) {
  try {
    localStorage.setItem(key, JSON.stringify(list));
  } catch (error) {
    console.error('Could not save to localStorage:', error);
  }
}

function defaultKeywords() {
  return window.INTEREST_PRESETS ? [...INTEREST_PRESETS.keywords] : [];
}

function loadPreferences() {
  state.keywords = readList(KEYWORDS_KEY, defaultKeywords());
  state.topics = Render.topicsFor(state.keywords, window.INTEREST_PRESETS);
  state.authors = readList(AUTHORS_KEY, []);
  state.pullMatches = readList(PULL_KEY, true) !== false;
  $('pullMatches').checked = state.pullMatches;
}

// --- Data -------------------------------------------------------------------

async function fetchText(path) {
  try {
    const response = await fetch(DATA_CONFIG.getDataUrl(path), { cache: 'no-cache' });
    return response.ok ? await response.text() : '';
  } catch (error) {
    console.error('Fetch failed:', path, error);
    return '';
  }
}

function summaryLanguage(day) {
  const available = state.languages.get(day) || [];
  return PREFERRED_LANGUAGES.find(l => available.includes(l)) || available[0] || PREFERRED_LANGUAGES[0];
}

async function loadDay(day) {
  const [raw, ai] = await Promise.all([
    fetchText(`data/${day}.jsonl`),
    fetchText(`data/${day}_AI_enhanced_${summaryLanguage(day)}.jsonl`),
  ]);
  return PaperData.mergeDay(raw, ai).map(record => ({ ...record, date: day }));
}

async function loadDays(days) {
  const perDay = await Promise.all(days.map(loadDay));
  return perDay.flat();
}

// --- Rendering --------------------------------------------------------------

function selectedDays() {
  const end = $('daySelect').value;
  if (!$('rangeToggle').checked) return [end];
  const start = $('daySelectStart').value;
  const [from, to] = start <= end ? [start, end] : [end, start];
  return state.days.filter(d => d >= from && d <= to).sort();
}

const OTHER_FIELDS = 'other';

function categoryOf(record) {
  const primary = (record.categories || [])[0];
  return DATA_CONFIG.mainCategories.includes(primary) ? primary : OTHER_FIELDS;
}

function inTopic(record) {
  if (state.topic === 'all') return true;
  const match = Render.matchesFor(record, state.keywords, state.authors);
  if (state.topic === 'authors') return match.authors.length > 0;
  return Render.topicNames(match, state.topics).includes(state.topic);
}

function visibleRecords() {
  const q = state.query.trim().toLowerCase();
  return state.records.filter(r => {
    if (state.category !== 'all' && categoryOf(r) !== state.category) return false;
    if (!inTopic(r)) return false;
    if (!q) return true;
    const ai = r.pending ? {} : r.AI || {};
    return [r.title, r.summary, (r.authors || []).join(', '), r.id, ...Object.values(ai)]
      .join(' ')
      .toLowerCase()
      .includes(q);
  });
}

function filterButton(kind, value, label, count, active) {
  return `<li><button type="button" data-${kind}="${PaperData.escapeHtml(value)}" aria-pressed="${active === value}">` +
    `<span>${PaperData.escapeHtml(label)}</span><span class="count">${count}</span></button></li>`;
}

function renderCategories() {
  const counts = new Map();
  state.records.forEach(r => counts.set(categoryOf(r), (counts.get(categoryOf(r)) || 0) + 1));
  const main = DATA_CONFIG.mainCategories.filter(c => counts.has(c)).sort((a, b) => counts.get(b) - counts.get(a));
  const items = [
    filterButton('category', 'all', 'All categories', state.records.length, state.category),
    ...main.map(c => filterButton('category', c, c, counts.get(c), state.category)),
  ];
  if (counts.has(OTHER_FIELDS)) {
    items.push(filterButton('category', OTHER_FIELDS, 'Other fields (cross-lists)', counts.get(OTHER_FIELDS), state.category));
  }
  $('categoryList').innerHTML = items.join('');
}

function renderTopics() {
  const counts = new Map(state.topics.map(t => [t.name, 0]));
  let authorCount = 0;
  state.records.forEach(r => {
    const match = Render.matchesFor(r, state.keywords, state.authors);
    Render.topicNames(match, state.topics).forEach(name => counts.set(name, counts.get(name) + 1));
    if (match.authors.length) authorCount += 1;
  });
  const items = [
    filterButton('topic', 'all', 'All papers', state.records.length, state.topic),
    ...state.topics.map(t => filterButton('topic', t.name, t.name, counts.get(t.name), state.topic)),
  ];
  if (state.authors.length) items.push(filterButton('topic', 'authors', 'Your authors', authorCount, state.topic));
  $('topicList').innerHTML = items.join('');
}

function renderInterestSummary(matchedCount) {
  const k = state.keywords.length;
  const a = state.authors.length;
  $('interestSummary').innerHTML = k + a === 0
    ? 'No keywords or authors set. <button type="button" class="link-button" data-open-settings>Add some</button>'
    : `${k} keyword${k === 1 ? '' : 's'}${a ? ` and ${a} author${a === 1 ? '' : 's'}` : ''}; ${matchedCount} paper${matchedCount === 1 ? '' : 's'} match today. <button type="button" class="link-button" data-open-settings>Edit</button>`;
}

function renderHead(days) {
  const total = state.records.length;
  const done = state.records.filter(r => !r.pending).length;
  const matched = state.records.filter(r => {
    const match = Render.matchesFor(r, state.keywords, state.authors);
    return match.keywords.length + match.authors.length > 0;
  }).length;
  $('dayTitle').textContent = Render.formatRange(days[0], days[days.length - 1]);
  $('daySentence').textContent = total ? Render.daySentence(total, matched, state.keywords.length + state.authors.length > 0) : '';
  const pending = total > 0 && done < total;
  $('progress').hidden = !pending;
  if (pending) {
    $('progressFill').style.width = `${Math.round((100 * done) / total)}%`;
    $('progressText').textContent = Render.progressText(done, total);
  }
  renderInterestSummary(matched);
}

function renderList() {
  const terms = state.keywords;
  const entries = visibleRecords().map((paper, index) => {
    const match = Render.matchesFor(paper, state.keywords, state.authors);
    return { paper, match, index, score: match.keywords.length + 2 * match.authors.length };
  });
  const list = $('paperList');
  if (!state.records.length) {
    list.innerHTML = `<p class="empty">No papers were published for this day. arXiv makes no announcement on Friday and Saturday nights or on holidays; pick another day above.</p>`;
    return;
  }
  if (!entries.length) {
    list.innerHTML = `<p class="empty">No papers match "${PaperData.escapeHtml(state.query)}" in this view. Clear the search or choose All categories.</p>`;
    return;
  }
  if (!state.pullMatches) {
    list.innerHTML = Render.renderSection('Papers', entries, terms);
    return;
  }
  const matched = entries.filter(e => e.score > 0).sort((a, b) => b.score - a.score || a.index - b.index);
  const rest = entries.filter(e => e.score === 0);
  list.innerHTML = Render.renderSection('Matches your interests', matched, terms) +
    Render.renderSection(matched.length ? 'Everything else' : 'Papers', rest, terms);
}

function render(days) {
  renderHead(days);
  renderTopics();
  renderCategories();
  renderList();
}

// --- URL JSON mode (used by SKILL/scripts/fetch.sh) -------------------------

function jsonParams() {
  const params = new URLSearchParams(window.location.search);
  const list = name => (params.get(name) ? params.get(name).split(',').map(s => s.trim()).filter(Boolean) : null);
  const category = params.get('category') || params.get('json');
  const keywords = list('keywords');
  const authors = list('author');
  return category || keywords || authors ? { category: category || 'all', keywords, authors } : null;
}

function outputJson(params, records) {
  const papers = records
    .filter(r => params.category === 'all' || (r.categories || [])[0] === params.category)
    .map(r => ({ r, m: Render.matchesFor(r, params.keywords || [], params.authors || []) }))
    .filter(({ m }) => (!params.keywords && !params.authors) || m.keywords.length + m.authors.length > 0)
    .map(({ r, m }) => ({
      id: r.id,
      title: r.title,
      authors: (r.authors || []).join(', '),
      categories: r.categories,
      summary: r.pending ? r.summary : r.AI.tldr,
      date: r.date,
      url: r.abs || `https://arxiv.org/abs/${r.id}`,
      reason: [...m.keywords.map(k => `keyword: ${k}`), ...m.authors.map(a => `author: ${a}`)].join(' | ') || null,
    }));
  document.head.innerHTML = '';
  document.body.textContent = JSON.stringify(
    { category: params.category, author: params.authors, keywords: params.keywords, count: papers.length, papers },
    null,
    2
  );
}

// --- Controls ---------------------------------------------------------------

function fillDaySelects() {
  const options = state.days
    .map(d => `<option value="${d}">${Render.formatDay(d, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</option>`)
    .join('');
  $('daySelect').innerHTML = options;
  $('daySelectStart').innerHTML = options;
  const start = state.days[Math.min(4, state.days.length - 1)];
  if (start) $('daySelectStart').value = start;
}

async function showSelection() {
  const days = selectedDays();
  if (!days.length) return;
  $('paperList').innerHTML = '<p class="empty">Loading papers…</p>';
  state.records = await loadDays(days);
  state.category = 'all';
  state.topic = 'all';
  render(days);
  const hash = new URLSearchParams({ day: days[days.length - 1], ...(days.length > 1 ? { from: days[0] } : {}) });
  history.replaceState(null, '', `#${hash}`);
}

function openSettings() {
  $('keywordsInput').value = state.keywords.join('\n');
  $('authorsInput').value = state.authors.join('\n');
  $('settings').showModal();
}

function bindEvents() {
  $('daySelect').addEventListener('change', showSelection);
  $('daySelectStart').addEventListener('change', showSelection);
  $('rangeToggle').addEventListener('change', () => {
    $('rangeStart').hidden = !$('rangeToggle').checked;
    $('dayLabel').hidden = $('rangeToggle').checked;
    showSelection();
  });
  $('search').addEventListener('input', event => {
    state.query = event.target.value;
    renderList();
  });
  $('pullMatches').addEventListener('change', event => {
    state.pullMatches = event.target.checked;
    writeList(PULL_KEY, state.pullMatches);
    renderList();
  });
  $('categoryList').addEventListener('click', event => {
    const button = event.target.closest('button[data-category]');
    if (!button) return;
    state.category = button.dataset.category;
    renderCategories();
    renderList();
  });
  $('topicList').addEventListener('click', event => {
    const button = event.target.closest('button[data-topic]');
    if (!button) return;
    state.topic = button.dataset.topic;
    renderTopics();
    renderList();
  });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-open-settings]')) openSettings();
  });
  $('openSettings').addEventListener('click', openSettings);
  $('resetSettings').addEventListener('click', () => {
    $('keywordsInput').value = defaultKeywords().join('\n');
  });
  $('settings').addEventListener('close', () => {
    if ($('settings').returnValue !== 'save') return;
    const lines = id => [...new Set($(id).value.split('\n').map(s => s.trim()).filter(Boolean))];
    state.keywords = lines('keywordsInput');
    state.authors = lines('authorsInput');
    state.topics = Render.topicsFor(state.keywords, window.INTEREST_PRESETS);
    state.topic = 'all';
    writeList(KEYWORDS_KEY, state.keywords);
    writeList(AUTHORS_KEY, state.authors);
    render(selectedDays());
  });
}

function restoreFromHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  const day = params.get('day');
  const from = params.get('from');
  if (day && state.days.includes(day)) $('daySelect').value = day;
  if (from && state.days.includes(from)) {
    $('daySelectStart').value = from;
    $('rangeToggle').checked = true;
    $('rangeStart').hidden = false;
    $('dayLabel').hidden = true;
  }
}

async function init() {
  loadPreferences();
  const listText = await fetchText('assets/file-list.txt');
  const fileList = PaperData.parseFileList(listText);
  state.days = fileList.dates;
  state.languages = fileList.languages;
  if (!state.days.length) {
    $('dayTitle').textContent = 'No days available';
    $('paperList').innerHTML = '<p class="empty">The list of days could not be loaded from GitHub. Check your connection and reload the page.</p>';
    return;
  }
  const params = jsonParams();
  if (params) {
    outputJson(params, await loadDay(state.days[0]));
    return;
  }
  fillDaySelects();
  restoreFromHash();
  bindEvents();
  await showSelection();
}

document.addEventListener('DOMContentLoaded', init);
