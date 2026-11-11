/**
 * The page's two streams: arXiv papers by day, and journal and conference
 * papers by ISO week (Monday to Sunday, by the day file a paper is in).
 * Week arithmetic, which records a stream shows, the venue groups of the
 * weekly list, and the wording of the week. Loaded as the global `Streams`,
 * and by node for tests.
 */
(function (root, factory) {
  const load = (name, file) => root[name] || (typeof require === 'function' ? require(file) : null);
  const api = factory(load('PaperData', './paper-data.js'), load('Sources', './sources.js'));
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Streams = api;
  }
})(typeof self !== 'undefined' ? self : this, function (PaperData, Sources) {
  const ARXIV = 'arxiv';
  const VENUES = 'venues';
  const DAY_MS = 24 * 60 * 60 * 1000;
  const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

  function toDate(day) {
    const [y, m, d] = day.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  }

  const toDay = date => date.toISOString().slice(0, 10);

  function isDay(text) {
    return typeof text === 'string' && ISO_DAY.test(text) && toDay(toDate(text)) === text;
  }

  /** The Monday of the ISO week a day is in. */
  function weekOf(day) {
    const date = toDate(day);
    const sinceMonday = (date.getUTCDay() + 6) % 7;
    return toDay(new Date(date.getTime() - sinceMonday * DAY_MS));
  }

  /** The seven days of the week that starts on `monday`, Monday first. */
  function weekDays(monday) {
    const start = toDate(monday).getTime();
    return Array.from({ length: 7 }, (_, i) => toDay(new Date(start + i * DAY_MS)));
  }

  /** The days of `days` that fall in the week starting on `monday`, oldest first. */
  function daysInWeek(monday, days) {
    const week = new Set(weekDays(monday));
    return days.filter(d => week.has(d)).sort();
  }

  /**
   * Venue papers per week, from venue papers per day: a Map from Monday to
   * count, newest week first, holding only weeks that have any.
   */
  function venueWeeks(dayCounts) {
    const weeks = new Map();
    [...(dayCounts || new Map())].forEach(([day, count]) => {
      if (!count || !isDay(day)) return;
      const monday = weekOf(day);
      weeks.set(monday, (weeks.get(monday) || 0) + count);
    });
    return new Map([...weeks].sort((a, b) => (a[0] < b[0] ? 1 : -1)));
  }

  /** The records a stream shows: arXiv papers, or the journal and conference papers. */
  function streamRecords(records, stream) {
    return records.filter(r => (stream === VENUES ? !PaperData.isArxiv(r) : PaperData.isArxiv(r)));
  }

  /** Newest `published` first; papers without one last; ties keep the file order. */
  function byPublished(a, b) {
    const pa = a.record.published || '';
    const pb = b.record.published || '';
    if (pa !== pb) return pa < pb ? 1 : -1;
    return a.index - b.index;
  }

  /**
   * The weekly list's groups, one per venue: { key, label, kind, area,
   * entries }, venues with the most papers first (ties by name), papers in
   * each by publication date, newest first.
   */
  function venueGroups(entries, venues) {
    const groups = new Map();
    entries.forEach(entry => {
      const key = Sources.sourceKey(entry.record);
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          label: Sources.sourceLabel(entry.record),
          kind: Sources.sourceType(entry.record, venues),
          area: Sources.sourceArea(entry.record, venues),
          entries: [],
        });
      }
      groups.get(key).entries.push(entry);
    });
    return [...groups.values()]
      .map(group => ({ ...group, entries: [...group.entries].sort(byPublished) }))
      .sort((a, b) => b.entries.length - a.entries.length || a.label.localeCompare(b.label));
  }

  const format = (day, options) => toDate(day).toLocaleDateString('en-GB', { ...options, timeZone: 'UTC' });

  /** Two days, oldest first, as "9–11 Nov 2026", "28 Sept – 4 Oct 2026", "29 Dec 2025 – 4 Jan 2026". */
  function dayRange(first, last) {
    const [y1, m1] = first.split('-');
    const [y2, m2] = last.split('-');
    const end = format(last, { day: 'numeric', month: 'short', year: 'numeric' });
    if (y1 !== y2) return `${format(first, { day: 'numeric', month: 'short', year: 'numeric' })} – ${end}`;
    if (m1 !== m2) return `${format(first, { day: 'numeric', month: 'short' })} – ${end}`;
    return `${Number(first.slice(8))}–${end}`;
  }

  /** "9–15 Nov 2026", "28 Sept – 4 Oct 2026", "29 Dec 2025 – 4 Jan 2026". */
  function weekRange(monday) {
    return dayRange(monday, weekDays(monday)[6]);
  }

  /** "Week of 9 Nov 2026", for the week picker. */
  function weekLabel(monday) {
    return `Week of ${format(monday, { day: 'numeric', month: 'short', year: 'numeric' })}`;
  }

  const plural = (n, word) => `${n.toLocaleString('en-GB')} ${word}${n === 1 ? '' : 's'}`;

  /** "187 papers from 8 venues". */
  function weekSummary(total, venueCount) {
    return `${plural(total, 'paper')} from ${plural(venueCount, 'venue')}`;
  }

  /** "187 papers from 8 venues, 3 matching your interests." */
  function weekSentence(total, venueCount, matched, hasInterests) {
    const papers = weekSummary(total, venueCount);
    if (!hasInterests) return `${papers}.`;
    return `${papers}, ${matched === 0 ? 'none' : matched} matching your interests.`;
  }

  /** "journal", "conference" or "journal and conference", from the kinds of the week's papers. */
  function kindWord(kinds) {
    const set = new Set(kinds);
    if (set.has('conference') && !set.has('journal')) return 'conference';
    if (set.has('conference') && set.has('journal')) return 'journal and conference';
    return 'journal';
  }

  /** The arXiv stream's line under the day: "+ 187 journal papers this week"; '' for none. */
  function weekNote(count, kinds = []) {
    if (!count) return '';
    return `+ ${count.toLocaleString('en-GB')} ${kindWord(kinds)} paper${count === 1 ? '' : 's'} this week`;
  }

  /**
   * The stream and week the URL asks for, checked against the weeks that
   * have venue papers: an unknown or missing week becomes the newest one,
   * and the venue stream falls back to arXiv when no week has any.
   */
  function readStream(params, weeks) {
    const mondays = [...(weeks || new Map()).keys()];
    if (params.get('stream') !== VENUES || !mondays.length) return { stream: ARXIV, week: null };
    const asked = params.get('week');
    const week = isDay(asked) && mondays.includes(weekOf(asked)) ? weekOf(asked) : mondays[0];
    return { stream: VENUES, week };
  }

  return {
    ARXIV, VENUES, isDay, weekOf, weekDays, daysInWeek, venueWeeks, streamRecords, venueGroups,
    dayRange, weekRange, weekLabel, weekSummary, weekSentence, weekNote, readStream,
  };
});
