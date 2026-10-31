const test = require('node:test');
const assert = require('node:assert/strict');

global.PaperData = require('../../js/paper-data.js');
const { createStaticSource, LoadError } = require('../../js/data-source.js');

const RAW = JSON.stringify({ id: '2610.00001', title: 'T', summary: 'abstract', authors: ['A'], categories: ['cs.CV'] });
const respond = (status, body = '') => Promise.resolve({ ok: status >= 200 && status < 300, status, text: () => Promise.resolve(body) });

function source(routes) {
  const fetchImpl = path => {
    const route = Object.keys(routes).find(key => path.endsWith(key));
    const answer = route ? routes[route] : 404;
    return answer instanceof Error ? Promise.reject(answer) : respond(...[].concat(answer));
  };
  return createStaticSource({ fetch: fetchImpl, url: path => `https://example.test/${path}` });
}

test('a day without summaries yet loads its papers as pending', async () => {
  const day = await source({ 'data/2026-10-30.jsonl': [200, RAW] }).loadDay('2026-10-30');
  assert.equal(day.length, 1);
  assert.equal(day[0].pending, true);
});

test('a missing paper file is an error, not an empty day', async () => {
  await assert.rejects(source({}).loadDay('2026-10-30'), err => err instanceof LoadError && err.status === 404);
});

test('a server error or network failure is an error, not an empty day', async () => {
  await assert.rejects(source({ 'data/2026-10-30.jsonl': 500 }).loadDay('2026-10-30'), err => err instanceof LoadError && err.status === 500);
  await assert.rejects(source({ 'data/2026-10-30.jsonl': new TypeError('Failed to fetch') }).loadDay('2026-10-30'), err => err instanceof LoadError && err.status === null);
});

test('a broken summary file is an error too', async () => {
  await assert.rejects(source({ 'data/2026-10-30.jsonl': [200, RAW], '_English.jsonl': 503 }).loadDay('2026-10-30'), LoadError);
});

test('a fork with no data yet lists no days, but an unreachable list is an error', async () => {
  assert.deepEqual((await source({}).listDays()).days, []);
  await assert.rejects(source({ 'assets/file-list.txt': new TypeError('offline') }).listDays(), LoadError);
});
