/**
 * The date picker's pure logic: month grids (Monday first), which days can
 * be picked in each mode (one day, several days, a week of the weekly
 * stream), keyboard movement, and wording. Days are ISO strings
 * ('2026-11-11'), months 'YYYY-MM'. The DOM side is js/calendar-picker.js.
 * Loaded as the global `Calendar`, and by node for tests.
 */
/**
 * What the picker draws: the mode, the days or weeks that can be picked, the
 * selection, and (set by the picker) the month on screen and a pending range.
 * @typedef {object} PickerView
 * @property {'day' | 'range' | 'week'} mode
 * @property {string} [month]                  'YYYY-MM' on screen
 * @property {Set<string>} available           days with data (day and range modes)
 * @property {string | null} [day]             day mode
 * @property {string | null} [start]           range mode
 * @property {string | null} [end]
 * @property {string | null} [pending]         a range's first click
 * @property {string | null} [preview]         the day under the pointer while a range is pending
 * @property {Map<string, number>} [weeks]     week mode: Monday -> venue papers
 * @property {string | null} [week]
 * @property {Set<string>} [months]            months with anything to pick
 * @property {DayBounds} [bounds]
 *
 * @typedef {{ min: string | null, max: string | null }} DayBounds
 *
 * @typedef {object} Cell
 * @property {string} day
 * @property {boolean} inMonth
 * @property {boolean} enabled
 * @property {boolean} selected
 * @property {boolean} inRange
 * @property {boolean} rangeStart
 * @property {boolean} rangeEnd
 * @property {number} weekCount
 */
(function (root, factory) {
  /**
   * A sibling script's global in the browser, or its module under node.
   * @param {string} name
   * @param {string} file
   * @returns {any}
   */
  const load = (name, file) => /** @type {any} */ (root)[name] || (typeof require === 'function' ? require(file) : null);
  const api = factory(load('Streams', './streams.js'));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Calendar = api;
  }
})(typeof self !== 'undefined' ? self : this, /** @param {typeof import('./streams.js')} Streams */ function (Streams) {
  const DAY_MS = 24 * 60 * 60 * 1000;
  const WEEKS_SHOWN = 6;

  /** @param {string} day */
  function toDate(day) {
    const [y, m, d] = day.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  }

  /** @param {Date} date */
  const toDay = date => date.toISOString().slice(0, 10);
  /**
   * @param {string} day
   * @param {Intl.DateTimeFormatOptions} options
   */
  const format = (day, options) => toDate(day).toLocaleDateString('en-GB', { ...options, timeZone: 'UTC' });

  /**
   * @param {string} day
   * @param {number} n
   */
  const addDays = (day, n) => toDay(new Date(toDate(day).getTime() + n * DAY_MS));
  /** @param {string} day */
  const monthOf = day => day.slice(0, 7);
  /** @param {string} month */
  const firstOf = month => `${month}-01`;

  /**
   * The same day n months later, or the month's last day when it is shorter.
   * @param {string} day
   * @param {number} n
   */
  function addMonths(day, n) {
    const [y, m, d] = day.split('-').map(Number);
    const lastDay = new Date(Date.UTC(y, m - 1 + n + 1, 0)).getUTCDate();
    return toDay(new Date(Date.UTC(y, m - 1 + n, Math.min(d, lastDay))));
  }

  /**
   * @param {string} month
   * @param {number} n
   */
  const stepMonth = (month, n) => monthOf(addMonths(firstOf(month), n));

  /** Six Monday-first weeks of seven days, starting with the week the month's first day is in. */
  /**
   * @param {string} month
   * @returns {string[][]}
   */
  function monthGrid(month) {
    const start = Streams.weekOf(firstOf(month));
    return Array.from({ length: WEEKS_SHOWN }, (_, w) => Array.from({ length: 7 }, (_, d) => addDays(start, w * 7 + d)));
  }

  /**
   * The days on or after `earliest`; null keeps them all.
   * @param {string[]} days
   * @param {string | null | undefined} earliest
   */
  function limitDays(days, earliest) {
    return earliest ? days.filter(d => d >= earliest) : days;
  }

  /**
   * Venue papers per day (a Map, or null) without the days before `earliest`.
   * @param {Map<string, number> | null | undefined} counts
   * @param {string | null | undefined} earliest
   * @returns {Map<string, number>}
   */
  function limitCounts(counts, earliest) {
    return new Map([...(counts || [])].filter(([day]) => !earliest || day >= earliest));
  }

  /** The asked day when the page offers it, else the latest day (days newest first); null for none. */
  /**
   * @param {unknown} asked
   * @param {string[]} days
   * @returns {string | null}
   */
  function chooseDay(asked, days) {
    return typeof asked === 'string' && days.includes(asked) ? asked : days[0] || null;
  }

  /** Whether the week of an asked day has any day the page offers. */
  /**
   * @param {unknown} asked
   * @param {string[]} days
   */
  function weekOnPage(asked, days) {
    return Streams.isDay(asked) && Streams.daysInWeek(Streams.weekOf(asked), days).length > 0;
  }

  /** Oldest and newest of the days, in any order; nulls for none. */
  /**
   * @param {string[]} days
   * @returns {DayBounds}
   */
  function bounds(days) {
    if (!days.length) return { min: null, max: null };
    const sorted = [...days].sort();
    return { min: sorted[0], max: sorted[sorted.length - 1] };
  }

  /** From the first Monday to the last Sunday of the weeks that have papers. */
  /**
   * @param {Map<string, number>} weeks
   * @returns {DayBounds}
   */
  function weekBounds(weeks) {
    const { min, max } = bounds([...weeks.keys()]);
    return { min, max: max && addDays(max, 6) };
  }

  /**
   * @param {string} day
   * @param {string} a
   * @param {string} b
   */
  const between = (day, a, b) => day >= a && day <= b;

  /** The range a range view shades: the chosen one, or the pending start to the day under the pointer. */
  /**
   * @param {PickerView} view
   * @returns {[string, string] | [null, null]}
   */
  function shadedRange(view) {
    if (view.pending) {
      const other = view.preview || view.pending;
      return other < view.pending ? [other, view.pending] : [view.pending, other];
    }
    return view.start && view.end ? [view.start, view.end] : [null, null];
  }

  /**
   * How one cell of the grid looks and behaves. `view`: { mode: 'day' |
   * 'range' | 'week', month, available: Set of days with data, day (day
   * mode), start, end, pending, preview (range mode), weeks: Map(Monday ->
   * venue papers), week (week mode) }.
   * @param {string} day
   * @param {PickerView} view
   * @returns {Cell}
   */
  function cellState(day, view) {
    const base = { day, inMonth: monthOf(day) === view.month, selected: false, inRange: false, rangeStart: false, rangeEnd: false, weekCount: 0 };
    if (view.mode === 'week') {
      const monday = Streams.weekOf(day);
      const weekCount = (view.weeks && view.weeks.get(monday)) || 0;
      return { ...base, enabled: weekCount > 0, selected: monday === view.week, weekCount };
    }
    const enabled = view.available.has(day);
    if (view.mode !== 'range') return { ...base, enabled, selected: day === view.day };
    const [from, to] = shadedRange(view);
    const rangeStart = Boolean(from) && day === from;
    const rangeEnd = Boolean(to) && day === to;
    const inRange = Boolean(from && to) && between(day, /** @type {string} */ (from), /** @type {string} */ (to));
    return { ...base, enabled, inRange, rangeStart, rangeEnd, selected: rangeStart || rangeEnd };
  }

  /** The months that have any of the days, as 'YYYY-MM'. */
  /** @param {string[]} days */
  function monthsWithDays(days) {
    return new Set(days.map(monthOf));
  }

  /** The months any day of a week with papers falls in. */
  /** @param {Map<string, number>} weeks */
  function monthsWithWeeks(weeks) {
    /** @type {Set<string>} */
    const months = new Set();
    [...weeks.keys()].forEach(monday => {
      months.add(monthOf(monday));
      months.add(monthOf(addDays(monday, 6)));
    });
    return months;
  }

  /** The year's twelve months for the month view, each enabled when `months` has it. */
  /**
   * @param {number | string} year
   * @param {Set<string>} months
   */
  function monthChoices(year, months) {
    return Array.from({ length: 12 }, (_, i) => {
      const month = `${year}-${String(i + 1).padStart(2, '0')}`;
      const first = firstOf(month);
      return { month, label: format(first, { month: 'short' }), name: monthTitle(month), enabled: months.has(month) };
    });
  }

  /** The first and last year that have a month with data. */
  /** @param {Iterable<string>} months */
  function yearSpan(months) {
    const years = [...months].map(m => Number(m.slice(0, 4)));
    return { first: Math.min(...years), last: Math.max(...years) };
  }

  /** A first pick leaves a pending start; a second ends the range, oldest day first. */
  /**
   * @param {string | null | undefined} pending
   * @param {string} day
   * @returns {{ pending: string | null, start: string | null, end: string | null }}
   */
  function rangePick(pending, day) {
    if (!pending) return { pending: day, start: null, end: null };
    const [start, end] = day < pending ? [day, pending] : [pending, day];
    return { pending: null, start, end };
  }

  /** @type {Partial<Record<string, (day: string, shift?: boolean) => string>>} */
  const MOVES = {
    ArrowLeft: day => addDays(day, -1),
    ArrowRight: day => addDays(day, 1),
    ArrowUp: day => addDays(day, -7),
    ArrowDown: day => addDays(day, 7),
    Home: day => Streams.weekOf(day),
    End: day => addDays(Streams.weekOf(day), 6),
    PageUp: (day, shift) => addMonths(day, shift ? -12 : -1),
    PageDown: (day, shift) => addMonths(day, shift ? 12 : 1),
  };

  /** Where a key moves the focused day, kept between the bounds; null for keys that do not move. */
  /**
   * @param {string} day
   * @param {string} key
   * @param {boolean} [shift]
   * @param {Partial<DayBounds>} [limits]
   * @returns {string | null}
   */
  function move(day, key, shift, { min, max } = {}) {
    const step = MOVES[key];
    if (!step) return null;
    const next = step(day, shift);
    if (min && next < min) return min;
    if (max && next > max) return max;
    return next;
  }

  /**
   * The day to focus in the shown month: the selection when it is there,
   * else the month's newest pickable day, else its first day.
   * @param {PickerView & { month: string }} view
   * @returns {string}
   */
  function focusDay(view) {
    const chosen = view.mode === 'week' ? view.week : view.mode === 'range' ? view.end : view.day;
    if (chosen && view.mode === 'week') {
      const inMonth = Streams.weekDays(chosen).find(d => monthOf(d) === view.month);
      if (inMonth) return inMonth;
    } else if (chosen && monthOf(chosen) === view.month) {
      return chosen;
    }
    const days = monthGrid(view.month).flat().filter(d => monthOf(d) === view.month);
    const pickable = days.filter(d => cellState(d, view).enabled);
    return pickable.length ? pickable[pickable.length - 1] : firstOf(view.month);
  }

  /** @param {string} month */
  function monthTitle(month) {
    return format(firstOf(month), { month: 'long', year: 'numeric' });
  }

  /** @param {string} day */
  function dayLabel(day) {
    return format(day, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).replace(',', '');
  }

  /** Monday to Sunday: { short: 'Mo', long: 'Monday' }. */
  function weekdayNames() {
    return Streams.weekDays('2026-11-09').map(d => {
      const long = format(d, { weekday: 'long' });
      return { short: long.slice(0, 2), long };
    });
  }

  /** The trigger button's text: "Wed 11 Nov 2026", "9–11 Nov 2026", or the week "9–15 Nov 2026". */
  /**
   * @param {PickerView} view
   * @returns {string}
   */
  function triggerText({ mode, day, start, end, week }) {
    if (mode === 'week') return week ? Streams.weekRange(week) : 'No week';
    if (mode === 'range' && start && end && start !== end) return Streams.dayRange(start, end);
    const one = mode === 'range' ? end : day;
    return one ? format(one, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).replace(',', '') : 'No day';
  }

  /**
   * The picker's view from the page's state: { venues (the weekly stream is
   * shown), days (with data, newest first), day, range, selected (the days
   * shown, oldest first), weeks, week }.
   * @param {{
   *   venues: boolean, days: string[], day: string | null, range: boolean, selected: string[],
   *   weeks: Map<string, number>, week: string | null,
   * }} state
   * @returns {PickerView}
   */
  function viewFor({ venues, days, day, range, selected, weeks, week }) {
    if (venues) return { mode: 'week', weeks, week, available: new Set(), months: monthsWithWeeks(weeks), bounds: weekBounds(weeks) };
    const common = { available: new Set(days), months: monthsWithDays(days), bounds: bounds(days) };
    if (!range) return { ...common, mode: 'day', day };
    return { ...common, mode: 'range', start: selected[0] || day, end: selected[selected.length - 1] || day };
  }

  /** The choices either side of `current` in a newest-first list; nulls at the ends or when it is missing. */
  /**
   * @param {string[]} list
   * @param {string | null | undefined} current
   * @returns {{ older: string | null, newer: string | null }}
   */
  function neighbours(list, current) {
    const i = current == null ? -1 : list.indexOf(current);
    if (i < 0) return { older: null, newer: null };
    return { older: list[i + 1] || null, newer: i > 0 ? list[i - 1] : null };
  }

  return {
    viewFor, neighbours,
    addDays, addMonths, monthOf, stepMonth, monthGrid, limitDays, limitCounts, chooseDay, weekOnPage, bounds, weekBounds, cellState,
    monthsWithDays, monthsWithWeeks, monthChoices, yearSpan, rangePick, move, focusDay,
    monthTitle, dayLabel, weekdayNames, triggerText,
  };
});
