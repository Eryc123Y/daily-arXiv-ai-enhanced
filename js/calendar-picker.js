/**
 * The date picker: a popover month grid under the top bar's date button.
 * One day, several days (a first then a last click on the same grid), or a
 * week of the weekly stream; only days with data (weeks with venue papers)
 * can be picked. The month title opens a month view to jump far back.
 * Keyboard: arrows move by day and week, Home/End to the week's ends,
 * PageUp/PageDown by month (with Shift by year), Enter or Space picks, Esc
 * closes. The pure logic is js/calendar.js; this file only draws and listens.
 *
 *   const picker = CalendarPicker.create({ trigger, panel, label, onPick });
 *   picker.update(view);   // see Calendar.cellState, plus bounds and months
 *   onPick({ day } | { start, end } | { week })
 */
(function (root) {
  const C = root.Calendar;
  /** @param {unknown} text */
  const esc = text => String(text).replace(/[&<>"']/g, ch => `&#${ch.charCodeAt(0)};`);
  const supportsPopover = Object.prototype.hasOwnProperty.call(HTMLElement.prototype, 'popover');
  const supportsAnchoring = root.CSS && CSS.supports('position-area: block-end');
  /** @type {Record<CalendarView['mode'], string>} */
  const MODE_NAMES = { day: 'Choose a day', range: 'Choose several days', week: 'Choose a week' };
  /** @param {string} d */
  const STEP_ICON = d => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"></path></svg>`;
  const PREV = STEP_ICON('M15 18l-6-6 6-6');
  const NEXT = STEP_ICON('M9 18l6-6-6-6');

  /**
   * @param {Parameters<typeof CalendarPicker.create>[0]} options
   * @returns {CalendarPickerHandle}
   */
  function create({ trigger, panel, label, onPick }) {
    // The page calls update() before the button can open the picker, so the
    // drawing code always has a view and a month.
    /** @type {CalendarView} */
    let view = /** @type {any} */ (null);
    /** @type {string} */
    let shown = /** @type {any} */ (null); // the month on screen
    /** @type {string | null} */
    let focused = null; // the day holding the grid's tab stop
    /** @type {string | null} */
    let pending = null; // a range's first day, before the second click
    /** @type {string | null} */
    let preview = null; // the day under the pointer or focus while a range is pending
    let pane = 'days'; // or 'months'
    let year = 0; // the month view's year

    const isOpen = () => (supportsPopover ? panel.matches(':popover-open') : !panel.hidden);
    /** @returns {CalendarView & { month: string }} */
    const current = () => ({ ...view, month: shown, pending, preview });

    function open() {
      if (supportsPopover) panel.showPopover();
      else opened();
    }

    function close({ restoreFocus = true } = {}) {
      if (supportsPopover) panel.hidePopover();
      else closed();
      if (restoreFocus) trigger.focus();
    }

    // --- Drawing ---------------------------------------------------------------

    /**
     * @param {string} title
     * @param {string} stepLabel
     * @param {boolean} canBack
     * @param {boolean} canForward
     * @param {string} titleAttrs
     */
    function head(title, stepLabel, canBack, canForward, titleAttrs) {
      return `<div class="picker-head">
<button type="button" class="icon-button" data-step="-1" aria-label="Previous ${stepLabel}"${canBack ? '' : ' disabled'}>${PREV}</button>
<button type="button" class="picker-title" id="pickerTitle" ${titleAttrs}>${esc(title)}</button>
<button type="button" class="icon-button" data-step="1" aria-label="Next ${stepLabel}"${canForward ? '' : ' disabled'}>${NEXT}</button>
</div>`;
    }

    function hint() {
      if (view.mode !== 'range') return '';
      const text = pending ? `From ${C.dayLabel(pending)}: now pick the last day` : 'Pick the first day, then the last';
      return `<p class="picker-hint" aria-live="polite">${esc(text)}</p>`;
    }

    function daysPane() {
      const bounds = view.bounds || { min: null, max: null };
      const first = C.monthOf(bounds.min || shown);
      const last = C.monthOf(bounds.max || shown);
      const weekMode = view.mode === 'week';
      const titleAttrs = `aria-label="${esc(C.monthTitle(shown))}, choose another month" aria-expanded="false"`;
      const heads = C.weekdayNames().map(d => `<th scope="col" abbr="${d.long}">${d.short}</th>`).join('');
      const countHead = weekMode ? '<th scope="col" class="week-count"><span class="visually-hidden">Papers</span></th>' : '';
      const rows = C.monthGrid(shown).map(week => {
        const cells = week.map(day => `<td role="gridcell" data-day="${day}" tabindex="-1">${Number(day.slice(8))}</td>`).join('');
        const count = weekMode ? '<td role="gridcell" class="week-count" aria-hidden="true"></td>' : '';
        return `<tr data-week="${week[0]}">${cells}${count}</tr>`;
      });
      return `${head(C.monthTitle(shown), 'month', shown > first, shown < last, titleAttrs)}${hint()}
<table class="picker-grid${weekMode ? ' is-weeks' : ''}" role="grid" aria-labelledby="pickerTitle">
<thead><tr>${heads}${countHead}</tr></thead><tbody>${rows.join('')}</tbody></table>`;
    }

    function monthsPane() {
      const monthsWithData = view.months || new Set();
      const span = C.yearSpan(monthsWithData);
      const titleAttrs = `aria-label="${year}, back to the days" aria-expanded="true"`;
      const months = C.monthChoices(year, monthsWithData).map(m => {
        const current = m.month === shown ? ' aria-current="true"' : '';
        return `<button type="button" data-month="${m.month}" aria-label="${esc(m.name)}"${current}${m.enabled ? '' : ' disabled'}>${esc(m.label)}</button>`;
      });
      return `${head(String(year), 'year', year > span.first, year < span.last, titleAttrs)}<div class="picker-months">${months.join('')}</div>`;
    }

    function render() {
      panel.setAttribute('aria-label', MODE_NAMES[view.mode]);
      panel.innerHTML = pane === 'months' ? monthsPane() : daysPane();
      if (pane === 'days') paint();
    }

    /** Selection, range shading, the disabled days and the tab stop, on the drawn grid. */
    function paint() {
      const v = current();
      /** @type {NodeListOf<HTMLTableCellElement>} */ (panel.querySelectorAll('td[data-day]')).forEach(cell => {
        const s = C.cellState(cell.dataset.day || '', v);
        cell.classList.toggle('is-outside', !s.inMonth);
        cell.classList.toggle('is-in-range', s.inRange);
        cell.classList.toggle('is-range-start', s.rangeStart);
        cell.classList.toggle('is-range-end', s.rangeEnd);
        cell.setAttribute('aria-selected', String(s.selected));
        cell.setAttribute('aria-disabled', String(!s.enabled));
        cell.tabIndex = s.day === focused ? 0 : -1;
        const papers = v.mode === 'week' && s.enabled ? `, week with ${s.weekCount.toLocaleString('en-GB')} journal and conference papers` : '';
        cell.setAttribute('aria-label', `${C.dayLabel(s.day)}${papers}${s.enabled ? '' : ', no papers'}`);
      });
      /** @type {NodeListOf<HTMLTableRowElement>} */ (panel.querySelectorAll('tr[data-week]')).forEach(row => {
        const s = C.cellState(row.dataset.week || '', v);
        row.classList.toggle('is-week-selected', v.mode === 'week' && s.selected);
        row.classList.toggle('is-week-enabled', v.mode === 'week' && s.enabled);
        const count = row.querySelector('.week-count');
        if (count) count.textContent = s.weekCount ? s.weekCount.toLocaleString('en-GB') : '';
      });
    }

    /**
     * @param {string | null} day
     * @returns {HTMLTableCellElement | null}
     */
    const cellFor = day => panel.querySelector(`td[data-day="${day}"]`);

    function focusCell() {
      const cell = cellFor(focused);
      if (cell) cell.focus();
    }

    /**
     * Show the month a day is in (redrawing when it changes) and give that day the tab stop.
     * @param {string} day
     */
    function moveTo(day) {
      focused = day;
      if (pending) preview = day;
      if (C.monthOf(day) !== shown) {
        shown = C.monthOf(day);
        render();
      } else {
        paint();
      }
      focusCell();
    }

    /** @param {string} month */
    function showMonth(month) {
      shown = month;
      pane = 'days';
      focused = C.focusDay(current());
      render();
    }

    // --- Picking ----------------------------------------------------------------

    /** @param {string} day */
    function pick(day) {
      if (!C.cellState(day, current()).enabled) return;
      if (view.mode === 'week') return finish({ week: root.Streams.weekOf(day) });
      if (view.mode === 'day') return finish({ day });
      const result = C.rangePick(pending, day);
      if (!result.pending) return finish({ start: /** @type {string} */ (result.start), end: /** @type {string} */ (result.end) });
      pending = result.pending;
      preview = day;
      render();
      focusCell();
    }

    /** @param {CalendarPick} choice */
    function finish(choice) {
      close();
      onPick(choice);
    }

    // --- Opening and closing -----------------------------------------------------------

    /** Without CSS anchor positioning, place the open panel under the button, inside the window. */
    function place() {
      if (supportsAnchoring) return;
      const rect = trigger.getBoundingClientRect();
      const width = panel.offsetWidth;
      const left = Math.max(8, Math.min(rect.left, root.innerWidth - width - 8));
      Object.assign(panel.style, { position: 'fixed', inset: 'auto', margin: '0', top: `${rect.bottom + 6}px`, left: `${left}px` });
    }

    function opened() {
      const chosen = view.mode === 'week' ? view.week : view.mode === 'range' ? view.end : view.day;
      pending = null;
      preview = null;
      pane = 'days';
      if (!supportsPopover) {
        panel.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
      }
      showMonth(C.monthOf(chosen || (view.bounds && view.bounds.max) || ''));
      place();
      focusCell();
    }

    function closed() {
      if (!supportsPopover) {
        panel.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
      }
      pending = null;
      preview = null;
    }

    // --- Events -------------------------------------------------------------------

    /** @param {MouseEvent} event */
    function onClick(event) {
      const clicked = /** @type {Element} */ (event.target);
      const step = /** @type {HTMLButtonElement | null} */ (clicked.closest('button[data-step]'));
      const month = /** @type {HTMLButtonElement | null} */ (clicked.closest('button[data-month]'));
      const cell = /** @type {HTMLTableCellElement | null} */ (clicked.closest('td[data-day]'));
      if (step && pane === 'months') {
        year += Number(step.dataset.step);
        render();
        /** @type {HTMLButtonElement} */ (panel.querySelector(`button[data-step="${step.dataset.step}"]`)).focus();
      } else if (step) {
        showMonth(C.stepMonth(shown, Number(step.dataset.step)));
        const again = /** @type {HTMLButtonElement} */ (panel.querySelector(`button[data-step="${step.dataset.step}"]`));
        /** @type {HTMLElement} */ (again.disabled ? cellFor(focused) : again).focus();
      } else if (month) {
        showMonth(/** @type {string} */ (month.dataset.month));
        focusCell();
      } else if (clicked.closest('#pickerTitle')) {
        pane = pane === 'days' ? 'months' : 'days';
        year = Number(shown.slice(0, 4));
        render();
        /** @type {HTMLElement | null} */
        const target = pane === 'months' ? panel.querySelector('button[data-month][aria-current]') || panel.querySelector('#pickerTitle') : cellFor(focused);
        if (target) target.focus();
      } else if (cell) {
        focused = /** @type {string} */ (cell.dataset.day);
        pick(focused);
      } else if (view.mode === 'week' && clicked.closest('tr[data-week] .week-count')) {
        pick(/** @type {string} */ (/** @type {HTMLTableRowElement} */ (clicked.closest('tr[data-week]')).dataset.week));
      }
    }

    /** @param {KeyboardEvent} event */
    function onKeydown(event) {
      const pressed = /** @type {Element} */ (event.target);
      const cell = /** @type {HTMLTableCellElement | null} */ (pressed.closest && pressed.closest('td[data-day]'));
      if (!supportsPopover && event.key === 'Escape') {
        close();
        return;
      }
      if (!cell || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        pick(/** @type {string} */ (cell.dataset.day));
        return;
      }
      const next = C.move(/** @type {string} */ (cell.dataset.day), event.key, event.shiftKey, view.bounds);
      if (!next || next === cell.dataset.day) return;
      event.preventDefault();
      moveTo(next);
    }

    /** @param {PointerEvent} event */
    function onPointerOver(event) {
      const cell = pending && /** @type {HTMLTableCellElement | null} */ (/** @type {Element} */ (event.target).closest('td[data-day]'));
      if (!cell || cell.dataset.day === preview) return;
      preview = cell.dataset.day || null;
      paint();
    }

    panel.addEventListener('click', onClick);
    panel.addEventListener('keydown', onKeydown);
    panel.addEventListener('pointerover', onPointerOver);
    if (supportsPopover) {
      panel.addEventListener('toggle', event => (/** @type {ToggleEvent} */ (event).newState === 'open' ? opened() : closed()));
    } else {
      // Browsers without the Popover API: open from the button, close on Esc or a click elsewhere.
      trigger.removeAttribute('popovertarget');
      panel.hidden = true;
      trigger.addEventListener('click', () => (isOpen() ? close() : opened()));
      root.document.addEventListener('click', event => {
        const target = /** @type {Node} */ (event.target);
        if (isOpen() && !panel.contains(target) && !trigger.contains(target)) close({ restoreFocus: false });
      });
    }

    return {
      /** New data or a new choice: redraw the button, and the grid if it is open. */
      /** @param {CalendarView} next */
      update(next) {
        view = next;
        label.textContent = C.triggerText(view);
        trigger.setAttribute('aria-label', `${MODE_NAMES[view.mode]}, ${label.textContent}`);
        trigger.disabled = !(view.bounds && view.bounds.max);
        if (isOpen() && pane === 'days') {
          render();
          focusCell();
        }
      },
      open,
      close,
    };
  }

  root.CalendarPicker = { create };
})(typeof self !== 'undefined' ? self : this);
