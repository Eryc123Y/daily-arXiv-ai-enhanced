const test = require('node:test');
const assert = require('node:assert/strict');

const { repoFromLocation } = require('../../js/data-config.js');

const FALLBACK = { owner: 'Eryc123Y', repo: 'daily-arXiv-ai-enhanced' };

test('a fork on GitHub Pages reads data from its own repository', () => {
  assert.deepEqual(
    repoFromLocation({ hostname: 'alice.github.io', pathname: '/my-arxiv/' }, FALLBACK),
    { owner: 'alice', repo: 'my-arxiv' }
  );
  assert.deepEqual(
    repoFromLocation({ hostname: 'Alice.GitHub.io', pathname: '/my-arxiv/index.html' }, FALLBACK),
    { owner: 'alice', repo: 'my-arxiv' }
  );
});

test('a user site at the root maps to the owner.github.io repository', () => {
  assert.deepEqual(
    repoFromLocation({ hostname: 'alice.github.io', pathname: '/index.html' }, FALLBACK),
    { owner: 'alice', repo: 'alice.github.io' }
  );
});

test('anywhere else (local preview, own server, custom domain) uses the configured repository', () => {
  assert.deepEqual(repoFromLocation({ hostname: 'localhost', pathname: '/' }, FALLBACK), FALLBACK);
  assert.deepEqual(repoFromLocation({ hostname: 'arxiv.example.org', pathname: '/' }, FALLBACK), FALLBACK);
  assert.deepEqual(repoFromLocation(undefined, FALLBACK), FALLBACK);
});
