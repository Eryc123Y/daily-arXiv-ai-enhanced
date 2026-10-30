const test = require('node:test');
const assert = require('node:assert/strict');

const PaperData = require('../../js/paper-data.js');
const { INTEREST_PRESETS } = require('../../js/interest-presets.js');

const AI = { tldr: '总结', motivation: '动机', method: '方法', result: '结果', conclusion: '结论' };
const paper = (id, extra = {}) => ({ id, title: `T${id}`, summary: `S${id}`, categories: ['cs.CV'], ...extra });
const jsonl = rows => rows.map(r => JSON.stringify(r)).join('\n') + '\n';

test('file list yields every date with raw or summary files, newest first', () => {
  const list = PaperData.parseFileList([
    '2026-10-28.jsonl',
    '2026-10-28_AI_enhanced_Chinese.jsonl',
    '2026-10-30.jsonl',
    '2026-10-29_AI_enhanced_English.jsonl',
    'README.md',
    '',
  ].join('\n'));

  assert.deepEqual(list.dates, ['2026-10-30', '2026-10-29', '2026-10-28']);
  assert.deepEqual(list.languages.get('2026-10-28'), ['Chinese']);
  assert.deepEqual(list.languages.get('2026-10-30'), []);
  assert.equal(list.rawDates.has('2026-10-30'), true);
  assert.equal(list.rawDates.has('2026-10-29'), false);
});

test('a day merges raw papers with summaries and marks the rest pending', () => {
  const raw = jsonl([paper('1'), paper('2'), paper('1'), paper('3')]);
  const ai = jsonl([{ ...paper('2'), AI: AI }, { ...paper('3'), AI: { tldr: 'partial' } }]);

  const records = PaperData.mergeDay(raw, ai);

  assert.deepEqual(records.map(r => [r.id, r.pending]), [['1', true], ['2', false], ['3', true]]);
  assert.deepEqual(records[1].AI, AI);
});

test('a day without a raw file still shows its summary records', () => {
  const records = PaperData.mergeDay('', jsonl([{ ...paper('9'), AI: AI }]));
  assert.deepEqual(records.map(r => [r.id, r.pending]), [['9', false]]);
});

test('malformed lines are skipped', () => {
  const records = PaperData.mergeDay('{"id": "1", "title": "x"}\nnot json\n', '404: Not Found');
  assert.deepEqual(records.map(r => r.id), ['1']);
});

test('keywords match whole words, ignore case and hyphens, and allow plurals', () => {
  const m = PaperData.keywordMatches;
  assert.equal(m('Monocular 2D-to-3D video conversion', '2D to 3D'), true);
  assert.equal(m('Learning from Partial-Label data', 'partial label'), true);
  assert.equal(m('Stereo matching with transformers', 'stereo'), true);
  assert.equal(m('Novel views from a single image', 'novel view'), true);
  assert.equal(m('We support PPOs and GRPO', 'PPO'), true);
  assert.equal(m('Gender stereotypes in LLMs', 'stereo'), false);
  assert.equal(m('We support robust training', 'PPO'), false);
  assert.equal(m('', 'stereo'), false);
  assert.equal(m('一种立体视频生成方法', '立体'), true);
});

test('highlight wraps matches once and keeps surrounding text', () => {
  const html = PaperData.highlight('Stereo video and stereo-matching, not stereotypes', ['stereo', 'stereo matching'], 'hl');
  assert.equal(
    html,
    '<span class="hl">Stereo</span> video and <span class="hl">stereo-matching</span>, not stereotypes'
  );
  assert.equal(PaperData.highlight('plain', [], 'hl'), 'plain');
});

test('escapeHtml neutralises markup in abstracts', () => {
  assert.equal(PaperData.escapeHtml('$a<b$ & "c"'), '$a&lt;b$ &amp; &quot;c&quot;');
});

test('interest presets cover both of Eric\'s focus areas without duplicates', () => {
  const keywords = INTEREST_PRESETS.keywords;
  for (const expected of ['stereo', '2D-to-3D', 'disparity', 'novel view', 'view synthesis', 'RLVR', 'data reuse', 'repeated epochs', 'weak supervision', 'sample efficiency']) {
    assert.ok(keywords.includes(expected), expected);
  }
  assert.equal(new Set(keywords.map(k => k.toLowerCase())).size, keywords.length);
});

test('preset topics hold exactly the flat keyword list', () => {
  const flat = INTEREST_PRESETS.topics.flatMap(t => t.keywords);
  assert.deepEqual(flat, INTEREST_PRESETS.keywords);
  assert.ok(INTEREST_PRESETS.topics.length >= 2);
});
