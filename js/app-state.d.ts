/**
 * Types for js/app.js, the page script, for `tsc --checkJs` only (the page
 * does not load this file). Kept here so app.js stays readable and under its
 * size limit.
 */

type FilterState = import('./filters.js').FilterState;
type FilterOption = import('./filters.js').FilterOption;
type FilterCounts = ReturnType<typeof Filters.counts>;
type RunLogEntry = import('./status.js').RunLogEntry;

/** Everything the page knows; app.js keeps one of these as `state`. */
interface AppState extends FilterState {
  /** Days with data, newest first. */
  days: string[];
  day: string | null;
  /** The other end of a range of days. */
  from: string | null;
  range: boolean;
  /** Streams.ARXIV or Streams.VENUES. */
  stream: string;
  /** The weekly stream's Monday. */
  week: string | null;
  /** Every paper of the days shown, both streams. */
  dayRecords: PageRecord[];
  /** The papers of the stream shown. */
  records: PageRecord[];
  /** Venue papers per day. */
  venueDays: Map<string, number>;
  /** The venue of each venue paper, per day. */
  venueNames: Map<string, string[]>;
  /** Whether venueDays came from assets/venue-days.json. */
  indexed: boolean;
  /** Venue papers per week (Monday), newest first. */
  weeks: Map<string, number>;
  groups: VenueGroup[];
  info: Map<string, PaperInfo>;
  topics: Topic[];
  keywords: string[];
  authors: string[];
  venues: VenueIndex;
  query: string;
  selectedId: string | null;
  mainCategories: string[];
  visible: ListEntry[];
  status: { log: RunLogEntry[] } | null;
}

/** The Settings dialog's form, with its named fields. */
type SettingsForm = HTMLFormElement & {
  elements: HTMLFormControlsCollection & {
    mode: RadioNodeList;
    lightTheme: RadioNodeList;
    darkTheme: RadioNodeList;
    openOn: RadioNodeList;
  };
};

/** The elements app.js finds by id in index.html, so `$('id')` is typed and a wrong id is an error. */
interface PageElements {
  appearance: HTMLFieldSetElement;
  areaList: HTMLUListElement;
  areaRow: HTMLDivElement;
  authorsInput: HTMLTextAreaElement;
  clearFilters: HTMLButtonElement;
  closeReader: HTMLButtonElement;
  darkOptions: HTMLDivElement;
  datePicker: HTMLDivElement;
  dateTrigger: HTMLButtonElement;
  dateTriggerText: HTMLSpanElement;
  dayForm: HTMLFormElement;
  daySentence: HTMLParagraphElement;
  dayTitle: HTMLHeadingElement;
  keywordsInput: HTMLTextAreaElement;
  lightOptions: HTMLDivElement;
  listHeading: HTMLHeadingElement;
  listNote: HTMLSpanElement;
  /** Drawn by showLoadError. */
  loadRetry: HTMLButtonElement;
  modeOptions: HTMLDivElement;
  nextDay: HTMLButtonElement;
  nextPaper: HTMLButtonElement;
  openSettings: HTMLButtonElement;
  paperList: HTMLUListElement;
  pipelineStatus: HTMLParagraphElement;
  prevDay: HTMLButtonElement;
  prevPaper: HTMLButtonElement;
  progress: HTMLDivElement;
  progressFill: HTMLDivElement;
  progressText: HTMLParagraphElement;
  rangeToggle: HTMLInputElement;
  reader: HTMLElement;
  readerContent: HTMLDivElement;
  refineList: HTMLUListElement;
  resetSettings: HTMLButtonElement;
  search: HTMLInputElement;
  settings: HTMLDialogElement;
  sourceFilter: HTMLElement;
  sourceList: HTMLUListElement;
  streamCount: HTMLSpanElement;
  streamSwitch: HTMLDivElement;
  topicList: HTMLUListElement;
  typeList: HTMLUListElement;
  venueRow: HTMLDivElement;
  weekNote: HTMLParagraphElement;
}
