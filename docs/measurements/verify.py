"""For works OpenAlex shows without an arXiv copy, search arXiv by title (3 s apart) and mark found ones."""
import json, re, sys, time, urllib.parse, urllib.request, difflib
UA = {"User-Agent": "daily-arxiv-coverage-check/0.1"}
def norm(t): return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (t or "").lower())).strip()
def on_arxiv(title):
    words = [w for w in norm(title).split() if len(w) > 2][:12]
    q = " AND ".join(f"ti:{w}" for w in words)
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": q, "max_results": 5})
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                xml = r.read().decode("utf-8", "replace"); break
        except Exception:
            time.sleep(10)
    else:
        return None
    titles = re.findall(r"<entry>.*?<title>(.*?)</title>", xml, re.S)
    return any(difflib.SequenceMatcher(None, norm(t), norm(title)).ratio() > 0.9 for t in titles)
path, select = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "all"
works = json.load(open(path))
todo = [w for w in works if not w["arxiv"] and (select == "all" or w.get("sort") == select)]
for i, w in enumerate(todo):
    w["arxiv_by_title"] = on_arxiv(w["title"])
    time.sleep(3)
json.dump(works, open(path, "w"), ensure_ascii=False, indent=1)
print("checked", len(todo), "found on arXiv by title:", sum(1 for w in todo if w["arxiv_by_title"]), "unknown:", sum(1 for w in todo if w["arxiv_by_title"] is None))
