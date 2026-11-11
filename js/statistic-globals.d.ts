/**
 * Libraries statistic.html loads from CDNs (flatpickr, compromise, d3,
 * d3-cloud, Chart.js), for `tsc --checkJs` only. They are typed loosely on
 * purpose: the page is upstream's and not worth vendoring their types for.
 */
declare var flatpickr: any;
declare var nlp: any;
declare var d3: any;
declare var Chart: any;

/** statistic.js keeps the summary languages of each day here. */
interface Window {
  dateLanguageMap?: Map<string, string[]>;
}
