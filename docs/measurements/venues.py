"""Random 2024 samples from named venues; record whether each work has an arXiv location in OpenAlex."""
import json, sys, time, urllib.parse, urllib.request
UA = {"User-Agent": "daily-arxiv-coverage-check/0.1"}
FIXED = {"CVPR": ("S4210176548", 2024), "ICCV": ("S4363607764", 2023), "ICML": ("S4306419644", 2024), "ICLR": ("S4306419637", 2024),
         "ACL": ("S4393915740", 2024), "ICIP": ("S4210223844", 2024), "JMLR": ("S118988714", 2023)}
VENUES = [
    ("CVPR", "Computer Vision and Pattern Recognition"), ("NeurIPS", "Neural Information Processing Systems"),
    ("ICML", "International Conference on Machine Learning"), ("ACL", "Annual Meeting of the Association for Computational Linguistics"),
    ("TPAMI", "IEEE Transactions on Pattern Analysis and Machine Intelligence"), ("TIP", "IEEE Transactions on Image Processing"),
    ("TCSVT", "IEEE Transactions on Circuits and Systems for Video Technology"), ("TVCG", "IEEE Transactions on Visualization and Computer Graphics"),
    ("ACM TOG", "ACM Transactions on Graphics"), ("Pattern Recognition", "Pattern Recognition"),
    ("Neurocomputing", "Neurocomputing"), ("Neural Networks", "Neural Networks"),
    ("ICASSP", "IEEE International Conference on Acoustics, Speech, and Signal Processing"), ("ICIP", "IEEE International Conference on Image Processing"),
    ("Journal of Vision", "Journal of Vision"), ("JMLR", "Journal of Machine Learning Research"),
]
def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r: return json.load(r)
        except Exception as e: err = e; time.sleep(3 * (i + 1))
    raise err
def has_arxiv(w):
    for loc in w.get("locations") or []:
        src = (loc.get("source") or {}).get("display_name") or ""
        url = (loc.get("landing_page_url") or "") + (loc.get("pdf_url") or "")
        if "arxiv" in src.lower() or "arxiv.org" in url: return True
    return False
out = []
import os
ONLY = set(os.environ.get("ONLY", "").split(",")) - {""}
for short, name in VENUES + [("ICCV", "x"), ("ICLR", "x")]:
    if ONLY and short not in ONLY:
        continue
    if short in FIXED:
        sid, year = FIXED[short]
        src = {"id": sid, "display_name": short + " (fixed id)"}
        params = {"filter": f"primary_location.source.id:{sid},publication_year:{year}", "sample": "40", "seed": "7", "per-page": "40", "select": "id,doi,title,publication_year,locations,primary_location"}
        res = get("https://api.openalex.org/works?" + urllib.parse.urlencode(params))["results"]
        for w in res:
            if w.get("title"):
                out.append({"venue": short, "source": src["display_name"], "id": w["id"], "doi": w.get("doi"), "title": w["title"], "arxiv": has_arxiv(w), "sort": "venue"})
        print(short, "->", src["display_name"], len(res), sum(has_arxiv(w) for w in res), flush=True)
        continue
    found = get("https://api.openalex.org/sources?" + urllib.parse.urlencode({"search": name, "per-page": "5", "select": "id,display_name,works_count,type"}))["results"]
    found = sorted(found, key=lambda s: -s["works_count"])
    exact = [s for s in found if s["display_name"].lower().startswith(name.lower()[:25])] or found
    src = exact[0]
    params = {"filter": f"primary_location.source.id:{src['id'].split('/')[-1]},publication_year:2024", "sample": "40", "seed": "7", "per-page": "40",
              "select": "id,doi,title,publication_year,locations,primary_location"}
    res = get("https://api.openalex.org/works?" + urllib.parse.urlencode(params))["results"]
    for w in res:
        if w.get("title"):
            out.append({"venue": short, "source": src["display_name"], "id": w["id"], "doi": w.get("doi"), "title": w["title"], "arxiv": has_arxiv(w), "sort": "venue"})
    print(short, "->", src["display_name"], len(res), sum(has_arxiv(w) for w in res), flush=True)
    time.sleep(0.3)
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
