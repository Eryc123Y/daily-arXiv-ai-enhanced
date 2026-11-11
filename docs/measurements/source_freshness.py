"""How fresh and how useful non-arXiv sources are for a daily feed (spec S1, R0).

For a look-back of WINDOW days ending today it asks:
- OpenAlex, per venue of the spec's watch list (`primary_location.source.id`);
- Crossref, per journal by ISSN, plus ECCV by its LNCS container title;
- OpenReview API v2, for ICLR, ICML, NeurIPS and TMLR (needs OPENREVIEW_TOKEN:
  the anonymous API answers scripts with a browser challenge since 2026-11).
and prints, per source and venue: papers per day, papers matching Eric's topics,
listing delay (median, p90), shares with abstract / open-access link / arXiv
version, papers the site already published, and the OpenAlex cost of a feed.

Run:  OPENALEX_API_KEY=... uv run python docs/measurements/source_freshness.py
Raw responses go to .cache/freshness/<today>/ (git-ignored). The key is read from
the environment and never printed. The run stops cleanly when OpenAlex quota runs
out and summarises what it has.
"""

import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WINDOW = 14            # days a source has to list a paper for it to count as new
PUB_LOOKBACK = 365     # OpenAlex: publication dates scanned to find works listed in the window
SITE_DAYS = 60         # data/<date>.jsonl files on origin/data compared against
DAILY_MAX_MEDIAN = 3   # spec Q5: median delay of 3 days or less is daily
SMALL_SAMPLE = 20
UA = {"User-Agent": "litscout-freshness-check/0.1"}

# Watch list v1 (docs/specs/s1-sources-beyond-arxiv.md). OpenAlex ids from a
# /sources search on 2026-11-11; None where OpenAlex has no source of its own.
WATCH = [
    # name, group, OpenAlex source, ISSNs (journals only), OpenReview venue ids
    ("CVPR", "ML and CV conferences", "S4210176548", [], []),
    ("ICCV", "ML and CV conferences", "S4363607764", [], []),
    ("ECCV", "ML and CV conferences", None, [], []),  # inside LNCS; Crossref by container title
    ("NeurIPS", "ML and CV conferences", "S4363606243", [], ["NeurIPS.cc/2026/Conference"]),
    ("ICML", "ML and CV conferences", "S4306419644", [], ["ICML.cc/2026/Conference"]),
    ("ICLR", "ML and CV conferences", "S4306419637", [], ["ICLR.cc/2026/Conference", "ICLR.cc/2027/Conference/Submission"]),
    ("AAAI", "ML and CV conferences", "S4210191458", [], []),
    ("IJCAI", "ML and CV conferences", "S4306419999", [], []),
    ("ACM MM", "ML and CV conferences", "S4363608757", [], []),
    ("ACM TOG", "Graphics and VR", "S185367456", ["0730-0301", "1557-7368"], []),
    ("IEEE TVCG", "Graphics and VR", "S84775595", ["1077-2626", "1941-0506"], []),
    ("CGF", "Graphics and VR", "S67831204", ["0167-7055", "1467-8659"], []),
    ("IEEE TPAMI", "Journals", "S199944782", ["0162-8828", "1939-3539"], []),
    ("IJCV", "Journals", "S25538012", ["0920-5691", "1573-1405"], []),
    ("IEEE TIP", "Journals", "S4210173141", ["1057-7149", "1941-0042"], []),
    ("IEEE TCSVT", "Journals", "S115173108", ["1051-8215", "1558-2205"], []),
    ("JMLR", "Journals", "S118988714", ["1532-4435", "1533-7928"], []),
    ("TMLR", "Journals", "S4393919742", ["2835-8856"], ["TMLR"]),
    ("Journal of Vision", "Vision science", "S137468011", ["1534-7362"], []),
]
ECCV_CONTAINER = "ECCV 2026"


# ---------------------------------------------------------------- pure helpers

def parse_date(text):
    """'2026-11-03' or '2026-11-03T..' -> date; None for anything else."""
    try:
        return dt.date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def crossref_date(field):
    """Crossref {'date-parts': [[y, m, d]]} -> (date, exact). Partial dates fall on the 1st and are not exact."""
    parts = ((field or {}).get("date-parts") or [[None]])[0]
    if not parts or parts[0] is None:
        return None, False
    year, month, day = (list(parts) + [1, 1])[:3]
    try:
        return dt.date(int(year), int(month or 1), int(day or 1)), len(parts) >= 3
    except ValueError:
        return None, False


def abstract_text(inverted):
    """OpenAlex abstract_inverted_index -> plain text ('' when missing)."""
    if not inverted:
        return ""
    slots = {}
    for word, positions in inverted.items():
        for pos in positions:
            slots[pos] = word
    return " ".join(slots[i] for i in sorted(slots))


def strip_tags(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def normalize_title(title):
    """Lowercase letters and digits only, single spaces: the key for title matches."""
    text = strip_tags(title).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


ARXIV_ID = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv[.:/])\s*(\d{4}\.\d{4,5})", re.I)


def arxiv_id(text):
    """First new-style arXiv id in a URL or DOI (10.48550/arXiv.2611.01234), without version."""
    match = ARXIV_ID.search(text or "")
    return match.group(1) if match else None


def delay_days(published, listed):
    return (listed - published).days if published and listed else None


def date_flags(published, listed, today, exact=True):
    """Why a record's publication date cannot be trusted ([] when it can)."""
    flags = []
    if published is None:
        return ["missing"]
    if not exact:
        flags.append("partial")
    elif published.month == 1 and published.day == 1:
        flags.append("jan1")
    if published > today:
        flags.append("future")
    elif listed and published > listed:
        flags.append("after_listing")
    return flags


def quantile(values, q):
    """Linear-interpolated quantile, None for no values."""
    data = sorted(values)
    if not data:
        return None
    pos = (len(data) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    return data[low] + (data[high] - data[low]) * (pos - low)


def verdict(median_delay, papers):
    """Spec Q5: median delay <= 3 days is daily, slower is weekly; nothing listed is not worth it."""
    if not papers or median_delay is None:
        return "not worth it"
    return "daily" if median_delay <= DAILY_MAX_MEDIAN else "weekly"


def share(count, total):
    return f"{100 * count / total:.0f}%" if total else "-"


def pages_needed(works, per_page=200):
    return math.ceil(works / per_page) if works else 1


# ---------------------------------------------------------------- HTTP

class QuotaExhausted(RuntimeError):
    pass


class Http:
    def __init__(self, raw_dir):
        self.raw_dir = raw_dir
        self.counts = {"openalex": 0, "crossref": 0, "openreview": 0}
        self.openalex_remaining = None

    def get(self, service, url, params, headers=None, tag=None):
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(f"{url}?{query}", headers={**UA, **(headers or {})})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    self.counts[service] += 1
                    if service == "openalex":
                        remaining = response.headers.get("x-ratelimit-remaining")
                        self.openalex_remaining = int(remaining) if remaining else self.openalex_remaining
                    body = json.load(response)
                    break
            except urllib.error.HTTPError as error:
                if service == "openalex" and error.code in (402, 429) and attempt >= 1:
                    raise QuotaExhausted(f"OpenAlex answered {error.code}") from None
                if error.code in (401, 403, 404):
                    raise
                time.sleep(3 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError):
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"{service}: no answer after 4 tries")
        if tag:
            (self.raw_dir / f"{tag}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body


# ---------------------------------------------------------------- sources

OPENALEX_FIELDS = "id,doi,title,publication_date,created_date,abstract_inverted_index,open_access,locations"


def openalex_venue(http, source_id, today):
    """All works of a venue with a publication date in the last PUB_LOOKBACK days (or later)."""
    key = os.environ.get("OPENALEX_API_KEY", "")
    since = today - dt.timedelta(days=PUB_LOOKBACK)
    params = {"filter": f"primary_location.source.id:{source_id},from_publication_date:{since}",
              "select": OPENALEX_FIELDS, "per-page": "200", "cursor": "*"}
    if key:
        params["api_key"] = key
    works, page = [], 0
    while params["cursor"]:
        body = http.get("openalex", "https://api.openalex.org/works", params, tag=f"openalex-{source_id}-{page}")
        works.extend(body.get("results") or [])
        params = {**params, "cursor": (body.get("meta") or {}).get("next_cursor")}
        page += 1
    return works


def openalex_record(work, today):
    published, listed = parse_date(work.get("publication_date")), parse_date(work.get("created_date"))
    urls = [work.get("doi") or ""]
    for loc in work.get("locations") or []:
        urls += [loc.get("landing_page_url") or "", loc.get("pdf_url") or ""]
    arx = next(filter(None, map(arxiv_id, urls)), None)
    oa = work.get("open_access") or {}
    return {"source": "OpenAlex", "id": work.get("id"), "doi": (work.get("doi") or "").replace("https://doi.org/", "").lower(),
            "title": work.get("title") or "", "abstract": abstract_text(work.get("abstract_inverted_index")),
            "published": published, "listed": listed, "flags": date_flags(published, listed, today),
            "oa": bool(oa.get("oa_url")), "arxiv": arx}


CROSSREF_FIELDS = "DOI,title,created,published,published-online,published-print,issued,license,relation,abstract,container-title,type"


def crossref_pages(http, filters, tag, extra=None, keep=None, max_pages=40):
    params = {"filter": filters, "select": CROSSREF_FIELDS, "rows": "1000", "cursor": "*", **(extra or {})}
    items, page = [], 0
    while params["cursor"] and page < max_pages:
        body = http.get("crossref", "https://api.crossref.org/works", params, tag=f"crossref-{tag}-{page}")["message"]
        batch = body.get("items") or []
        kept = [i for i in batch if keep is None or keep(i)]
        items.extend(kept)
        if not batch or (keep and len(kept) < 0.05 * len(batch)):
            break
        params = {**params, "cursor": body.get("next-cursor")}
        page += 1
    return items


def crossref_record(item, today):
    listed, _ = crossref_date(item.get("created"))
    for field in ("published-online", "published", "issued", "published-print"):
        published, exact = crossref_date(item.get(field))
        if published:
            break
    relations = item.get("relation") or {}
    preprints = [r.get("id", "") for r in relations.get("has-preprint", [])]
    licenses = [lic.get("URL", "") for lic in item.get("license") or []]
    return {"source": "Crossref", "id": item.get("DOI"), "doi": (item.get("DOI") or "").lower(),
            "title": " ".join(item.get("title") or []), "abstract": strip_tags(item.get("abstract")),
            "published": published, "listed": listed, "flags": date_flags(published, listed, today, exact),
            "oa": any("creativecommons.org" in u for u in licenses),
            "arxiv": next(filter(None, map(arxiv_id, preprints)), None) or ("arxiv" if any("arxiv" in p.lower() for p in preprints) else None)}


def openreview_venue(http, venue_id, today):
    token = os.environ.get("OPENREVIEW_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    since_ms = int(dt.datetime.combine(first_day(today), dt.time()).timestamp() * 1000)
    notes, offset = [], 0
    while True:
        body = http.get("openreview", "https://api2.openreview.net/notes",
                        {"content.venueid": venue_id, "sort": "pdate:desc", "limit": "1000", "offset": str(offset)},
                        headers=headers, tag=f"openreview-{venue_id.replace('/', '_')}-{offset}")
        batch = body.get("notes") or []
        notes.extend(n for n in batch if (n.get("pdate") or n.get("odate") or n.get("cdate") or 0) >= since_ms)
        if len(batch) < 1000 or (batch[-1].get("pdate") or 0) < since_ms:
            return notes
        offset += 1000


def first_day(today):
    """First day of the window (inclusive): WINDOW days ending today."""
    return today - dt.timedelta(days=WINDOW - 1)


def in_window(day, today):
    return bool(day) and first_day(today) <= day <= today


def openreview_record(note, today):
    def day(ms):
        return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date() if ms else None
    content = note.get("content") or {}
    value = lambda k: (content.get(k) or {}).get("value") or ""
    published = day(note.get("pdate") or note.get("odate"))
    listed = day(note.get("odate") or note.get("pdate") or note.get("cdate"))
    return {"source": "OpenReview", "id": note.get("id"), "doi": "", "title": value("title"), "abstract": value("abstract"),
            "published": published, "listed": listed, "flags": date_flags(published, listed, today),
            "oa": bool(value("pdf")), "arxiv": None}


def crossref_created_by_doi(http, dois):
    """DOI -> Crossref `created` date (the publisher's DOI registration), 40 DOIs a request."""
    found, dois = {}, sorted({d for d in dois if d})
    for start in range(0, len(dois), 40):
        chunk = dois[start:start + 40]
        body = http.get("crossref", "https://api.crossref.org/works",
                        {"filter": ",".join(f"doi:{d}" for d in chunk), "select": "DOI,created", "rows": "100"})["message"]
        for item in body.get("items") or []:
            found[item["DOI"].lower()] = crossref_date(item.get("created"))[0]
    return found


def lag_behind_doi(records, created_by_doi):
    """Days from DOI registration to the OpenAlex listing, for records Crossref knows."""
    return [delay_days(created_by_doi[r["doi"]], r["listed"]) for r in records if created_by_doi.get(r["doi"]) and r["listed"]]


CONFERENCE_SAMPLES = [("CVPR", "S4210176548", 2025), ("ICCV", "S4363607764", 2025), ("NeurIPS", "S4363606243", 2025),
                      ("AAAI", "S4210191458", 2026), ("IJCAI", "S4306419999", 2025), ("ACM MM", "S4363608757", 2025)]


def conference_history(http, today):
    """Last proceedings of each conference: a 200-work sample of publication and listing dates."""
    key = os.environ.get("OPENALEX_API_KEY", "")
    out = {}
    for name, source_id, year in CONFERENCE_SAMPLES:
        params = {"filter": f"primary_location.source.id:{source_id},publication_year:{year}", "sample": "200", "seed": "1",
                  "per-page": "200", "select": "id,publication_date,created_date"}
        if key:
            params["api_key"] = key
        works = http.get("openalex", "https://api.openalex.org/works", params, tag=f"history-{source_id}-{year}")["results"]
        pairs = [(parse_date(w.get("publication_date")), parse_date(w.get("created_date"))) for w in works]
        delays = [delay_days(p, c) for p, c in pairs if p and c and not date_flags(p, c, today)]
        out[f"{name} {year}"] = {"n": len(works), "reliable": len(delays), "median": quantile(delays, 0.5), "p90": quantile(delays, 0.9),
                                 "published": sorted({str(p) for p, _ in pairs if p})[:3],
                                 "listed_from": str(min((c for _, c in pairs if c), default=None)),
                                 "listed_to": str(max((c for _, c in pairs if c), default=None))}
    return out


def eccv_listing(http, today):
    """ECCV 2026 chapters in Crossref since August: when Springer registered them."""
    items = crossref_pages(http, "from-created-date:2026-08-01,type:book-chapter,prefix:10.1007", "ECCV-all",
                           extra={"query.container-title": f"Computer Vision {ECCV_CONTAINER}", "sort": "score"},
                           keep=lambda i: any(ECCV_CONTAINER in c for c in i.get("container-title") or []), max_pages=6)
    recs = [crossref_record(i, today) for i in items]
    created = sorted(r["listed"] for r in recs if r["listed"])
    return {"n": len(recs), "listed_from": str(created[0]) if created else None, "listed_to": str(created[-1]) if created else None,
            "listed_median": str(created[len(created) // 2]) if created else None,
            "published": sorted({str(r["published"]) for r in recs if r["published"]})[:5]}


# ---------------------------------------------------------------- site and topics

def site_index(today):
    """arXiv ids and normalized titles of the last SITE_DAYS days on origin/data."""
    ids, titles = set(), set()
    for back in range(SITE_DAYS):
        day = today - dt.timedelta(days=back)
        shown = subprocess.run(["git", "show", f"origin/data:data/{day}.jsonl"], cwd=ROOT, capture_output=True, text=True)
        for line in shown.stdout.splitlines() if shown.returncode == 0 else []:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ids.add(str(rec.get("id", "")).split("v")[0])
            titles.add(normalize_title(rec.get("title")))
    titles.discard("")
    return ids, titles


def summarise(records, today, site, topics):
    from summaries.interests import topics_for
    new = [r for r in records if in_window(r["listed"], today)]
    reliable = [r for r in new if not r["flags"]]
    delays = [delay_days(r["published"], r["listed"]) for r in reliable]
    ids, titles = site
    matched = [r for r in new if topics_for({"title": r["title"], "summary": r["abstract"]}, topics)]
    return {
        "new": len(new), "per_day": len(new) / WINDOW, "matched": len(matched), "matched_titles": [r["title"] for r in matched],
        "median": quantile(delays, 0.5), "p90": quantile(delays, 0.9), "reliable": len(reliable),
        "flags": {f: sum(f in r["flags"] for r in new) for f in ("missing", "partial", "jan1", "future", "after_listing")},
        "abstract": sum(bool(r["abstract"]) for r in new), "oa": sum(r["oa"] for r in new), "arxiv": sum(bool(r["arxiv"]) for r in new),
        "on_site": sum((r["arxiv"] in ids) or (normalize_title(r["title"]) in titles) for r in new),
        "published_in_window": sum(in_window(r["published"], today) for r in records),
    }


# ---------------------------------------------------------------- report

def fmt(x, digits=0):
    return "-" if x is None else f"{x:.{digits}f}"


def print_table(rows):
    print("| Source | Venue | New in 14 d | Per day | Topic matches | Delay median | Delay p90 | Dated reliably | Abstract | OA link | arXiv | Already on site | Verdict |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for source, venue, s in rows:
        n = s["new"]
        small = " (n<20)" if n < SMALL_SAMPLE else ""
        print(f"| {source} | {venue}{small} | {n} | {s['per_day']:.1f} | {s['matched']} | {fmt(s['median'])} | {fmt(s['p90'])} | "
              f"{s['reliable']} | {share(s['abstract'], n)} | {share(s['oa'], n)} | {share(s['arxiv'], n)} | {s['on_site']} | "
              f"{verdict(s['median'], n)} |")


def run():
    from summaries.interests import load_topics
    today = dt.date.today()
    raw = ROOT / ".cache" / "freshness" / str(today)
    raw.mkdir(parents=True, exist_ok=True)
    http, topics, site = Http(raw), load_topics(), site_index(today)
    print(f"site index: {len(site[0])} arXiv ids, {len(site[1])} titles over {SITE_DAYS} days", file=sys.stderr)
    rows, notes, cost, records_out = [], [], {}, {}

    quota_hit = False
    for name, group, source_id, issns, venue_ids in WATCH:
        if source_id and not quota_hit:
            try:
                works = openalex_venue(http, source_id, today)
                recs = [openalex_record(w, today) for w in works]
                records_out[f"OpenAlex/{name}"] = recs
                rows.append(("OpenAlex", name, summarise(recs, today, site, topics)))
                cost[name] = {w: sum(1 for r in recs if r["published"] and (today - r["published"]).days <= w) for w in (30, 90, 365)}
            except QuotaExhausted as error:
                quota_hit = True
                notes.append(f"OpenAlex stopped at {name}: {error}")
            print(f"OpenAlex {name}: done ({http.counts['openalex']} requests)", file=sys.stderr)
        if issns:
            items = crossref_pages(http, ",".join([f"issn:{i}" for i in issns] + [f"from-created-date:{first_day(today)}"]),
                                   f"{name.replace(' ', '_')}")
            recs = [crossref_record(i, today) for i in items]
            records_out[f"Crossref/{name}"] = recs
            rows.append(("Crossref", name, summarise(recs, today, site, topics)))
            print(f"Crossref {name}: {len(recs)}", file=sys.stderr)
        for venue_id in venue_ids:
            try:
                recs = [openreview_record(n, today) for n in openreview_venue(http, venue_id, today)]
                records_out[f"OpenReview/{venue_id}"] = recs
                rows.append(("OpenReview", venue_id, summarise(recs, today, site, topics)))
            except urllib.error.HTTPError as error:
                notes.append(f"OpenReview {venue_id}: HTTP {error.code} ({'challenge required' if error.code == 403 else 'error'})")
        time.sleep(0.2)

    eccv = crossref_pages(http, f"from-created-date:{first_day(today)},type:book-chapter,prefix:10.1007", "ECCV",
                          extra={"query.container-title": f"Computer Vision {ECCV_CONTAINER}", "sort": "score"},
                          keep=lambda i: any(ECCV_CONTAINER in c for c in i.get("container-title") or []))
    recs = [crossref_record(i, today) for i in eccv]
    records_out["Crossref/ECCV"] = recs
    rows.append(("Crossref", "ECCV", summarise(recs, today, site, topics)))

    extras = {}
    try:
        for name in [w[0] for w in WATCH if w[3]]:
            oa_new = [r for r in records_out.get(f"OpenAlex/{name}", []) if in_window(r["listed"], today)]
            cr_new = [r for r in records_out.get(f"Crossref/{name}", []) if in_window(r["listed"], today)]
            created = crossref_created_by_doi(http, [r["doi"] for r in oa_new])
            lags = lag_behind_doi(oa_new, created)
            oa_dois = {r["doi"] for r in records_out.get(f"OpenAlex/{name}", [])}
            extras[name] = {"oa_new": len(oa_new), "joined": len(lags), "lag_median": quantile(lags, 0.5), "lag_p90": quantile(lags, 0.9),
                            "crossref_new": len(cr_new), "crossref_in_openalex": sum(r["doi"] in oa_dois for r in cr_new)}
        history = conference_history(http, today) if not quota_hit else {}
    except QuotaExhausted as error:
        notes.append(f"OpenAlex stopped in the extra checks: {error}")
        history = {}
    eccv_all = eccv_listing(http, today)

    (raw / "records.json").write_text(json.dumps(records_out, default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    (raw / "summary.json").write_text(json.dumps({"rows": rows, "cost": cost, "notes": notes, "requests": http.counts,
                                                  "openalex_remaining": http.openalex_remaining,
                                                  "doi_lag": extras, "history": history, "eccv": eccv_all}, default=str, indent=1), encoding="utf-8")
    print(f"## Window {first_day(today)} to {today}\n")
    print_table(rows)
    print("\n## OpenAlex works per venue with publication date in the trailing N days (what a daily re-scan must page through)\n")
    print("| Venue | 30 d | 90 d | 365 d |\n|---|---|---|---|")
    for venue, c in cost.items():
        print(f"| {venue} | {c[30]} | {c[90]} | {c[365]} |")
    print("\n## Journals: OpenAlex listing lag behind the Crossref DOI registration (works OpenAlex listed in the window)\n")
    print("| Venue | OpenAlex new | Joined by DOI | Lag median | Lag p90 | Crossref new | of which in OpenAlex today |\n|---|---|---|---|---|---|---|")
    for venue, e in extras.items():
        print(f"| {venue} | {e['oa_new']} | {e['joined']} | {fmt(e['lag_median'])} | {fmt(e['lag_p90'])} | {e['crossref_new']} | {e['crossref_in_openalex']} |")
    print("\n## Conferences: last proceedings in OpenAlex (200-work sample)\n")
    print("| Proceedings | Sample | Dated reliably | Delay median | Delay p90 | Publication dates | Listed from | Listed to |\n|---|---|---|---|---|---|---|---|")
    for name, h in history.items():
        print(f"| {name} | {h['n']} | {h['reliable']} | {fmt(h['median'])} | {fmt(h['p90'])} | {', '.join(h['published'])} | {h['listed_from']} | {h['listed_to']} |")
    print(f"\nECCV 2026 in Crossref since 2026-08-01: {eccv_all}")
    for w in (30, 90, 365):
        print(f"\nRe-scan of {w} days: {sum(pages_needed(c[w]) for c in cost.values())} OpenAlex list requests a day")
    print(f"\nRequests this run: {http.counts}; OpenAlex credits left: {http.openalex_remaining}")
    for note in notes:
        print(f"- {note}")


if __name__ == "__main__":
    run()
