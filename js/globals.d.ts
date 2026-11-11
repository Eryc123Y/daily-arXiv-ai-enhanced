/**
 * The globals the page's scripts share, for `tsc --checkJs` only (the page
 * does not load this file). Each script sets its global with `root.X = api`;
 * the files that also export to node are CommonJS modules to TypeScript, so
 * their globals take the exported type. See tsconfig.json.
 */

/** Node's CommonJS hooks, used only by the files that tests `require`. */
declare var module: { exports: unknown };
declare function require(path: string): any;

/** js/data-config.js, browser half. */
interface DataConfig {
  repoOwner: string;
  repoName: string;
  dataBranch: string;
  mainCategories: string[];
  earliestDay: string | null;
  primaryLink: 'alphaxiv' | 'arxiv';
  getDataBaseUrl(): string;
  getDataUrl(filePath: string): string;
  repoUrl(): string;
}

/** js/json-mode.js */
interface JsonRequest {
  category: string;
  keywords: string[] | null;
  authors: string[] | null;
}

/** js/calendar-picker.js: what onPick receives. */
type CalendarPick = { day: string } | { start: string; end: string } | { week: string };

/** js/calendar-picker.js */
interface CalendarPickerHandle {
  update(view: CalendarView): void;
  open(): void;
  close(): void;
}

/** The view CalendarPicker draws: see Calendar.cellState, plus bounds and months. */
type CalendarView = import('./calendar.js').PickerView;

declare var DATA_CONFIG: DataConfig;
declare var PaperData: typeof import('./paper-data.js');
declare var Sources: typeof import('./sources.js');
declare var Streams: typeof import('./streams.js');
declare var Calendar: typeof import('./calendar.js');
declare var Render: typeof import('./render.js');
declare var Filters: typeof import('./filters.js');
declare var Status: typeof import('./status.js');
declare var Theme: typeof import('./theme.js') & { show(prefs?: import('./theme.js').ThemePrefs): void };
declare var INTEREST_PRESETS: typeof import('./interest-presets.js').INTEREST_PRESETS;
declare var keywordsFor: typeof import('./interest-presets.js').keywordsFor;
declare var LoadError: typeof import('./data-source.js').LoadError;
declare var DataSource: ReturnType<typeof import('./data-source.js').createStaticSource>;
declare var JsonMode: {
  params(search: string): JsonRequest | null;
  output(request: JsonRequest, records: PageRecord[]): void;
};
declare var CalendarPicker: {
  create(options: {
    trigger: HTMLButtonElement;
    panel: HTMLElement;
    label: HTMLElement;
    onPick(pick: CalendarPick): void;
  }): CalendarPickerHandle;
};
