"""Current-roster truth for a game, from ESPN (free, default UA): who is on the ACTIVE offense, who is on IR / suspended / practice squad, and the official
game-day inactives once posted. Fixes the case where 6 weeks of play-by-play still credit volume to players who were traded (M. Harrison Jr. ARI->HOU),
cut, or placed on IR since (McLaurin WSH, Pierce PHI, Adams LAR) - none of whom the ESPN *injury report* listed.

    roster(team_id) -> {'offense': {sig: (name,pos)}, 'out': [{'team','player','pos','status'}], 'pos': {sig: pos}}
    inactives(event_id, team_id, pos_by_sig) -> (posted: bool, [names])
"""
import re, json, time, urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e}/competitions/{e}/competitors/{t}/roster"
OUT_GROUPS = ("injuredReserveOrOut", "suspended")
MIN_ACTIVE_POSTED = 40          # before the 90-minute mark ESPN flags every roster row active=False


def _get(url: str, tries: int = 4):
    """ESPN answers a transient 404/5xx now and then: retry before giving up"""
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url), timeout=25))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def sig(name: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", name.strip()) if p and p.lower() not in ("jr", "sr", "ii", "iii", "iv", "v")]
    return (parts[0][0] + re.sub(r"[^a-z]", "", parts[-1].lower())).lower() if parts else ""


def roster(team_id: str, team: str) -> dict:
    groups = {g["position"]: g["items"] for g in _get(f"{SITE}/teams/{team_id}/roster")["athletes"]}
    offense = {}
    pos = {}
    for g in ("offense", "defense", "specialTeam"):
        for a in groups.get(g, []):
            pos[sig(a["displayName"])] = a["position"]["abbreviation"]
            if g == "offense":
                offense[sig(a["displayName"])] = (a["displayName"], a["position"]["abbreviation"])
    out = []
    for g in OUT_GROUPS:
        for a in groups.get(g, []):
            out.append({"team": team, "player": a["displayName"], "pos": a["position"]["abbreviation"], "status": "Injured Reserve" if g == "injuredReserveOrOut" else "Suspension"})
            pos.setdefault(sig(a["displayName"]), a["position"]["abbreviation"])
    return {"offense": offense, "out": out, "pos": pos}


def inactives(event_id: str, team_id: str, pos_by_sig: dict) -> tuple:
    rows = _get(CORE.format(e=event_id, t=team_id)).get("entries", [])
    active = [r for r in rows if r.get("active")]
    if not (MIN_ACTIVE_POSTED <= len(active) <= 53):
        return False, []
    return True, [r.get("displayName") for r in rows if r.get("active") is False and r.get("displayName")]


# ── transactions layer: ESPN's roster endpoint lags the wire by days (Pierce PHI still "offense" 4 days after going on IR) ─────────────────────────────
POS = r"(?:QB|RB|WR|TE|FB|OL|OT|T|G|C|EDGE|DT|DE|NT|LB|ILB|OLB|CB|S|DB|K|P|LS|DL)"
NAME = r"([A-Z][A-Za-z.'’-]*(?:\s+(?:Jr\.|Sr\.|II|III|IV|V|[A-Z][A-Za-z.'’-]*))*)"
OUT_RE = re.compile(r"^(Placed|Released|Waived|Traded)\b")
IN_RE = re.compile(r"^(Signed|Activated|Reinstated)\b")


def full(name: str) -> str:
    """normalised FULL name (suffix dropped): wire moves are matched on the full name so 'J. Williams' never collides with another Williams"""
    return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", name.lower()))


def _names(sentence: str):
    return [m.group(1).strip() for m in re.finditer(rf"\b{POS}\s+{NAME}", sentence)]


def tx_state(team: str, since: str = "2026-09-01", limit: int = 600) -> dict:
    """{full-name: 'out'|'in'} for offensive-position players, from the latest wire move (oldest->newest). Practice-squad moves and 'designated to return' are ignored."""
    tx = [t for t in _get(f"{SITE}/transactions?limit={limit}")["transactions"] if t["team"]["abbreviation"].replace("LAR", "LA").replace("WSH", "WAS") == team and t["date"][:10] >= since]
    state = {}
    for t in sorted(tx, key=lambda x: x["date"]):
        for sent in re.split(r"(?<=\.)\s+", t.get("description", "")):
            if "to return" in sent or "to the practice squad" in sent or ("practice squad" in sent and "active roster" not in sent):
                continue
            kind = "out" if OUT_RE.match(sent) else "in" if IN_RE.match(sent) else None
            if kind is None:
                continue
            if kind == "in" and "active roster" not in sent and not sent.startswith(("Activated", "Reinstated")):
                continue
            if kind == "out" and sent.startswith("Placed") and "injured reserve" not in sent and "reserve" not in sent:
                continue
            for n in _names(sent):
                state[full(n)] = kind
    return state
