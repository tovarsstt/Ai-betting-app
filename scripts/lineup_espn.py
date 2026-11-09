"""ESPN-based lineup availability: fallback for nfl_availability when the nflverse depth files are missing.
Counts, per team, how many depth-chart STARTERS (ESPN depth chart, first name per slot) are Out/Doubtful/IR (1.0) or Questionable (0.4).
Only the groups whose sim terms measured sensible on 2026-11-08 are returned: ol, dl, cb, rb, te (wr/lb/s came out wrong-signed = noise).
Effects inside the sim are small by design (calibrated): 1 OL ~ -0.35 pts, 2 OL ~ -1.0 margin, 1 CB ~ -1.2 margin, 1 DL ~ -0.45 margin, TE ~ -1.3, RB ~ -0.35."""
import json, re, unicodedata, urllib.request
GROUPS = {"ol": ["lt", "lg", "c", "rg", "rt"], "dl": ["lde", "ldt", "rdt", "rde", "nt", "de", "dt"], "cb": ["lcb", "rcb", "nb"], "te": ["te"], "rb": ["rb"]}
Q_WEIGHT = 0.4
_SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
_ABBR = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"}
_cache = {}


def _g(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u), timeout=25))


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)).strip()


def team_ids():
    if "ids" not in _cache:
        d = _g("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")
        _cache["ids"] = {_ABBR.get(t["team"]["abbreviation"], t["team"]["abbreviation"]): t["team"]["id"] for t in d["sports"][0]["leagues"][0]["teams"]}
    return _cache["ids"]


def _roster_names(tid):
    r = _g(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}/roster")
    return {a["id"]: a["fullName"] for grp in r["athletes"] for a in grp["items"]}


def _starters(tid):
    d = _g(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/teams/{tid}/depthcharts")
    slots = {}
    for it in d.get("items", []):
        if it.get("name") == "Special Teams":
            continue
        for pos, v in it.get("positions", {}).items():
            if pos not in slots:
                ath = sorted(v.get("athletes", []), key=lambda a: a.get("rank", 9))
                slots[pos] = [re.search(r"/athletes/(\d+)", a["athlete"]["$ref"]).group(1) for a in ath if a.get("athlete")]
    return {grp: [slots[p][0] for p in ps if slots.get(p)] for grp, ps in GROUPS.items()}


def team_counts(team, out_names, q_names=()):
    tid = team_ids()[team]; st = _starters(tid); names = _roster_names(tid)
    out = {_norm(n) for n in out_names}; q = {_norm(n) for n in q_names} - out
    c, lost = {}, []
    for grp, ids in st.items():
        n = 0.0
        for i in ids:
            nm = _norm(names.get(i, ""))
            if nm in out: n += 1.0; lost.append(names.get(i))
            elif nm in q: n += Q_WEIGHT; lost.append((names.get(i), "Q"))
        c[grp + "_lost"] = n
    return c, lost


def avail_from_espn(home, away, injuries, extra_out=None):
    """injuries: [{'team','player','pos','status'}]; extra_out: {'ARI': ['Roy Lopez']} for in-game injuries. Returns ({'home':{...},'away':{...}}, detail)."""
    res, detail = {}, {}
    for side, tm in (("home", home), ("away", away)):
        out = [i["player"] for i in injuries if i.get("team") == tm and str(i.get("status", "")).lower() in ("out", "doubtful", "injured reserve", "ir")] + list((extra_out or {}).get(tm, []))
        q = [i["player"] for i in injuries if i.get("team") == tm and str(i.get("status", "")).lower() == "questionable"]
        res[side], detail[tm] = team_counts(tm, out, q)
    return res, detail
