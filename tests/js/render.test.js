const test = require('node:test');
const assert = require('node:assert/strict');

const Render = require('../../js/render.js');

const AI = { tldr: 'Converts mono video to stereo.', motivation: 'm', method: 'x', result: 'r', conclusion: 'c' };
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
  assert.equal(Render.authorLine(['Solo']), 'Solo');
});

test('matches come from title, abstract and TL;DR, and from authors', () => {
  const match = Render.matchesFor(paper({ AI, pending: false }), ['stereo', 'disparity', 'RLVR'], ['turing']);
  assert.deepEqual(match, { keywords: ['stereo', 'disparity'], authors: ['turing'] });
});

test('a summarised paper shows its TL;DR and the four other fields', () => {
  const html = Render.renderPaper(paper({ AI, pending: false }), { keywords: ['stereo'], authors: [] }, ['stereo']);
  assert.match(html, /class="paper is-match"/);
  assert.match(html, /Matches stereo/);
  assert.match(html, /<p class="paper-tldr">Converts mono video to <span class="hl">stereo<\/span>\.<\/p>/);
  assert.match(html, /<dt>Conclusion<\/dt><dd>c<\/dd>/);
  assert.match(html, /href="https:\/\/arxiv.org\/pdf\/2610.00001"/);
});

test('a pending paper shows its escaped abstract and says the summary is not written yet', () => {
  const html = Render.renderPaper(paper({ pending: true }), { keywords: [], authors: [] }, []);
  assert.match(html, /is-pending/);
  assert.match(html, /disparity &lt;with&gt; care/);
  assert.match(html, /Summary not written yet/);
  assert.doesNotMatch(html, /paper-tldr/);
});

test('the day sentence counts papers and matches', () => {
  assert.equal(Render.daySentence(910, 56, true), '910 new papers; 56 match your interests.');
  assert.equal(Render.daySentence(1, 1, true), '1 new paper; 1 matches your interests.');
  assert.equal(Render.daySentence(5, 0, false), '5 new papers.');
});

test('topics come from the presets, with extra keywords in their own topic', () => {
  const presets = { topics: [{ name: 'Stereo', keywords: ['stereo', 'disparity'] }, { name: 'RL', keywords: ['RLVR'] }] };
  const topics = Render.topicsFor(['stereo', 'RLVR', 'diffusion'], presets);
  assert.deepEqual(topics, [
    { name: 'Stereo', keywords: ['stereo'] },
    { name: 'RL', keywords: ['RLVR'] },
    { name: 'Your other keywords', keywords: ['diffusion'] },
  ]);
});

test('a paper belongs to every topic one of whose keywords it matches', () => {
  const topics = [{ name: 'Stereo', keywords: ['stereo'] }, { name: 'RL', keywords: ['RLVR'] }];
  assert.deepEqual(Render.topicNames({ keywords: ['stereo'], authors: [] }, topics), ['Stereo']);
  assert.deepEqual(Render.topicNames({ keywords: [], authors: [] }, topics), []);
});
