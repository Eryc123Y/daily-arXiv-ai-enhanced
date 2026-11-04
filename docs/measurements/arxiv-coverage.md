# How much of the literature is on arXiv (2026-11-04)

Question: if the pipeline reads only arXiv, how much of what is published in Eric's fields does it miss?

## Method

- 40 papers drawn at random (OpenAlex `sample=40`, seed 7) from each of 15 venues, published in 2024 (ICCV: 2023, it runs in odd years). 600 papers.
- A paper counts as on arXiv when OpenAlex lists an arXiv location for it. Every paper without one was searched on arXiv by title (all title words of three letters or more, a match is a title similarity above 0.9). That found 3 more of 391, so OpenAlex's arXiv links are reliable.
- A paper renamed between its arXiv version and publication is missed by both checks, so the shares below are lower bounds.
- Scripts: [venues.py](venues.py), [verify.py](verify.py). ICML, ICLR and JMLR are left out: OpenAlex returned no papers for them in these years.

## Result

| Venue | Kind | On arXiv |
|---|---|---|
| NeurIPS | ML conference | 85% |
| CVPR | CV conference | 72% |
| ICCV | CV conference | 62% |
| ACL | NLP conference | 57% |
| ACM TOG (SIGGRAPH) | graphics journal | 50% |
| IEEE TPAMI | journal | 45% |
| IEEE TIP | journal | 38% |
| IEEE TVCG (VR, displays) | journal | 30% |
| ICASSP | signal-processing conference | 28% |
| ICIP | image-processing conference | 28% |
| IEEE TCSVT | video journal | 10% |
| Neural Networks (Elsevier) | journal | 10% |
| Pattern Recognition (Elsevier) | journal | 8% |
| Neurocomputing (Elsevier) | journal | 8% |
| Journal of Vision | vision-science journal | 0% |

## What it means for the pipeline

- The top ML and CV conferences are mostly on arXiv (62-85%), so the daily arXiv feed sees most of what matters for the weak-supervision and data-reuse project, but still misses roughly one paper in four or five even there.
- For the stereo and 3D-video direction the gap is large: graphics (TOG 50%), video and image processing (TCSVT 10%, TIP 38%, ICIP 28%), VR and displays (TVCG 30%) and human stereo perception (Journal of Vision 0%) are mostly not on arXiv.
- Elsevier's ML journals are almost entirely absent (8-10%).
- So a second source of metadata (OpenAlex or Crossref, both free) would add the most for the stereo direction and for journals; publisher APIs (Elsevier, IEEE Xplore) matter only for full text. Publisher abstracts are often copyrighted, so they can be stored only behind the M2 login, never on the public `data` branch.
