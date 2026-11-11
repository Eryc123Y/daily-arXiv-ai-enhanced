// The date picker's pure logic: month grids, which days can be picked,
// ranges, weeks, keyboard movement and the wording of the trigger.
const test = require('node:test');
const assert = require('node:assert/strict');

const Calendar = require('../../js/calendar.js');
const Streams = require('../../js/streams.js');

// Days with data, newest first, as listDays() returns them: a gap on 7-8 Nov (a weekend).
const DAYS = ['2026-11-11', '2026-11-10', '2026-11-09', '2026-11-06', '2026-11-05', '2026-10-30', '2025-03-18'];
const AVAILABLE = new Set(DAYS);

// --- Day arithmetic -----------------------------------------------------------------

test('days and months add across month and year ends', () => {
  assert.equal(Calendar.addDays('2026-11-30', 1), '2026-12-01');
  assert.equal(Calendar.addDays('2027-01-01', -1), '2026-12-31');
  assert.equal(Calendar.addMonths('2026-11-11', 1), '2026-12-11');
  assert.equal(Calendar.addMonths('2026-01-31', 1), '2026-02-28'); // clamps to the month's last day
  assert.equal(Calendar.addMonths('2026-11-11', -12), '2025-11-11');
  assert.equal(Calendar.monthOf('2026-11-11'), '2026-11');
  assert.equal(Calendar.stepMonth('2026-12', 1), '2027-01');
  assert.equal(Calendar.stepMonth('2025-01', -1), '2024-12');
});

// --- Month grid --------------------------------------------------------------------

test('a month grid has six Monday-first weeks covering the whole month', () => {
  const grid = Calendar.monthGrid('2026-11'); // 1 Nov 2026 is a Sunday
  assert.equal(grid.length, 6);
  grid.forEach(week => assert.equal(week.length, 7));
  assert.deepEqual(grid[0], ['2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-10-31', '2026-11-01']);
  assert.equal(grid[5][6], '2026-12-06');
  grid.forEach(week => assert.equal(Streams.weekOf(week[0]), week[0]));
});

test('a month that starts on Monday starts the grid on its first day', () => {
  const grid = Calendar.monthGrid('2026-06'); // 1 Jun 2026 is a Monday
  assert.equal(grid[0][0], '2026-06-01');
  assert.equal(grid[4][2], '2026-07-01');
});

// --- Which days can be picked ---------------------------------------------------------

test('the earliest selectable day is set in one place, and null keeps every day', () => {
  assert.deepEqual(Calendar.limitDays(DAYS, null), DAYS);
  assert.deepEqual(Calendar.limitDays(DAYS, '2025-12-29'), DAYS.slice(0, 6));
});

test('in day and range mode, only days with data can be picked', () => {
  const view = { mode: 'day', month: '2026-11', available: AVAILABLE, day: '2026-11-11' };
  assert.equal(Calendar.cellState('2026-11-11', view).enabled, true);
  assert.equal(Calendar.cellState('2026-11-07', view).enabled, false); // Saturday, no file
  assert.equal(Calendar.cellState('2026-10-30', view).enabled, true);
  assert.equal(Calendar.cellState('2026-10-30', view).inMonth, false);
  assert.equal(Calendar.cellState('2026-11-11', view).selected, true);
  assert.equal(Calendar.cellState('2026-11-10', view).selected, false);
});

test('in week mode, every day of a week with venue papers can be picked', () => {
  const weeks = new Map([['2026-11-09', 187], ['2026-11-02', 40]]);
  const view = { mode: 'week', month: '2026-11', available: AVAILABLE, weeks, week: '2026-11-09' };
  const sunday = Calendar.cellState('2026-11-15', view);
  assert.equal(sunday.enabled, true);
  assert.equal(sunday.selected, true);
  assert.equal(sunday.weekCount, 187);
  assert.equal(Calendar.cellState('2026-11-07', view).enabled, true);
  assert.equal(Calendar.cellState('2026-11-07', view).selected, false);
  assert.equal(Calendar.cellState('2026-11-17', view).enabled, false);
  assert.equal(Calendar.cellState('2026-11-17', view).weekCount, 0);
});

test('months with data, for the month and year view', () => {
  const months = Calendar.monthsWithDays(DAYS);
  assert.deepEqual([...months].sort(), ['2025-03', '2026-10', '2026-11']);
  // A week with papers that starts in one month makes both months worth opening.
  const fromWeeks = Calendar.monthsWithWeeks(new Map([['2026-09-28', 3]]));
  assert.deepEqual([...fromWeeks].sort(), ['2026-09', '2026-10']);
  const choices = Calendar.monthChoices(2025, months);
  assert.equal(choices.length, 12);
  assert.deepEqual(choices[2], { month: '2025-03', label: 'Mar', name: 'March 2025', enabled: true });
  assert.equal(choices[3].enabled, false);
});

test('the years the month view can step through', () => {
  assert.deepEqual(Calendar.yearSpan(Calendar.monthsWithDays(DAYS)), { first: 2025, last: 2026 });
});

// --- Ranges ------------------------------------------------------------------------

test('a range is picked as a first click then a second, in either order', () => {
  const first = Calendar.rangePick(null, '2026-11-10');
  assert.deepEqual(first, { pending: '2026-11-10', start: null, end: null });
  assert.deepEqual(Calendar.rangePick(first.pending, '2026-11-05'), { pending: null, start: '2026-11-05', end: '2026-11-10' });
  assert.deepEqual(Calendar.rangePick(first.pending, '2026-11-11'), { pending: null, start: '2026-11-10', end: '2026-11-11' });
  assert.deepEqual(Calendar.rangePick(first.pending, '2026-11-10'), { pending: null, start: '2026-11-10', end: '2026-11-10' });
});

test('a range is shaded between its ends, and a pending start previews up to the hovered day', () => {
  const view = { mode: 'range', month: '2026-11', available: AVAILABLE, start: '2026-11-05', end: '2026-11-10' };
  assert.equal(Calendar.cellState('2026-11-05', view).rangeStart, true);
  assert.equal(Calendar.cellState('2026-11-10', view).rangeEnd, true);
  assert.equal(Calendar.cellState('2026-11-07', view).inRange, true);
  assert.equal(Calendar.cellState('2026-11-11', view).inRange, false);
  assert.equal(Calendar.cellState('2026-11-05', view).selected, true);
  const pending = { ...view, pending: '2026-11-10', preview: '2026-11-06' };
  assert.equal(Calendar.cellState('2026-11-08', pending).inRange, true);
  assert.equal(Calendar.cellState('2026-11-06', pending).rangeStart, true);
  assert.equal(Calendar.cellState('2026-11-10', pending).rangeEnd, true);
  assert.equal(Calendar.cellState('2026-11-05', pending).inRange, false);
});

// --- Keyboard --------------------------------------------------------------------------

test('arrow keys move by day and week, Home and End to the week ends', () => {
  const bounds = { min: '2025-03-18', max: '2026-11-11' };
  assert.equal(Calendar.move('2026-11-10', 'ArrowLeft', false, bounds), '2026-11-09');
  assert.equal(Calendar.move('2026-11-10', 'ArrowRight', false, bounds), '2026-11-11');
  assert.equal(Calendar.move('2026-11-10', 'ArrowUp', false, bounds), '2026-11-03');
  assert.equal(Calendar.move('2026-11-03', 'ArrowDown', false, bounds), '2026-11-10');
  assert.equal(Calendar.move('2026-11-04', 'Home', false, bounds), '2026-11-02');
  assert.equal(Calendar.move('2026-11-04', 'End', false, bounds), '2026-11-08');
});

test('PageUp and PageDown change month, with Shift a year, and movement stays inside the data', () => {
  const bounds = { min: '2025-03-18', max: '2026-11-11' };
  assert.equal(Calendar.move('2026-10-31', 'PageUp', false, bounds), '2026-09-30');
  assert.equal(Calendar.move('2026-09-30', 'PageDown', false, bounds), '2026-10-30');
  assert.equal(Calendar.move('2026-05-12', 'PageUp', true, bounds), '2025-05-12');
  assert.equal(Calendar.move('2026-11-10', 'PageDown', false, bounds), '2026-11-11'); // clamped to the newest day
  assert.equal(Calendar.move('2026-11-11', 'ArrowDown', false, bounds), '2026-11-11');
  assert.equal(Calendar.move('2025-03-20', 'ArrowUp', false, bounds), '2025-03-18');
  assert.equal(Calendar.move('2026-11-10', 'Enter', false, bounds), null); // not a movement key
});

test('bounds cover the days with data, or whole weeks in week mode', () => {
  assert.deepEqual(Calendar.bounds(DAYS), { min: '2025-03-18', max: '2026-11-11' });
  assert.deepEqual(Calendar.weekBounds(new Map([['2026-11-09', 1], ['2026-10-26', 2]])), { min: '2026-10-26', max: '2026-11-15' });
  assert.deepEqual(Calendar.bounds([]), { min: null, max: null });
});

test('the day to focus when the grid opens or changes month', () => {
  const view = { mode: 'day', month: '2026-11', available: AVAILABLE, day: '2026-11-10' };
  assert.equal(Calendar.focusDay(view), '2026-11-10');
  // The selection is in another month: the newest pickable day of the shown month.
  assert.equal(Calendar.focusDay({ ...view, month: '2026-10' }), '2026-10-30');
  // Nothing pickable in the month: its first day.
  assert.equal(Calendar.focusDay({ ...view, month: '2026-08' }), '2026-08-01');
  const weekView = { mode: 'week', month: '2026-11', available: AVAILABLE, weeks: new Map([['2026-11-02', 3]]), week: '2026-11-02' };
  assert.equal(Calendar.focusDay(weekView), '2026-11-02');
});

// --- Wording -------------------------------------------------------------------------

test('the trigger reads as the current choice', () => {
  assert.equal(Calendar.triggerText({ mode: 'day', day: '2026-11-11' }), 'Wed 11 Nov 2026');
  assert.equal(Calendar.triggerText({ mode: 'range', start: '2026-11-09', end: '2026-11-11' }), '9–11 Nov 2026');
  assert.equal(Calendar.triggerText({ mode: 'range', start: '2026-10-30', end: '2026-11-11' }), '30 Oct – 11 Nov 2026');
  assert.equal(Calendar.triggerText({ mode: 'range', start: '2026-11-11', end: '2026-11-11' }), 'Wed 11 Nov 2026');
  assert.equal(Calendar.triggerText({ mode: 'week', week: '2026-11-09' }), '9–15 Nov 2026');
  assert.equal(Calendar.triggerText({ mode: 'week', week: null }), 'No week');
});

test('month titles and day labels for screen readers', () => {
  assert.equal(Calendar.monthTitle('2025-03'), 'March 2025');
  assert.equal(Calendar.dayLabel('2026-11-11'), 'Wednesday 11 November 2026');
  assert.deepEqual(Calendar.weekdayNames().map(d => d.short), ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']);
  assert.equal(Calendar.weekdayNames()[6].long, 'Sunday');
});

test('Streams.dayRange words any two days the way weekRange words a week', () => {
  assert.equal(Streams.dayRange('2026-11-09', '2026-11-11'), '9–11 Nov 2026');
  assert.equal(Streams.dayRange('2025-12-29', '2026-01-02'), '29 Dec 2025 – 2 Jan 2026');
  assert.equal(Streams.weekRange('2026-11-30'), '30 Nov – 6 Dec 2026');
});

// --- From the page's state -----------------------------------------------------------

test('the picker view for one day, several days and a week', () => {
  const base = { days: DAYS, day: '2026-11-10', from: '2026-11-05', range: false, weeks: new Map([['2026-11-09', 187]]), week: '2026-11-09', selected: ['2026-11-10'] };
  const day = Calendar.viewFor({ ...base, venues: false });
  assert.equal(day.mode, 'day');
  assert.equal(day.day, '2026-11-10');
  assert.equal(day.available.has('2025-03-18'), true);
  assert.deepEqual(day.bounds, { min: '2025-03-18', max: '2026-11-11' });
  assert.equal(day.months.has('2025-03'), true);
  const range = Calendar.viewFor({ ...base, venues: false, range: true, selected: ['2026-11-05', '2026-11-06', '2026-11-09', '2026-11-10'] });
  assert.equal(range.mode, 'range');
  assert.equal(range.start, '2026-11-05');
  assert.equal(range.end, '2026-11-10');
  const week = Calendar.viewFor({ ...base, venues: true });
  assert.equal(week.mode, 'week');
  assert.equal(week.week, '2026-11-09');
  assert.deepEqual(week.bounds, { min: '2026-11-09', max: '2026-11-15' });
  assert.deepEqual([...week.months], ['2026-11']);
});

test('the ‹ › buttons step to the next older or newer choice', () => {
  assert.deepEqual(Calendar.neighbours(DAYS, '2026-11-10'), { older: '2026-11-09', newer: '2026-11-11' });
  assert.deepEqual(Calendar.neighbours(DAYS, '2026-11-11'), { older: '2026-11-10', newer: null });
  assert.deepEqual(Calendar.neighbours(DAYS, '2025-03-18'), { older: null, newer: '2026-10-30' });
  assert.deepEqual(Calendar.neighbours(DAYS, '2024-01-01'), { older: null, newer: null });
});
