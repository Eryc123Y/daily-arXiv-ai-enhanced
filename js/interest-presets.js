/**
 * Default highlight keywords, used until keywords are saved in Settings.
 * Seeded on 2026-10-30 from the arXiv daily digest's project brief (weak
 * supervision, data reuse, RLVR) and its 2D-to-3D / stereo focus list.
 */
(function (root) {
  const INTEREST_PRESETS = {
    version: '2026-10-30',
    keywords: [
      // 2D-to-3D conversion and stereo vision
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
      // Weak supervision, data reuse and RL post-training efficiency
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
  };

  if (typeof module === 'object' && module.exports) {
    module.exports = { INTEREST_PRESETS };
  } else {
    root.INTEREST_PRESETS = INTEREST_PRESETS;
  }
})(typeof self !== 'undefined' ? self : this);
