/**
 * Daily arXiv reading page (three panes): topics and filters, the paper list,
 * and the selected paper, in two streams: arXiv papers by day, and journal
 * and conference papers by week (js/streams.js). Data comes from
 * window.DataSource; keyword and author lists live in localStorage under the
 * keys upstream used.
 */
const KEYWORDS_KEY = 'preferredKeywords';
const AUTHORS_KEY = 'preferredAuthors';
const OPEN_ON_KEY = 'daily-arxiv-open-on';
const PHONE = window.matchMedia('(max-width: 760px)');
// Weeks are counted newest first; after this many weeks without a venue paper, the feed is taken never to have run.
const EMPTY_WEEKS_BEFORE_GIVING_UP = 2;

const state = {
  days: [],
  day: null,
  from: null,
  range: false,
  stream: 'arxiv',
  week: null,
  dayRecords: [],
  records: [],
  venueDays: new Map(),
  venueNames: new Map(),
  indexed: false,
  weeks: new Map(),
  groups: [],
  info: new Map(),
  topics: [],
  keywords: [],
  authors: [],
  topic: null,
  category: 'all',
  codeOnly: false,
  freeOnly: false,
  type: 'all',
  area: 'all',
  source: 'all',
  venues: new Map(),
  query: '',
  selectedId: null,
  mainCategories: [],
  visible: [],
  status: null,
};

const $ = id => document.getElementById(id);
const esc = text => PaperData.escapeHtml(text);
let picker = null;

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

function forgetList(key) {
  try {
    localStorage.removeItem(key);
  } catch (error) {
    console.error('Could not update localStorage:', error);
  }
}

/** Saved keywords, unless they are an unchanged copy of a default list. */
function resolveKeywords(saved) {
  if (!window.keywordsFor) return saved || defaultKeywords();
  const { keywords, clearSaved } = keywordsFor(saved);
  if (clearSaved) forgetList(KEYWORDS_KEY);
  return [...keywords];
}

/** Where "Open on ..." goes: this browser's choice, else the site default. */
function primaryLink() {
  const saved = readList(OPEN_ON_KEY, null);
  return saved === 'arxiv' || saved === 'alphaxiv' ? saved : DATA_CONFIG.primaryLink;
}

function loadPreferences() {
  state.keywords = resolveKeywords(readList(KEYWORDS_KEY, null));
  state.authors = readList(AUTHORS_KEY, []);
  state.topics = Render.topicsFor(state.keywords, window.INTEREST_PRESETS);
}

function describeAll() {
  state.info = new Map(state.records.map(r => [r.id, Render.describe(r, state.keywords, state.authors, state.topics)]));
}

// --- Filtering ----------------------------------------------------------------

function activeFilters() {
  const { topic, category, codeOnly, freeOnly, type, area, source, query } = state;
  return { topic, category, codeOnly, freeOnly, type, area, source, query };
}

/** Set the type, area, venue and "Free to read" choices from a filters object. */
function setSourceChoices({ type, area, source, freeOnly }) {
  Object.assign(state, { type, area, source, freeOnly });
}

function currentCounts() {
  return Filters.counts(entries(), activeFilters(), state.mainCategories, state.topics.map(t => t.name), state.venues);
}

function entries() {
  return state.records.map((record, index) => ({ record, index, info: state.info.get(record.id) }));
}

const inVenues = () => state.stream === Streams.VENUES;

/** The list in order: by interest in the arXiv stream; by venue, newest first, in the weekly one. */
function computeVisible() {
  const shown = Filters.apply(entries(), activeFilters(), state.mainCategories, state.venues);
  state.groups = inVenues() ? Streams.venueGroups(shown, state.venues) : [];
  state.visible = inVenues()
    ? state.groups.flatMap(g => g.entries)
    : shown.sort((a, b) => b.info.score - a.info.score || a.index - b.index);
}

function topicLabel(topic) {
  if (topic === 'matches') return 'Interest matches';
  if (topic === 'authors') return 'Your authors';
  if (topic === 'all') return 'All papers';
  return topic;
}

// --- Rendering ----------------------------------------------------------------

/** One chip of a chip list; disabled when it would show nothing, unless it is the active one. */
function chip(kind, key, label, count, active) {
  const disabled = count === 0 && active !== key ? ' disabled' : '';
  return `<li><button type="button" data-${kind}="${esc(key)}" aria-pressed="${active === key}"${disabled}><span class="label">${esc(label)}</span><span class="count">${count}</span></button></li>`;
}

function filterItem(kind, key, label, count, active, colourIndex) {
  const dot = colourIndex === undefined ? '' : `<span class="dot topic-${colourIndex}"></span>`;
  return `<li><button type="button" data-${kind}="${esc(key)}" aria-pressed="${active === key}">${dot}<span class="label">${esc(label)}</span><span class="count">${count}</span></button></li>`;
}

/** One day as two lines, weekday then date; a range on one. */
function dayHeading(days) {
  if (!days.length) return 'No day selected';
  if (days.length > 1) return esc(Render.formatRange(days[0], days[days.length - 1]));
  const weekday = Render.formatDay(days[0], { weekday: 'long' });
  const date = Render.formatDay(days[0], { day: 'numeric', month: 'long', year: 'numeric' });
  return `${esc(weekday)}<br>${esc(date)}`;
}

function renderNav(days) {
  const total = state.records.length;
  const progress = Render.summaryProgress(state.records);
  const matched = state.records.filter(r => state.info.get(r.id).matched).length;
  const hasInterests = state.keywords.length + state.authors.length > 0;
  if (inVenues()) {
    const venueCount = new Set(state.records.map(r => Sources.sourceKey(r))).size;
    $('dayTitle').textContent = Streams.weekRange(state.week);
    $('daySentence').textContent = total ? Streams.weekSentence(total, venueCount, matched, hasInterests) : '';
  } else {
    $('dayTitle').innerHTML = dayHeading(days);
    $('daySentence').textContent = total ? Render.daySentence(total, matched, hasInterests) : '';
  }
  renderStreams(days);
  const pending = progress.done < progress.total;
  $('progress').hidden = !pending;
  if (pending) {
    $('progressFill').style.width = `${Math.round((100 * progress.done) / progress.total)}%`;
    $('progressText').textContent = Render.progressText(progress.done, progress.total, progress);
  }
  renderStatus(days);

  const counts = currentCounts();
  const count = topic => counts.topics.get(topic);
  const topics = [filterItem('topic', 'matches', 'Interest matches', count('matches'), state.topic)];
  state.topics.forEach((t, i) => topics.push(filterItem('topic', t.name, t.name, count(t.name), state.topic, i)));
  if (state.authors.length) topics.push(filterItem('topic', 'authors', 'Your authors', count('authors'), state.topic, 'author'));
  topics.push(filterItem('topic', 'all', 'All papers', count('all'), state.topic));
  $('topicList').innerHTML = topics.join('');
  renderRefine(counts);
  renderSources(counts);
}

/** Type, area and venue rows; the section is hidden when every paper is from arXiv. */
function renderSources(counts) {
  const groups = Filters.sourceGroups(state.records, counts, activeFilters(), state.venues);
  $('sourceFilter').hidden = !groups;
  if (!groups) return;
  const row = (list, options, kind, active) => {
    $(list).innerHTML = options.map(({ key, label, count }) => chip(kind, key, label, count, active)).join('');
  };
  row('typeList', groups.types, 'type', state.type);
  row('areaList', groups.areas, 'area', state.area);
  row('sourceList', groups.venues, 'source', state.source);
  $('areaRow').hidden = !groups.areas.length;
  $('venueRow').hidden = !groups.venues.length;
  ['typeList', 'areaList', 'sourceList'].forEach(id => revealPressed($(id)));
}

/**
 * On a phone a chip row scrolls sideways and starts at its left end after
 * every render; scroll it so the chosen chip is in view. An "All" chip is
 * the default and needs no scrolling.
 */
function revealPressed(list) {
  const pressed = [...list.querySelectorAll('button[aria-pressed="true"]')].find(b => !Object.values(b.dataset).includes('all'));
  if (!pressed || list.scrollWidth <= list.clientWidth) return;
  const box = list.getBoundingClientRect();
  const chipBox = pressed.getBoundingClientRect();
  if (chipBox.left < box.left || chipBox.right > box.right) list.scrollLeft += chipBox.left - box.left - 8;
}

function sourceName(key) {
  const record = state.records.find(r => Sources.sourceKey(r) === key);
  return record ? Sources.sourceLabel(record) : key.replace(/^venue:/, '');
}

const FREE_TITLE = 'arXiv papers, and journal or conference papers with an open-access copy.';

/** "Has code" and the arXiv categories: refinements applied on top of the topic. */
function renderRefine(counts) {
  const totals = new Map();
  state.records.forEach(r => {
    const key = Filters.categoryOf(r, state.mainCategories);
    totals.set(key, (totals.get(key) || 0) + 1);
  });
  const category = (key, label) => chip('category', key, label, counts.categories.get(key) || 0, state.category);
  const free = Filters.hasVenuePapers(state.records)
    ? [`<li><button type="button" data-free aria-pressed="${state.freeOnly}" title="${FREE_TITLE}"><span class="label">Free to read</span><span class="count">${counts.free}</span></button></li>`]
    : [];
  const main = state.mainCategories.filter(c => totals.has(c)).sort((a, b) => totals.get(b) - totals.get(a));
  const categories = inVenues()
    ? []
    : ['<li class="chip-break" aria-hidden="true"></li>', category('all', 'All fields'), ...main.map(c => category(c, c))];
  if (!inVenues() && totals.has(Filters.OTHER_FIELDS)) categories.push(category(Filters.OTHER_FIELDS, 'Other fields'));
  const items = [
    `<li class="chip-code"><button type="button" data-code aria-pressed="${state.codeOnly}" title="Papers whose abstract or comments link a code repository. Links that appear only in the PDF are not seen.">${Render.CODE_ICON}<span class="label">Has code</span><span class="count">${counts.code}</span></button></li>`,
    ...free,
    ...categories,
  ];
  $('refineList').innerHTML = items.join('');
  revealPressed($('refineList'));
}

function renderList() {
  computeVisible();
  const place = state.category === 'all' ? topicLabel(state.topic) : `${topicLabel(state.topic)} in ${state.category === Filters.OTHER_FIELDS ? 'other fields' : state.category}`;
  const scope = [place, ...Filters.refinementPhrases(activeFilters(), sourceName)].join(', ');
  $('listHeading').innerHTML = `${esc(scope)} <span class="count">${state.visible.length}</span>`;
  $('listNote').textContent = !state.visible.length ? '' : inVenues() ? 'By venue, newest first' : state.topic === 'all' ? 'Interest matches first' : '';
  $('clearFilters').hidden = !Filters.isRefined(activeFilters());
  if (!state.records.length) {
    $('paperList').innerHTML = inVenues()
      ? '<li class="empty">No journal or conference papers arrived this week. Choose another week above.</li>'
      : '<li class="empty">No papers were published for this day. arXiv makes no announcement on Friday and Saturday nights or on holidays; choose another day above.</li>';
    renderReader();
    return;
  }
  if (!state.visible.length) {
    $('paperList').innerHTML = state.query
      ? `<li class="empty">No papers match "${esc(state.query)}" here. Clear the search or choose All papers.</li>`
      : Filters.isRefined(activeFilters())
        ? '<li class="empty">No papers in this topic match these refinements. Clear filters to see the whole topic.</li>'
        : `<li class="empty">No papers in this topic ${inVenues() ? 'this week' : 'today'}. Choose All papers to see everything.</li>`;
    renderReader();
    return;
  }
  if (!state.visible.some(e => e.record.id === state.selectedId) && !PHONE.matches) {
    state.selectedId = state.visible[0].record.id;
  }
  const row = e => Render.renderRow(e.record, e.info, e.record.id === state.selectedId);
  $('paperList').innerHTML = inVenues()
    ? state.groups.map(g => Render.groupHead(g) + g.entries.map(row).join('')).join('')
    : state.visible.map(row).join('');
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
  $('readerContent').innerHTML = Render.renderReader(entry.record, entry.info, state.keywords, { primaryLink: primaryLink() });
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

// --- Pipeline status ----------------------------------------------------------

/** "10:41" today, "2 Nov 21:59" on another day, in the reader's time zone. */
function clockTime(iso) {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '';
  const clock = when.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  if (when.toDateString() === new Date().toDateString()) return clock;
  return `${when.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} ${clock}`;
}

/** One line under the day: crawl, summaries and report, for a single selected day. */
function renderStatus(days) {
  const box = $('pipelineStatus');
  if (!state.status || days.length !== 1 || inVenues()) {
    box.hidden = true;
    return;
  }
  const parts = Status.statusParts({ ...state.status, day: days[0], newest: days[0] === state.days[0], time: clockTime });
  box.hidden = !parts.length;
  box.innerHTML = parts
    .map(part => {
      const text = esc(part.text);
      const body = part.href ? `<a href="${esc(part.href)}" target="_blank" rel="noopener">${text}</a>` : text;
      return `<span class="status-part is-${part.tone}">${body}</span>`;
    })
    .join('');
}

// --- Days and the URL ---------------------------------------------------------

function selectedDays() {
  if (!state.day) return [];
  if (!state.range) return [state.day];
  const [from, to] = state.from <= state.day ? [state.from, state.day] : [state.day, state.from];
  return state.days.filter(d => d >= from && d <= to).sort();
}

function writeHash() {
  const days = selectedDays();
  const params = inVenues() ? new URLSearchParams({ stream: Streams.VENUES, week: state.week }) : new URLSearchParams({ day: days[days.length - 1] });
  if (!inVenues() && days.length > 1) params.set('from', days[0]);
  if (state.topic && state.topic !== 'matches') params.set('topic', state.topic);
  if (state.codeOnly) params.set('code', '1');
  if (state.freeOnly) params.set('free', '1');
  if (state.type !== 'all') params.set('type', state.type);
  if (state.area !== 'all') params.set('area', state.area);
  if (state.source.startsWith('venue:')) params.set('venue', state.source.slice('venue:'.length));
  if (state.selectedId) params.set('paper', state.selectedId);
  history.replaceState(null, '', `#${params}`);
}

function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  const day = params.get('day');
  const from = params.get('from');
  if (day && state.days.includes(day)) state.day = day;
  if (from && state.days.includes(from)) {
    state.from = from;
    state.range = true;
    $('rangeToggle').checked = true;
  }
  state.topic = params.get('topic');
  state.codeOnly = params.get('code') === '1';
  state.freeOnly = params.get('free') === '1';
  state.type = params.get('type') || 'all';
  state.area = params.get('area') || 'all';
  state.source = params.get('venue') ? `venue:${params.get('venue')}` : 'all';
  state.selectedId = params.get('paper');
}

/** The top bar: the date button and its calendar, and the ‹ › buttons. */
function updateDayButtons() {
  const venues = inVenues();
  $('rangeToggle').parentElement.hidden = venues;
  $('dayForm').setAttribute('aria-label', venues ? 'Choose a week' : 'Choose a day');
  $('prevDay').setAttribute('aria-label', venues ? 'Previous week' : 'Previous day');
  $('nextDay').setAttribute('aria-label', venues ? 'Next week' : 'Next day');
  const { older, newer } = steps();
  $('prevDay').disabled = !older;
  $('nextDay').disabled = !newer;
  picker.update(Calendar.viewFor({ ...state, venues, selected: selectedDays() }));
}

/** The choices either side of the current one, for the ‹ › buttons. */
function steps() {
  return inVenues() ? Calendar.neighbours([...state.weeks.keys()], state.week) : Calendar.neighbours(state.days, state.day);
}

/** A choice from the date picker: { day }, { start, end } or { week }. */
function pickDays({ day, start, end, week }) {
  if (week) state.week = week;
  else if (start) Object.assign(state, { from: start, day: end });
  else state.day = day;
  showSelection();
}

/** A failed download, shown as a failure with a way to try again, never as an empty day. */
function showLoadError(error, retry) {
  console.error('Could not load data:', error);
  const status = error && error.status;
  const message = !status
    ? "The papers could not be loaded because GitHub's file server could not be reached. Check your connection and try again."
    : status === 404
      ? `The papers could not be loaded: ${error.path} is missing from the data branch (HTTP 404). Choose another day, or try again after the next crawl.`
      : `The papers could not be loaded: GitHub's file server answered HTTP ${status}. Try again in a minute.`;
  state.records = [];
  state.visible = [];
  $('daySentence').textContent = '';
  $('progress').hidden = true;
  $('topicList').innerHTML = '';
  $('refineList').innerHTML = '';
  $('sourceFilter').hidden = true;
  $('listHeading').textContent = 'Papers';
  $('listNote').textContent = '';
  $('clearFilters').hidden = true;
  $('paperList').innerHTML = `<li class="empty load-error" role="alert">${esc(message)}<br><button type="button" class="button-outline" id="loadRetry">Try again</button></li>`;
  $('loadRetry').addEventListener('click', retry, { once: true });
  renderReader();
}

/** The days the current stream shows: the chosen day or days, or the chosen week's files. */
function streamDays() {
  return inVenues() ? Streams.daysInWeek(state.week, state.days) : selectedDays();
}

async function showSelection({ keepTopic = false } = {}) {
  const days = streamDays();
  updateDayButtons();
  if (!days.length && !inVenues()) return;
  $('paperList').innerHTML = '<li class="empty">Loading papers…</li>';
  try {
    state.dayRecords = (await Promise.all(days.map(d => DataSource.loadDay(d)))).flat();
  } catch (error) {
    showLoadError(error, () => showSelection({ keepTopic: true }));
    return;
  }
  state.records = Streams.streamRecords(state.dayRecords, state.stream);
  days.forEach(d => noteVenueDay(d, state.dayRecords.filter(r => r.date === d)));
  describeAll();
  const anyMatch = state.records.some(r => state.info.get(r.id).matched);
  const known = ['matches', 'all', 'authors', ...state.topics.map(t => t.name)];
  if (!keepTopic || !known.includes(state.topic)) state.topic = anyMatch ? 'matches' : 'all';
  state.category = 'all';
  setSourceChoices(Filters.keepValid(activeFilters(), state.records, state.venues));
  renderAll(days);
  writeHash();
}

/**
 * A link to one paper (the daily report's links) opens it, under All papers
 * if its topic hides it; a journal or conference paper opens in the weekly
 * stream, on the week of the day it arrived.
 */
async function openLinkedPaper(id) {
  if (!id) return;
  const venuePaper = !inVenues() && state.dayRecords.find(r => r.id === id && !PaperData.isArxiv(r));
  if (venuePaper) {
    await setStream(Streams.VENUES, Streams.weekOf(venuePaper.date), { paper: id });
  }
  if (!state.records.some(r => r.id === id)) return;
  if (!state.visible.some(e => e.record.id === id)) {
    state.topic = 'all';
    renderAll(streamDays());
  }
  select(id);
}

// --- Streams and weeks ----------------------------------------------------------

/** Remember a day's venue papers (their count, and their venues for the "+ N" line's wording). */
function noteVenueNames(day, names) {
  state.venueNames.set(day, names);
  state.venueDays.set(day, names.length);
}

/** Remember a day's venue papers from records already loaded. */
function noteVenueDay(day, records) {
  noteVenueNames(day, records.filter(r => !PaperData.isArxiv(r)).map(r => r.venue || ''));
  refreshWeeks();
}

function refreshWeeks() {
  state.weeks = Streams.venueWeeks(state.venueDays);
}

/** The week's venue papers, counted from its day files; a day that cannot be read counts as unknown. */
async function countWeek(monday) {
  const days = Streams.daysInWeek(monday, state.days);
  const lists = await Promise.all(days.map(d => DataSource.venuePapers(d).catch(() => null)));
  days.forEach((d, i) => {
    if (lists[i]) noteVenueNames(d, lists[i]);
  });
  return lists.reduce((n, list) => n + (list ? list.length : 0), 0);
}

/**
 * Which weeks have venue papers: from assets/venue-days.json when the
 * branch has it. Without it (an older fork), weeks are counted from the day
 * files newest first until the first empty week before one with papers (the
 * feed runs every day, so that is where it started), or until a few empty
 * weeks in a row when none has any.
 */
async function discoverWeeks() {
  if (!state.indexed) await countWeeks();
  refreshWeeks();
  updateDayButtons();
  renderStreams(streamDays());
}

async function countWeeks() {
  const mondays = [...new Set(state.days.map(Streams.weekOf))];
  let found = false;
  let empty = 0;
  for (const monday of mondays) {
    if ((await countWeek(monday)) > 0) {
      found = true;
      empty = 0;
    } else if (found || ++empty >= EMPTY_WEEKS_BEFORE_GIVING_UP) {
      break;
    }
  }
}

/** The week the stream switch and the line under the day are about. */
function currentWeek(days) {
  if (inVenues()) return state.week;
  return days.length ? Streams.weekOf(days[days.length - 1]) : null;
}

/** The stream switch, hidden while no week has venue papers, and the arXiv day's "+ N journal papers this week". */
function renderStreams(days) {
  const week = currentWeek(days);
  const count = (week && state.weeks.get(week)) || 0;
  $('streamSwitch').hidden = !state.weeks.size && !inVenues();
  document.querySelectorAll('#streamSwitch button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.stream === state.stream)));
  $('streamCount').textContent = count ? count.toLocaleString('en-GB') : '';
  const showNote = !inVenues() && days.length === 1 && count > 0;
  $('weekNote').hidden = !showNote;
  if (!showNote) return;
  const kinds = Streams.daysInWeek(week, state.days).flatMap(d => (state.venueNames.get(d) || []).map(name => (state.venues.get(name) || {}).kind));
  $('weekNote').innerHTML = `<a href="#stream=venues&amp;week=${week}" data-week="${week}">${esc(Streams.weekNote(count, kinds))}</a>`;
}

/** Switch stream (and, for the weekly one, week), keeping the topic. */
async function setStream(stream, week = null, { paper = null } = {}) {
  state.stream = stream;
  if (stream === Streams.VENUES) state.week = state.weeks.has(week) ? week : [...state.weeks.keys()][0] || null;
  state.selectedId = paper;
  await showSelection({ keepTopic: true });
}

// --- Events -------------------------------------------------------------------

function themeOption(theme, name, current) {
  const checked = theme.id === current ? ' checked' : '';
  return `<label class="theme-option"><input type="radio" name="${name}" value="${theme.id}"${checked}>
<span class="swatch" data-swatch="${theme.id}" aria-hidden="true"><i></i><i></i><i></i></span>
<span class="theme-text"><span class="theme-name">${esc(theme.name)}</span><span class="theme-note">${esc(theme.note)}</span></span></label>`;
}

function modeOption(mode, current) {
  const checked = mode.id === current ? ' checked' : '';
  return `<label><input type="radio" name="mode" value="${mode.id}"${checked}><span>${esc(mode.name)}</span></label>`;
}

/** The theme choices currently ticked in the dialog. */
function themeChoices(form) {
  return { mode: form.elements.mode.value, light: form.elements.lightTheme.value, dark: form.elements.darkTheme.value };
}

function openSettings() {
  const prefs = Theme.read(localStorage);
  $('modeOptions').innerHTML = Theme.MODES.map(mode => modeOption(mode, prefs.mode)).join('');
  $('lightOptions').innerHTML = Theme.LIGHT.map(theme => themeOption(theme, 'lightTheme', prefs.light)).join('');
  $('darkOptions').innerHTML = Theme.DARK.map(theme => themeOption(theme, 'darkTheme', prefs.dark)).join('');
  const openOn = primaryLink();
  document.querySelectorAll('input[name="openOn"]').forEach(input => {
    input.checked = input.value === openOn;
  });
  $('keywordsInput').value = state.keywords.join('\n');
  $('authorsInput').value = state.authors.join('\n');
  $('settings').showModal();
}

/** Save the dialog; the theme previews as soon as it is picked and reverts on Cancel. */
function closeSettings() {
  const form = $('settings').querySelector('form');
  if ($('settings').returnValue !== 'save') {
    Theme.show();
    return;
  }
  Theme.save(localStorage, themeChoices(form));
  Theme.show();
  writeList(OPEN_ON_KEY, form.elements.openOn.value || DATA_CONFIG.primaryLink);
  const lines = id => [...new Set($(id).value.split('\n').map(s => s.trim()).filter(Boolean))];
  writeList(KEYWORDS_KEY, lines('keywordsInput'));
  state.keywords = resolveKeywords(lines('keywordsInput'));
  state.authors = lines('authorsInput');
  state.topics = Render.topicsFor(state.keywords, window.INTEREST_PRESETS);
  writeList(AUTHORS_KEY, state.authors);
  describeAll();
  renderAll(streamDays());
}

function isTyping(target) {
  return target instanceof Element && Boolean(target.closest('input, textarea, select, dialog[open]'));
}

function bindEvents() {
  $('rangeToggle').addEventListener('change', () => {
    state.range = $('rangeToggle').checked;
    showSelection();
  });
  const step = which => {
    const next = steps()[which];
    if (!next) return;
    state[inVenues() ? 'week' : 'day'] = next;
    showSelection();
  };
  $('prevDay').addEventListener('click', () => step('older'));
  $('nextDay').addEventListener('click', () => step('newer'));
  $('streamSwitch').addEventListener('click', event => {
    const button = event.target.closest('button[data-stream]');
    if (button && button.dataset.stream !== state.stream) setStream(button.dataset.stream, currentWeek(selectedDays()));
  });
  $('weekNote').addEventListener('click', event => {
    const link = event.target.closest('a[data-week]');
    if (!link) return;
    event.preventDefault();
    setStream(Streams.VENUES, link.dataset.week);
  });
  $('search').addEventListener('input', event => {
    state.query = event.target.value;
    renderNav(streamDays());
    renderList();
  });
  $('topicList').addEventListener('click', event => {
    const button = event.target.closest('button[data-topic]');
    if (!button) return;
    state.topic = button.dataset.topic;
    renderNav(streamDays());
    renderList();
    writeHash();
  });
  $('refineList').addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.hasAttribute('data-code')) state.codeOnly = !state.codeOnly;
    else if (button.hasAttribute('data-free')) state.freeOnly = !state.freeOnly;
    else if (button.dataset.category) state.category = button.dataset.category;
    else return;
    renderNav(streamDays());
    renderList();
    writeHash();
  });
  [['typeList', 'type'], ['areaList', 'area'], ['sourceList', 'source']].forEach(([list, kind]) => {
    $(list).addEventListener('click', event => {
      const button = event.target.closest(`button[data-${kind}]`);
      if (!button) return;
      state[kind] = button.dataset[kind];
      if (kind !== 'source') state.source = 'all'; // the venue row now lists other venues
      renderNav(streamDays());
      renderList();
      writeHash();
    });
  });
  $('clearFilters').addEventListener('click', () => {
    state.category = 'all';
    state.codeOnly = false;
    setSourceChoices({ type: 'all', area: 'all', source: 'all', freeOnly: false });
    renderNav(streamDays());
    renderList();
    writeHash();
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
  $('settings').addEventListener('close', closeSettings);
  $('appearance').addEventListener('change', () => Theme.show(themeChoices($('settings').querySelector('form'))));
}

async function init() {
  loadPreferences();
  let listing;
  try {
    listing = await DataSource.listDays();
  } catch (error) {
    $('dayTitle').textContent = 'Papers unavailable';
    showLoadError(error, init);
    return;
  }
  const { categories } = listing;
  const days = Calendar.limitDays(listing.days, DATA_CONFIG.earliestDay);
  state.days = days;
  state.mainCategories = categories || DATA_CONFIG.mainCategories;
  state.venues = Sources.venueIndex(listing.venues);
  state.indexed = Boolean(listing.venueDays);
  if (state.indexed) state.venueDays = new Map(listing.venueDays);
  if (!days.length) {
    $('dayTitle').textContent = 'No papers yet';
    $('paperList').innerHTML = `<li class="empty">Nothing has been published to the data branch of ${esc(DATA_CONFIG.repoOwner)}/${esc(DATA_CONFIG.repoName)} yet, or it could not be reached. On a new fork, run the arXiv-daily-ai-enhanced workflow from the Actions tab; the first day appears a few minutes after it finishes.</li>`;
    return;
  }
  const json = JsonMode.params(window.location.search);
  if (json) {
    JsonMode.output(json, await DataSource.loadDay(days[0]));
    return;
  }
  state.day = days[0];
  state.from = days[Math.min(4, days.length - 1)];
  picker = CalendarPicker.create({ trigger: $('dateTrigger'), panel: $('datePicker'), label: $('dateTriggerText'), onPick: pickDays });
  readHash();
  const linkedPaper = state.selectedId;
  bindEvents();
  DataSource.loadStatus().then(status => {
    state.status = status;
    renderStatus(streamDays());
  });
  const params = new URLSearchParams(location.hash.slice(1));
  const keepTopic = Boolean(state.topic);
  const linkedWeek = params.get('stream') === Streams.VENUES && Streams.isDay(params.get('week'));
  if (params.get('stream') === Streams.VENUES && !linkedWeek) {
    await discoverWeeks();
    Object.assign(state, Streams.readStream(params, state.weeks));
    await showSelection({ keepTopic });
  } else {
    // Start loading the day or the linked week first, so counting weeks reuses the download.
    if (linkedWeek) Object.assign(state, { stream: Streams.VENUES, week: Streams.weekOf(params.get('week')) });
    const shown = showSelection({ keepTopic });
    discoverWeeks();
    await shown;
  }
  await openLinkedPaper(linkedPaper);
}

document.addEventListener('DOMContentLoaded', init);
