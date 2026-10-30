/**
 * Default interest topics and keywords, used until keywords are saved in the
 * "Keywords & authors" dialog.
 * Seeded on 2026-10-30 from the arXiv daily digest's project brief (weak
 * supervision, data reuse, RLVR), its 2D-to-3D / stereo focus list, and the
 * two routes of the Research Soul core question (continual learning; which
 * data representations are most learnable). Keywords that mostly matched
 * unrelated papers (disparity, off-policy, PPO, sample efficiency, ...) are
 * left out or narrowed.
 */
(function (root) {
  const TOPICS = [
    {
      name: '2D-to-3D and stereo',
      keywords: [
        'stereo',
        'stereoscopic',
        '2D-to-3D',
        'monocular-to-stereo',
        'disparity estimation',
        'disparity map',
        'binocular',
        'novel view',
        'view synthesis',
        '3D video',
        'spatial video',
        'VR video',
        'depth-based rendering',
        'dual-view',
        'anaglyph',
        'monocular depth',
        'video depth',
      ],
    },
    {
      name: 'Weak supervision and data reuse',
      keywords: [
        'weak supervision',
        'weakly supervised',
        'partial label',
        'complementary label',
        'candidate label',
        'bandit feedback',
        'binary reward',
        'verifiable reward',
        'RLVR',
        'outcome reward',
        'GRPO',
        'data reuse',
        'sample reuse',
        'rollout reuse',
        'repeated epochs',
        'multiple epochs',
        'multi-epoch',
        'ideal observer',
        'Bayes-optimal',
        'PAC learning',
        'cross-situational',
        'word learning',
        'referential game',
        'emergent communication',
      ],
    },
    {
      name: 'Continual learning',
      keywords: [
        'continual learning',
        'lifelong learning',
        'catastrophic forgetting',
        'loss of plasticity',
        'test-time training',
        'incremental learning',
        'knowledge injection',
      ],
    },
    {
      name: 'Data and representation',
      keywords: [
        'tokenization',
        'tokenizer',
        'learnability',
        'data-constrained',
        'repeated data',
        'data repetition',
        'data representation',
      ],
    },
  ];

  // Default lists shipped before; a browser that saved one of these unchanged
  // gets the current defaults instead of a frozen copy.
  const PREVIOUS_DEFAULTS = [
    [
      'stereo',
      'stereoscopic',
      '2D-to-3D',
      'monocular-to-stereo',
      'disparity',
      'binocular',
      'novel view',
      'view synthesis',
      '3D video',
      'spatial video',
      'VR video',
      'depth-based rendering',
      'dual-view',
      'anaglyph',
      'weak supervision',
      'weakly supervised',
      'partial label',
      'complementary label',
      'candidate label',
      'bandit feedback',
      'binary reward',
      'verifiable reward',
      'RLVR',
      'outcome reward',
      'GRPO',
      'PPO',
      'data reuse',
      'sample reuse',
      'rollout reuse',
      'repeated epochs',
      'multiple epochs',
      'multi-epoch',
      'data-constrained',
      'off-policy',
      'sample efficiency',
      'sample complexity',
      'ideal observer',
      'Bayes-optimal',
      'information-theoretic',
      'knowledge injection',
      'cross-situational',
      'word learning',
      'referential game',
      'emergent communication',
    ],
  ];

  const INTEREST_PRESETS = {
    version: '2026-10-31',
    topics: TOPICS,
    keywords: TOPICS.flatMap(topic => topic.keywords),
    previousDefaults: PREVIOUS_DEFAULTS,
  };

  const sameSet = (a, b) => {
    const norm = list => [...new Set(list.map(k => k.trim().toLowerCase()))].sort().join('\n');
    return norm(a) === norm(b);
  };

  /** Keywords to use given what a browser saved, and whether to drop the saved copy. */
  function keywordsFor(saved) {
    if (!Array.isArray(saved)) return { keywords: INTEREST_PRESETS.keywords, clearSaved: false };
    const isDefault = [INTEREST_PRESETS.keywords, ...PREVIOUS_DEFAULTS].some(list => sameSet(saved, list));
    return isDefault ? { keywords: INTEREST_PRESETS.keywords, clearSaved: true } : { keywords: saved, clearSaved: false };
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { INTEREST_PRESETS, keywordsFor };
  } else {
    root.INTEREST_PRESETS = INTEREST_PRESETS;
    root.keywordsFor = keywordsFor;
  }
})(typeof self !== 'undefined' ? self : this);
