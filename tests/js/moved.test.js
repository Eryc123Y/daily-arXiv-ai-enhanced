const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const NEW_HOME = 'https://litscout.turing2234.com/';
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'index.html'), 'utf8');
const inline = html.match(/<script id="moved">([\s\S]*?)<\/script>/);

/** Runs index.html's inline redirect at a fake address; returns where it sent the visitor, or null. */
function visit(url) {
  const at = new URL(url);
  let sentTo = null;
  const location = {
    hostname: at.hostname, pathname: at.pathname, search: at.search, hash: at.hash,
    replace(target) { sentTo = target; },
  };
  vm.runInNewContext(inline[1], { location });
  return sentTo;
}

test('index.html has the redirect inline, before any stylesheet or script it loads', () => {
  assert.ok(inline, 'missing <script id="moved"> in index.html');
  const at = html.indexOf('<script id="moved">');
  assert.ok(at < html.indexOf('<link rel="stylesheet"'));
  assert.ok(at < html.indexOf('<script src='));
});

test('index.html names the new address as canonical', () => {
  assert.match(html, new RegExp(`<link rel="canonical" href="${NEW_HOME}">`));
});

test('the old GitHub Pages address moves to the new one, keeping query and hash', () => {
  const old = 'https://eryc123y.github.io/daily-arXiv-ai-enhanced/';
  assert.equal(visit(old), NEW_HOME);
  assert.equal(visit(`${old}#day=2026-11-11&paper=2611.01234`), `${NEW_HOME}#day=2026-11-11&paper=2611.01234`);
  assert.equal(visit(`${old}?json=1#day=2026-11-11&topic=all`), `${NEW_HOME}?json=1#day=2026-11-11&topic=all`);
  assert.equal(visit(`${old}index.html#day=2026-11-11`), `${NEW_HOME}#day=2026-11-11`);
  assert.equal(visit('https://eryc123y.github.io/daily-arXiv-ai-enhanced'), NEW_HOME);
  assert.equal(visit('https://eryc123y.github.io/daily-arxiv-ai-enhanced/'), NEW_HOME);
});

test('forks, other paths and other hosts stay where they are', () => {
  for (const url of [
    'https://alice.github.io/daily-arXiv-ai-enhanced/',
    'https://alice.github.io/my-arxiv/#day=2026-11-11',
    'https://eryc123y.github.io/',
    'https://eryc123y.github.io/other-repo/',
    'https://eryc123y.github.io/daily-arXiv-ai-enhanced-old/',
    'https://eryc123y.github.io/daily-arXiv-ai-enhanced/statistic.html',
    'https://litscout.turing2234.com/#day=2026-11-11',
    'http://localhost:8000/',
    'http://127.0.0.1:8000/index.html',
  ]) {
    assert.equal(visit(url), null, url);
  }
});
