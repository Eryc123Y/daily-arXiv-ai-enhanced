/**
 * Daily arXiv reading page (three panes): topics and filters, the paper list,
 * and the selected paper. Data comes from window.DataSource; keyword and
 * author lists live in localStorage under the keys upstream used.
 */
const KEYWORDS_KEY = 'preferredKeywords';
const AUTHORS_KEY = 'preferredAuthors';
const OTHER_FIELDS = 'other';
const PHONE = window.matchMedia('(max-width: 760px)');

const state = {
  days: [],
  records: [],
  info: new Map(),
  topics: [],
  keywords: [],
  authors: [],
  topic: null,
  category: 'all',
  query: '',
  selectedId: null,
  mainCategories: [],
  visible: [],
};

const $ = id => document.getElementById(id);
const esc = text => PaperData.escapeHtml(text);

// --- Preferences --------------------------------------------------------------

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
  state.authors = readList(AUTHORS_KEY, []);
  state.topics = Render.topicsFor(state.keywords, window.INTEREST_PRESETS);
}

function describeAll() {
  state.info = new Map(state.records.map(r => [r.id, Render.describe(r, state.keywords, state.authors, state.topics)]));
}

// --- Filtering ----------------------------------------------------------------

function categoryOf(record) {
  const primary = (record.categories || [])[0];
  return state.mainCategories.includes(primary) ? primary : OTHER_FIELDS;
}

function inTopic(record, topic) {
  const info = state.info.get(record.id);
  if (topic === 'all') return true;
  if (topic === 'matches') return info.matched;
  if (topic === 'authors') return info.match.authors.length > 0;
  return info.topics.some(t => t.name === topic);
}

function matchesQuery(record, query) {
  if (!query) return true;
  const ai = record.pending ? {} : record.AI || {};
  return [record.title, record.summary, (record.authors || []).join(', '), record.id, ...Object.values(ai)]
    .join(' ')
    .toLowerCase()
    .includes(query);
}

function computeVisible() {
  const query = state.query.trim().toLowerCase();
  state.visible = state.records
    .map((record, index) => ({ record, index, info: state.info.get(record.id) }))
    .filter(e => inTopic(e.record, state.topic))
    .filter(e => state.category === 'all' || categoryOf(e.record) === state.category)
    .filter(e => matchesQuery(e.record, query))
    .sort((a, b) => b.info.score - a.info.score || a.index - b.index);
}

function topicLabel(topic) {
  if (topic === 'matches') return 'Interest matches';
  if (topic === 'authors') return 'Your authors';
  if (topic === 'all') return 'All papers';
  return topic;
}

// --- Rendering ----------------------------------------------------------------

function filterItem(kind, key, label, count, active, colourIndex) {
  const dot = colourIndex === undefined ? '' : `<span class="dot topic-${colourIndex}"></span>`;
  return `<li><button type="button" data-${kind}="${esc(key)}" aria-pressed="${active === key}">${dot}<span class="label">${esc(label)}</span><span class="count">${count}</span></button></li>`;
}

function renderNav(days) {
  const total = state.records.length;
  const done = state.records.filter(r => !r.pending).length;
  const matched = state.records.filter(r => state.info.get(r.id).matched).length;
  $('dayTitle').textContent = days.length ? Render.formatRange(days[0], days[days.length - 1]) : 'No day selected';
  $('daySentence').textContent = total ? Render.daySentence(total, matched, state.keywords.length + state.authors.length > 0) : '';
  const pending = total > 0 && done < total;
  $('progress').hidden = !pending;
  if (pending) {
    $('progressFill').style.width = `${Math.round((100 * done) / total)}%`;
    $('progressText').textContent = Render.progressText(done, total);
  }

  const count = topic => state.records.filter(r => inTopic(r, topic)).length;
  const topics = [filterItem('topic', 'matches', 'Interest matches', matched, state.topic)];
  state.topics.forEach((t, i) => topics.push(filterItem('topic', t.name, t.name, count(t.name), state.topic, i)));
  if (state.authors.length) topics.push(filterItem('topic', 'authors', 'Your authors', count('authors'), state.topic, 'author'));
  topics.push(filterItem('topic', 'all', 'All papers', total, state.topic));
  $('topicList').innerHTML = topics.join('');

  const counts = new Map();
  state.records.forEach(r => counts.set(categoryOf(r), (counts.get(categoryOf(r)) || 0) + 1));
  const main = state.mainCategories.filter(c => counts.has(c)).sort((a, b) => counts.get(b) - counts.get(a));
  const chips = [filterItem('category', 'all', 'All', total, state.category)];
  main.forEach(c => chips.push(filterItem('category', c, c, counts.get(c), state.category)));
  if (counts.has(OTHER_FIELDS)) chips.push(filterItem('category', OTHER_FIELDS, 'Other fields', counts.get(OTHER_FIELDS), state.category));
  $('categoryList').innerHTML = chips.join('');
}

function renderList() {
  computeVisible();
  const scope = state.category === 'all' ? topicLabel(state.topic) : `${topicLabel(state.topic)} in ${state.category === OTHER_FIELDS ? 'other fields' : state.category}`;
  $('listHeading').innerHTML = `${esc(scope)} <span class="count">${state.visible.length}</span>`;
  $('listNote').textContent = state.topic === 'all' && state.visible.length ? 'Interest matches first' : '';
  if (!state.records.length) {
    $('paperList').innerHTML = '<li class="empty">No papers were published for this day. arXiv makes no announcement on Friday and Saturday nights or on holidays; choose another day above.</li>';
    renderReader();
    return;
  }
  if (!state.visible.length) {
    $('paperList').innerHTML = state.query
      ? `<li class="empty">No papers match "${esc(state.query)}" here. Clear the search or choose All papers.</li>`
      : '<li class="empty">No papers in this topic today. Choose All papers to see everything.</li>';
    renderReader();
    return;
  }
  if (!state.visible.some(e => e.record.id === state.selectedId) && !PHONE.matches) {
    state.selectedId = state.visible[0].record.id;
  }
  $('paperList').innerHTML = state.visible.map(e => Render.renderRow(e.record, e.info, e.record.id === state.selectedId)).join('');
  renderReader();
}

function renderReader() {
  const position = state.visible.findIndex(e => e.record.id === state.selectedId);
  const entry = state.visible[position];
  if (!entry) {
    $('readerContent').innerHTML = '<p class="empty">Choose a paper from the list to read its summary.</p>';
    $('prevPaper').disabled = true;
    $('nextPaper').disabled = true;
    return;
  }
  $('readerContent').innerHTML = Render.renderReader(entry.record, entry.info, state.keywords);
  $('prevPaper').disabled = position <= 0;
  $('nextPaper').disabled = position >= state.visible.length - 1;
  $('reader').scrollTop = 0;
}

function renderAll(days) {
  renderNav(days);
  renderList();
}

// --- Selection and navigation ------------------------------------------------

function select(id, { open = true } = {}) {
  state.selectedId = id;
  document.querySelectorAll('.row.is-selected').forEach(b => {
    b.classList.remove('is-selected');
    b.removeAttribute('aria-current');
  });
  const button = document.querySelector(`.row[data-id="${CSS.escape(id)}"]`);
  if (button) {
    button.classList.add('is-selected');
    button.setAttribute('aria-current', 'true');
    button.scrollIntoView({ block: 'nearest' });
  }
  renderReader();
  if (open && PHONE.matches) document.body.classList.add('reader-open');
  writeHash();
}

function move(delta) {
  if (!state.visible.length) return;
  const position = state.visible.findIndex(e => e.record.id === state.selectedId);
  const next = Math.min(state.visible.length - 1, Math.max(0, position + delta));
  select(state.visible[next].record.id, { open: document.body.classList.contains('reader-open') });
}

function closeReader() {
  document.body.classList.remove('reader-open');
  const button = document.querySelector('.row.is-selected');
  if (button) button.focus();
}

// --- Days and the URL ---------------------------------------------------------

function selectedDays() {
  const end = $('daySelect').value;
  if (!$('rangeToggle').checked) return [end];
  const start = $('daySelectStart').value;
  const [from, to] = start <= end ? [start, end] : [end, start];
  return state.days.filter(d => d >= from && d <= to).sort();
}

function writeHash() {
  const days = selectedDays();
  const params = new URLSearchParams({ day: days[days.length - 1] });
  if (days.length > 1) params.set('from', days[0]);
  if (state.topic && state.topic !== 'matches') params.set('topic', state.topic);
  if (state.selectedId) params.set('paper', state.selectedId);
  history.replaceState(null, '', `#${params}`);
}

function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  const day = params.get('day');
  const from = params.get('from');
  if (day && state.days.includes(day)) $('daySelect').value = day;
  if (from && state.days.includes(from)) {
    $('daySelectStart').value = from;
    $('rangeToggle').checked = true;
    $('rangeStart').hidden = false;
  }
  state.topic = params.get('topic');
  state.selectedId = params.get('paper');
}

function updateDayButtons() {
  const index = state.days.indexOf($('daySelect').value);
  $('prevDay').disabled = index >= state.days.length - 1;
  $('nextDay').disabled = index <= 0;
}

async function showSelection({ keepTopic = false } = {}) {
  const days = selectedDays();
  updateDayButtons();
  if (!days.length) return;
  $('paperList').innerHTML = '<li class="empty">Loading papers…</li>';
  state.records = (await Promise.all(days.map(d => DataSource.loadDay(d)))).flat();
  describeAll();
  const anyMatch = state.records.some(r => state.info.get(r.id).matched);
  const known = ['matches', 'all', 'authors', ...state.topics.map(t => t.name)];
  if (!keepTopic || !known.includes(state.topic)) state.topic = anyMatch ? 'matches' : 'all';
  state.category = 'all';
  renderAll(days);
  writeHash();
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

// --- Events -------------------------------------------------------------------

function openSettings() {
  $('keywordsInput').value = state.keywords.join('\n');
  $('authorsInput').value = state.authors.join('\n');
  $('settings').showModal();
}

function isTyping(target) {
  return target instanceof Element && Boolean(target.closest('input, textarea, select, dialog[open]'));
}

function bindEvents() {
  $('daySelect').addEventListener('change', () => showSelection());
  $('daySelectStart').addEventListener('change', () => showSelection());
  $('rangeToggle').addEventListener('change', () => {
    $('rangeStart').hidden = !$('rangeToggle').checked;
    showSelection();
  });
  $('prevDay').addEventListener('click', () => {
    $('daySelect').selectedIndex = Math.min($('daySelect').options.length - 1, $('daySelect').selectedIndex + 1);
    showSelection();
  });
  $('nextDay').addEventListener('click', () => {
    $('daySelect').selectedIndex = Math.max(0, $('daySelect').selectedIndex - 1);
    showSelection();
  });
  $('search').addEventListener('input', event => {
    state.query = event.target.value;
    renderList();
  });
  $('topicList').addEventListener('click', event => {
    const button = event.target.closest('button[data-topic]');
    if (!button) return;
    state.topic = button.dataset.topic;
    renderNav(selectedDays());
    renderList();
    writeHash();
  });
  $('categoryList').addEventListener('click', event => {
    const button = event.target.closest('button[data-category]');
    if (!button) return;
    state.category = button.dataset.category;
    renderNav(selectedDays());
    renderList();
  });
  $('paperList').addEventListener('click', event => {
    const button = event.target.closest('button.row');
    if (button) select(button.dataset.id);
  });
  $('prevPaper').addEventListener('click', () => move(-1));
  $('nextPaper').addEventListener('click', () => move(1));
  $('closeReader').addEventListener('click', closeReader);
  document.addEventListener('keydown', event => {
    if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
    if (event.key === 'j') move(1);
    else if (event.key === 'k') move(-1);
    else if (event.key === 'Escape' && document.body.classList.contains('reader-open')) closeReader();
    else if (event.key === '/') {
      event.preventDefault();
      $('search').focus();
    }
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
    writeList(KEYWORDS_KEY, state.keywords);
    writeList(AUTHORS_KEY, state.authors);
    describeAll();
    renderAll(selectedDays());
  });
}

async function init() {
  loadPreferences();
  const { days, categories } = await DataSource.listDays();
  state.days = days;
  state.mainCategories = categories || DATA_CONFIG.mainCategories;
  if (!days.length) {
    $('dayTitle').textContent = 'No papers yet';
    $('paperList').innerHTML = `<li class="empty">Nothing has been published to the data branch of ${esc(DATA_CONFIG.repoOwner)}/${esc(DATA_CONFIG.repoName)} yet, or it could not be reached. On a new fork, run the arXiv-daily-ai-enhanced workflow from the Actions tab; the first day appears a few minutes after it finishes.</li>`;
    return;
  }
  const params = jsonParams();
  if (params) {
    outputJson(params, await DataSource.loadDay(days[0]));
    return;
  }
  const options = days
    .map(d => `<option value="${d}">${Render.formatDay(d, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</option>`)
    .join('');
  $('daySelect').innerHTML = options;
  $('daySelectStart').innerHTML = options;
  $('daySelectStart').value = days[Math.min(4, days.length - 1)];
  readHash();
  bindEvents();
  await showSelection({ keepTopic: Boolean(state.topic) });
}

document.addEventListener('DOMContentLoaded', init);
