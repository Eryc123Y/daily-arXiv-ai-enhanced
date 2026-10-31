const test = require('node:test');
const assert = require('node:assert/strict');

const Render = require('../../js/render.js');

const AI = { tldr: 'Converts mono video to stereo.', motivation: 'm', method: 'x', result: 'r', conclusion: 'c' };
const TOPICS = [
  { name: 'Stereo', keywords: ['stereo', 'disparity'] },
  { name: 'RL', keywords: ['RLVR'] },
];
const paper = extra => ({
  id: '2610.00001',
  title: 'Stereo video from a single camera',
  authors: ['Ada Lovelace', 'Alan Turing'],
  categories: ['cs.CV', 'cs.GR'],
  summary: 'We estimate disparity <with> care.',
  abs: 'https://arxiv.org/abs/2610.00001',
  ...extra,
});

test('dates read as full English dates and ranges', () => {
  assert.equal(Render.formatDay('2026-10-30'), 'Friday, 30 October 2026');
  assert.equal(Render.formatRange('2026-10-28', '2026-10-30'), '28 October to 30 October 2026');
});

test('long author lists are shortened', () => {
  const names = Array.from({ length: 9 }, (_, i) => `A${i}`);
  assert.equal(Render.authorLine(names), 'A0, A1, A2, A3, A4, A5 and 3 others');
  assert.equal(Render.authorLine(names, 2), 'A0, A1 and 7 others');
  assert.equal(Render.authorLine(['Solo']), 'Solo');
});

test('matches come from title, abstract and TL;DR, and from authors', () => {
  const match = Render.matchesFor(paper({ AI, pending: false }), ['stereo', 'disparity', 'RLVR'], ['turing']);
  assert.deepEqual(match, { keywords: ['stereo', 'disparity'], authors: ['turing'] });
});

test('describe gives the matched topics with their colour slot', () => {
  const info = Render.describe(paper({ AI, pending: false }), ['stereo', 'RLVR'], [], TOPICS);
  assert.equal(info.matched, true);
  assert.deepEqual(info.topics, [{ name: 'Stereo', index: 0 }]);
  const none = Render.describe(paper({ title: 'Other', summary: 'x' }), ['RLVR'], [], TOPICS);
  assert.equal(none.matched, false);
});

test('a list row shows topic, title, authors and the pending state', () => {
  const info = Render.describe(paper({ pending: true }), ['stereo'], [], TOPICS);
  const html = Render.renderRow(paper({ pending: true }), info, true);
  assert.match(html, /data-id="2610.00001"/);
  assert.match(html, /aria-current="true"/);
  assert.match(html, /class="row-topic topic-0"/);
  assert.match(html, /Summary pending/);
  assert.match(html, /Ada Lovelace, Alan Turing/);
});

test('the reading pane shows TL;DR, the four fields and links for a summarised paper', () => {
  const p = paper({ AI, pending: false, code_url: 'https://github.com/a/b' });
  const info = Render.describe(p, ['stereo'], [], TOPICS);
  const html = Render.renderReader(p, info, ['stereo']);
  assert.match(html, /<h2 class="reader-title" id="readerTitle">/);
  assert.match(html, /class="tldr"/);
  assert.match(html, /Converts mono video to <mark class="hl">stereo<\/mark>\./);
  assert.match(html, /<h3>Conclusion<\/h3><p>c<\/p>/);
  assert.match(html, /href="https:\/\/arxiv.org\/pdf\/2610.00001"/);
  assert.match(html, /href="https:\/\/github.com\/a\/b"/);
});

test('the reading pane of a pending paper shows the escaped abstract and says so', () => {
  const p = paper({ pending: true });
  const html = Render.renderReader(p, Render.describe(p, [], [], TOPICS), []);
  assert.match(html, /summary has not been written yet/);
  assert.match(html, /disparity &lt;with&gt; care/);
  assert.doesNotMatch(html, /class="tldr"/);
});

test('the day sentence counts papers and matches', () => {
  assert.equal(Render.daySentence(910, 56, true), '910 new papers, 56 matching your interests.');
  assert.equal(Render.daySentence(1, 1, true), '1 new paper, 1 matching your interests.');
  assert.equal(Render.daySentence(5, 0, false), '5 new papers.');
});

test('topics come from the presets, with extra keywords in their own topic', () => {
  const presets = { topics: TOPICS };
  assert.deepEqual(Render.topicsFor(['stereo', 'RLVR', 'diffusion'], presets), [
    { name: 'Stereo', keywords: ['stereo'] },
    { name: 'RL', keywords: ['RLVR'] },
    { name: 'Your other keywords', keywords: ['diffusion'] },
  ]);
});

test('the main button opens alphaXiv by default, with arXiv kept as a link', () => {
  const p = paper({ AI, pending: false });
  const info = Render.describe(p, [], [], TOPICS);
  const html = Render.renderReader(p, info, []);
  assert.match(html, /<a class="button-solid" href="https:\/\/www.alphaxiv.org\/abs\/2610.00001"[^>]*>Open on alphaXiv<\/a>/);
  assert.match(html, /<a class="button-outline" href="https:\/\/arxiv.org\/abs\/2610.00001"[^>]*>arXiv<\/a>/);
  const arxivFirst = Render.renderReader(p, info, [], { primaryLink: 'arxiv' });
  assert.match(arxivFirst, /<a class="button-solid" href="https:\/\/arxiv.org\/abs\/2610.00001"[^>]*>Open on arXiv<\/a>/);
  assert.match(arxivFirst, /<a class="button-outline" href="https:\/\/www.alphaxiv.org\/abs\/2610.00001"[^>]*>alphaXiv<\/a>/);
});

test('code links are a repository or a project page, and absent otherwise', () => {
  assert.equal(Render.codeKind(paper({ code_url: 'https://github.com/a/b' })), 'code');
  assert.equal(Render.codeKind(paper({ code_url: 'https://anonymous.4open.science/r/x' })), 'code');
  assert.equal(Render.codeKind(paper({ code_url: 'https://a.github.io/proj' })), 'page');
  assert.equal(Render.codeKind(paper({ code_url: 'https://a.gitlab.io/proj/' })), 'page');
  assert.equal(Render.codeKind(paper({})), null);
});

test('a row marks linked code or a project page, and nothing when there is none', () => {
  const info = Render.describe(paper({}), [], [], TOPICS);
  assert.match(Render.renderRow(paper({ code_url: 'https://github.com/a/b' }), info, false), /<span class="row-code"[^>]*>.*Code<\/span>/);
  assert.match(Render.renderRow(paper({ code_url: 'https://a.github.io/p' }), info, false), /<span class="row-code is-page"[^>]*>.*Project page<\/span>/);
  assert.doesNotMatch(Render.renderRow(paper({}), info, false), /row-code/);
});

test('the reading pane names the link as code or a project page', () => {
  const info = Render.describe(paper({}), [], [], TOPICS);
  assert.match(Render.renderReader(paper({ code_url: 'https://github.com/a/b' }), info, []), />Code<\/a>/);
  assert.match(Render.renderReader(paper({ code_url: 'https://a.github.io/p' }), info, []), />Project page<\/a>/);
});
