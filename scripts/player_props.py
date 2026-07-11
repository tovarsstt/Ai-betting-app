#!/usr/bin/env python3
"""
player_props.py — player-stat prop simulator (the "will LeBron get 25?" engine).

Why: two losing days exposed the gap — the app prices TEAM markets only, but
the user's slips carry player props (points/rebounds/assists, shots/shots on
target, tackles/sacks/yards). This closes it: REAL per-game logs -> recency-
weighted distribution fit -> Monte Carlo -> P(over line), fair odds, Stake
min-odds floor, and the same BET/LEAN/NO_BET gates the day card uses.

Data (all free, no quota keys, fetched ON DEMAND only — never in tests):
  NBA / WNBA / NFL : ESPN public gamelog API (per-game stat lines)
  Soccer           : Sofascore per-match player statistics (sofascore.py)

Model: count stats (rebounds, shots, tackles, ...) fit a Poisson, upgraded to
negative binomial when the game log is overdispersed (var > mean — real
players are). Volume stats (points, yards) fit a truncated normal. Recency
weighting = exponential decay, halflife 5 games.

Context variables (NBA/WNBA — ESPN logs carry minutes + box score):
  MINUTES   role change detection: projected mean = per-minute rate x recent
            minutes, so a player moved into/out of the rotation isn't priced
            off his old role.
  USAGE     possessions-used proxy (FGA + 0.44*FTA + TOV) recent vs season —
            reported so a usage spike/crater is visible, never hidden.
  VACUUM    teammates ruled OUT: the log is FILTERED to real games those
            teammates missed and the sim runs on that conditional sample —
            actual observed behavior, not an invented multiplier. Only when
            too few such games exist does it fall back to a flagged, dampened
            usage-redistribution estimate (and says so in the report).

Never invents a number: no game log -> NO_DATA, thin log -> LOW_DATA and no
bet signal, unknown teammate -> named in the report, not silently ignored.

CLI (live network — real usage only, never debug):
  python3 scripts/player_props.py --sport nba --player "Luka Doncic" \
      --stat points --line 32.5 --odds 1.87 --out "Kyrie Irving"
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from math import ceil
from typing import Optional

import numpy as np

import fetch_wc_player_stats as wc_fetch
import opponent_adjust as opp_adj
import sofascore as sofa
from bank_builder import VERDICT_BET_EV, _verdict

# ── Stat catalog ─────────────────────────────────────────────────────────────
# kind: "count" -> Poisson / negative binomial;  "volume" -> truncated normal.
# names: candidate keys in ESPN's gamelog `names` array, first hit wins.
# ESPN serves shooting as combined "made-attempted" columns ("8-14") — the
# made number is the leading one, which _stat_value already takes.
ESPN_STATS = {
    "nba": {
        "points":   {"kind": "volume", "names": ["points"]},
        "rebounds": {"kind": "count",  "names": ["totalRebounds", "rebounds"]},
        "assists":  {"kind": "count",  "names": ["assists"]},
        "threes":   {"kind": "count",  "names": [
            "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
            "threePointFieldGoalsMade"]},
        "steals":   {"kind": "count",  "names": ["steals"]},
        "blocks":   {"kind": "count",  "names": ["blocks"]},
    },
    "nfl": {
        "passing_yards":   {"kind": "volume", "names": ["passingYards"]},
        "rushing_yards":   {"kind": "volume", "names": ["rushingYards"]},
        "receiving_yards": {"kind": "volume", "names": ["receivingYards"]},
        "receptions":      {"kind": "count",  "names": ["receptions"]},
        "tackles":         {"kind": "count",  "names": ["totalTackles"]},
        "sacks":           {"kind": "count",  "names": ["sacks", "totalSacks"]},
        "passing_tds":     {"kind": "count",  "names": ["passingTouchdowns"]},
        "rushing_attempts": {"kind": "count", "names": ["rushingAttempts"]},
    },
    # Soccer merges THREE sources (WC short — every real game counts):
    #   1. WC 2026 cache (fetch_wc_player_stats.py — tournament games)
    #   2. ESPN club gamelog soccer/all (recent club form, `names` below)
    #   3. Sofascore (bonus when reachable; sole source for tackles/passes)
    "soccer": {
        "shots":           {"kind": "count",  "names": ["totalShots"]},
        "shots_on_target": {"kind": "count",  "names": ["shotsOnTarget"]},
        "goals":           {"kind": "count",  "names": ["totalGoals"]},
        "assists":         {"kind": "count",  "names": ["goalAssists"]},
        "fouls":           {"kind": "count",  "names": ["foulsCommitted"]},
        "tackles":         {"kind": "count"},   # sofascore only
        "passes":          {"kind": "volume"},  # sofascore only
    },
}
ESPN_STATS["wnba"] = ESPN_STATS["nba"]  # same box score, same keys

ESPN_LEAGUE = {"nba": "basketball/nba", "wnba": "basketball/wnba",
               "nfl": "football/nfl", "soccer": "soccer/all"}
ESPN_SOCCER_SPORT_UID = "s:600"  # soccer athletes match by sport id, not league

MIN_GAMES_FULL = 8   # below this the read is flagged SMALL_SAMPLE
MIN_GAMES_BET = 5    # below this no verdict at all — data-gated, never estimate
HALFLIFE_GAMES = 5   # recency decay: 5 games back = half weight
N_SIMS = 20_000

# Usage-vacuum fallback (only when the conditional sample is too thin):
# proportional redistribution of the out player's possessions, dampened 50% —
# bench absorbs roughly half in practice, starters don't inherit it all.
TEAM_POSS_PER_GAME = {"nba": 99.0, "wnba": 80.5}
VACUUM_DAMPEN = 0.5
USAGE_NAMES = {"fga": "fieldGoalsMade-fieldGoalsAttempted",
               "fta": "freeThrowsMade-freeThrowsAttempted",
               "tov": "turnovers"}

_UA = {"User-Agent": "Mozilla/5.0"}


def _ceil2(x: float) -> float:
    return ceil(x * 100) / 100


# ── ESPN fetch (network — real usage only) ───────────────────────────────────
def _get_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def espn_search_player(sport: str, name: str) -> Optional[dict]:
    """Resolve a name to an ESPN athlete {id, name} in the sport's league."""
    q = urllib.parse.quote(name)
    data = _get_json(f"https://site.web.api.espn.com/apis/search/v2?query={q}&limit=10")
    return parse_espn_search(data, sport)


def parse_espn_search(data: dict, sport: str) -> Optional[dict]:
    """Pure: first player result whose league/sport matches. Soccer players
    carry their CLUB league slug (usa.1, eng.1, ...) so they match on the
    sport uid (s:600) instead."""
    league = ESPN_LEAGUE[sport].split("/")[1]
    for section in data.get("results", []):
        if section.get("type") != "player":
            continue
        for item in section.get("contents", []):
            uid = item.get("uid", "")           # e.g. "s:40~l:46~a:1966"
            slug = (item.get("defaultLeagueSlug") or item.get("subtitle") or "").lower()
            matched = (uid.startswith(ESPN_SOCCER_SPORT_UID + "~") if sport == "soccer"
                       else league in slug or league in uid.lower())
            if matched:
                athlete_id = uid.split("a:")[-1] if "a:" in uid else item.get("id")
                if athlete_id:
                    return {"id": str(athlete_id), "name": item.get("displayName", "")}
    return None


def espn_gamelog(sport: str, athlete_id: str) -> dict:
    return _get_json(
        "https://site.web.api.espn.com/apis/common/v3/sports/"
        f"{ESPN_LEAGUE[sport]}/athletes/{athlete_id}/gamelog")


def _iter_espn_events(raw: dict):
    for st in raw.get("seasonTypes", []):
        for cat in st.get("categories", []):
            yield from cat.get("events", [])


def parse_espn_gamelog_rows(raw: dict, stat_names: list[str]) -> list[dict]:
    """Pure: per-game rows {event_id, date, value, minutes}, most recent first.

    ESPN's shape: top-level `names` (camelCase stat keys) aligns index-for-
    index with each event's `stats` array under seasonTypes/categories.
    """
    names = raw.get("names") or raw.get("labels") or []
    idx = next((names.index(n) for n in stat_names if n in names), None)
    if idx is None:
        return []
    min_idx = names.index("minutes") if "minutes" in names else None
    game_dates = {eid: (ev or {}).get("gameDate", "")
                  for eid, ev in (raw.get("events") or {}).items()}
    rows = []
    for ev in _iter_espn_events(raw):
        stats = ev.get("stats") or []
        if idx >= len(stats):
            continue
        v = _stat_value(stats[idx])
        if v is None:
            continue
        eid = str(ev.get("eventId"))
        rows.append({
            "event_id": eid,
            "date": game_dates.get(eid, ""),
            "value": v,
            "minutes": _stat_value(stats[min_idx]) if min_idx is not None and min_idx < len(stats) else None,
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def parse_espn_gamelog(raw: dict, stat_names: list[str]) -> list[float]:
    """Pure: per-game values only, most recent first."""
    return [r["value"] for r in parse_espn_gamelog_rows(raw, stat_names)]


def parse_espn_played_events(raw: dict) -> set[str]:
    """Pure: event ids where this athlete logged a stat line (i.e. played)."""
    return {str(ev.get("eventId")) for ev in _iter_espn_events(raw) if ev.get("stats")}


def parse_usage_rows(raw: dict) -> list[float]:
    """Pure: possessions-used proxy per game (FGA + 0.44*FTA + TOV), most
    recent first. Standard usage numerator — measures how much offense runs
    through the player, robust to hot/cold shooting nights."""
    names = raw.get("names") or []
    try:
        fga_i, fta_i, tov_i = (names.index(USAGE_NAMES[k]) for k in ("fga", "fta", "tov"))
    except ValueError:
        return []
    game_dates = {eid: (ev or {}).get("gameDate", "")
                  for eid, ev in (raw.get("events") or {}).items()}
    rows = []
    for ev in _iter_espn_events(raw):
        stats = ev.get("stats") or []
        if max(fga_i, fta_i, tov_i) >= len(stats):
            continue
        fga = _stat_attempted(stats[fga_i])
        fta = _stat_attempted(stats[fta_i])
        tov = _stat_value(stats[tov_i])
        if fga is None or fta is None or tov is None:
            continue
        rows.append((game_dates.get(str(ev.get("eventId")), ""),
                     fga + 0.44 * fta + tov))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [v for _, v in rows]


def _stat_value(s) -> Optional[float]:
    """'27' -> 27.0, '10-20' -> 10.0 (made), '-5' -> -5.0, '-' / '' -> None."""
    if s is None:
        return None
    txt = str(s).strip()
    if not txt or txt == "-":
        return None
    head = txt.split("-")[0] if "-" in txt and not txt.startswith("-") else txt
    try:
        return float(head)
    except ValueError:
        return None


def _stat_attempted(s) -> Optional[float]:
    """'8-14' -> 14.0 (attempted, the trailing number). Plain '7' -> 7.0."""
    if s is None:
        return None
    txt = str(s).strip()
    if not txt or txt == "-":
        return None
    try:
        return float(txt.split("-")[-1])
    except ValueError:
        return None


# ── Soccer: three-source merged game log ─────────────────────────────────────
WC_STATS = {"shots", "shots_on_target", "goals", "assists", "fouls",
            "yellow_cards", "red_cards"}


def wc_lookup(cache: dict, player: str) -> Optional[dict]:
    """Pure: find a player in the WC cache — accent/case-insensitive, accepts
    'Díaz, Luis', 'luis diaz' or plain 'messi' (token-subset match)."""
    want = set(wc_fetch.norm_name(player.replace(",", " ")).split())
    if not want:
        return None
    best, best_size = None, 99
    for key, slot in cache.get("players", {}).items():
        have = set(key.split())
        if want == have:
            return slot
        if want <= have and len(have) < best_size:  # shortest superset wins
            best, best_size = slot, len(have)
    return best


def merge_gamelogs(*source_logs: tuple[str, list[tuple[str, float]]]) -> tuple[list[float], list[str]]:
    """Pure: merge (source, [(date, value)]) logs, dedupe by calendar day
    (first source wins — WC cache is fed first on purpose), newest first."""
    seen_days: set[str] = set()
    merged: list[tuple[str, float]] = []
    used: list[str] = []
    for source, entries in source_logs:
        hit = False
        for date, value in entries:
            day = (date or "")[:10]
            if day and day in seen_days:
                continue
            seen_days.add(day)
            merged.append((date, value))
            hit = True
        if hit:
            used.append(source)
    merged.sort(key=lambda r: r[0], reverse=True)
    return [v for _, v in merged], used


def soccer_combined_gamelog(player: str, stat: str) -> Optional[dict]:
    """WC cache + ESPN club form + Sofascore, merged. Returns
    {player, values, sources} or None when no source knows the name."""
    logs: list[tuple[str, list[tuple[str, float]]]] = []
    resolved = None

    if stat in WC_STATS:  # 1. tournament games — the current-competition read
        try:
            hit = wc_lookup(wc_fetch.ensure_fresh(), player)
        except Exception:
            hit = None
        if hit:
            resolved = hit.get("display") or player
            logs.append(("wc_2026", [(g["date"], float(g.get(stat, 0.0)))
                                     for g in hit.get("games", [])]))

    catalog = ESPN_STATS["soccer"].get(stat) or {}
    if catalog.get("names"):  # 2. club recent form (ESPN, all competitions)
        try:
            athlete = espn_search_player("soccer", player)
        except Exception:
            athlete = None
        if athlete:
            resolved = resolved or athlete["name"]
            try:
                rows = parse_espn_gamelog_rows(
                    espn_gamelog("soccer", athlete["id"]), catalog["names"])
                logs.append(("espn_club", [(r["date"], r["value"]) for r in rows]))
            except Exception:
                pass

    try:  # 3. Sofascore — bonus depth; only source for tackles/passes
        sofa_log = sofa.soccer_player_gamelog(player, stat, pages=2, max_games=20)
    except Exception:
        sofa_log = None
    if sofa_log and sofa_log.get("entries"):
        resolved = resolved or sofa_log["player"]
        logs.append(("sofascore", sofa_log["entries"]))

    if resolved is None:
        return None
    values, used = merge_gamelogs(*logs)
    return {"player": resolved, "values": values, "sources": used}


# ── Distribution fit + simulation (pure) ─────────────────────────────────────
def weighted_moments(values: list[float], halflife: int = HALFLIFE_GAMES) -> tuple[float, float]:
    """Recency-weighted (mean, var). values[0] = most recent game."""
    v = np.asarray(values, dtype=float)
    w = 0.5 ** (np.arange(len(v)) / halflife)
    w /= w.sum()
    mean = float(np.sum(w * v))
    var = float(np.sum(w * (v - mean) ** 2))
    return mean, var


def minutes_projection(rows: list[dict]) -> Optional[dict]:
    """Pure: role-change model. Projected mean = recency-weighted per-minute
    rate x recency-weighted minutes — a player whose minutes just jumped or
    cratered is priced off his CURRENT role, not the season blend.
    None when the log has no usable minutes."""
    played = [r for r in rows if r.get("minutes") and r["minutes"] > 0]
    if len(played) < 3:
        return None
    rates = [r["value"] / r["minutes"] for r in played]
    mins = [float(r["minutes"]) for r in played]
    rate_mean, _ = weighted_moments(rates)
    min_mean, _ = weighted_moments(mins)
    return {
        "projected_mean": rate_mean * min_mean,
        "recent_minutes": round(min_mean, 1),
        "season_minutes": round(float(np.mean(mins)), 1),
        "per_minute_rate": round(rate_mean, 3),
    }


def vacuum_conditional(rows: list[dict], out_played_ids: set[str]) -> list[float]:
    """Pure: the honest vacuum read — this player's stat in REAL games the
    out teammate(s) did not play. Observed behavior, nothing invented."""
    return [r["value"] for r in rows if r["event_id"] not in out_played_ids]


def vacuum_redistribution_scale(out_usage_per_game: float, team_poss: float) -> float:
    """Pure: fallback when too few teammate-out games exist. The out player's
    possessions get redistributed proportionally across the rest — dampened
    (VACUUM_DAMPEN) because in practice the bench absorbs roughly half."""
    share = min(out_usage_per_game / team_poss, 0.4)  # cap: no one uses 40%+
    return 1.0 + VACUUM_DAMPEN * (share / (1.0 - share))


def simulate_stat(mean: float, var: float, kind: str,
                  n: int = N_SIMS, seed: int = 7) -> np.ndarray:
    """Draw n simulated games. count -> Poisson, or negative binomial when the
    log is overdispersed. volume -> normal clipped at 0."""
    rng = np.random.default_rng(seed)
    if kind == "count":
        if mean <= 0:
            return np.zeros(n)
        if var > mean * 1.05:  # overdispersed — NB with matched mean/var
            r = mean * mean / (var - mean)
            p = r / (r + mean)
            return rng.negative_binomial(r, p, size=n).astype(float)
        return rng.poisson(mean, size=n).astype(float)
    sd = max(np.sqrt(var), mean * 0.15, 1e-6)  # floor: tiny samples lie about spread
    return np.clip(rng.normal(mean, sd, size=n), 0, None)


def prop_probabilities(samples: np.ndarray, line: float) -> dict:
    """P(over) / P(under) / P(push). Integer line on a count stat can push."""
    p_over = float(np.mean(samples > line))
    p_push = float(np.mean(samples == line)) if float(line).is_integer() else 0.0
    return {"p_over": round(p_over, 4),
            "p_under": round(1.0 - p_over - p_push, 4),
            "p_push": round(p_push, 4)}


def price_side(prob: float, offered_odds: Optional[float]) -> dict:
    """Fair price, Stake floor, and the day-card verdict gates for one side."""
    out = {
        "prob": round(prob, 4),
        "fair_odds": _ceil2(1.0 / prob) if prob > 0 else None,
        "min_odds": _ceil2((1.0 + VERDICT_BET_EV) / prob) if prob > 0 else None,
    }
    if offered_odds:
        ev = prob * offered_odds - 1.0
        out.update({"offered_odds": offered_odds,
                    "ev_pct": round(ev * 100, 1),
                    "verdict": _verdict(prob, ev)})
    return out


# ── Orchestrator ─────────────────────────────────────────────────────────────
def simulate_player_prop(sport: str, player: str, stat: str, line: float,
                         odds_over: Optional[float] = None,
                         odds_under: Optional[float] = None,
                         teammates_out: Optional[list[str]] = None,
                         opponent: Optional[str] = None) -> dict:
    """Full report for one prop. Network for the game logs, then pure math."""
    sport = sport.lower()
    catalog = ESPN_STATS.get(sport)
    if not catalog or stat not in catalog:
        known = sorted(catalog) if catalog else sorted(ESPN_STATS)
        return {"status": "UNSUPPORTED",
                "note": f"'{stat}' not modelled for '{sport}'. Known: {known}"}

    opp_ctx = opp_adj.opponent_factor(sport, opponent, stat) if opponent else None
    opp_scale = float(opp_ctx["factor"]) if opp_ctx else 1.0

    if sport == "soccer":
        log = soccer_combined_gamelog(player, stat)
        if log is None:
            return {"status": "NOT_FOUND",
                    "note": f"no soccer player matched '{player}' in WC cache / ESPN / Sofascore"}
        context: dict = {}
        if opp_ctx:
            context["opponent_adjust"] = opp_ctx
        report = build_report(sport, log["player"], stat, catalog[stat]["kind"],
                              log["values"], line, odds_over, odds_under,
                              "+".join(log["sources"]) or "none",
                              context=context or None, mean_scale=opp_scale)
        if teammates_out:
            report.setdefault("context", {})["vacuum"] = {
                "out": teammates_out, "mode": "unsupported",
                "note": "soccer vacuum not modelled — no teammate lineup feed"}
        return report

    athlete = espn_search_player(sport, player)
    if athlete is None:
        return {"status": "NOT_FOUND", "note": f"no {sport.upper()} player matched '{player}'"}
    raw = espn_gamelog(sport, athlete["id"])
    rows = parse_espn_gamelog_rows(raw, catalog[stat]["names"])
    values = [r["value"] for r in rows]
    context: dict = {}

    # Minutes / role: current per-minute rate x current minutes.
    projected_mean = None
    mproj = minutes_projection(rows)
    if mproj:
        projected_mean = mproj.pop("projected_mean")
        context["minutes"] = mproj

    # Usage proxy: recent vs season, visible in every report.
    usage = parse_usage_rows(raw)
    if usage:
        u_recent, _ = weighted_moments(usage)
        context["usage_proxy"] = {"recent": round(u_recent, 1),
                                  "season": round(float(np.mean(usage)), 1),
                                  "basis": "FGA + 0.44*FTA + TOV per game"}

    # Vacuum: filter to real teammate-out games; estimate only as fallback.
    mean_scale = 1.0
    if teammates_out:
        vac, values, projected_mean, mean_scale = _espn_vacuum(
            sport, rows, values, projected_mean, teammates_out)
        context["vacuum"] = vac

    if opp_ctx:  # opponent multiplier stacks with the vacuum scale
        context["opponent_adjust"] = opp_ctx
        mean_scale *= opp_scale

    return build_report(sport, athlete["name"], stat, catalog[stat]["kind"],
                        values, line, odds_over, odds_under, "espn",
                        context=context, projected_mean=projected_mean,
                        mean_scale=mean_scale)


def _espn_vacuum(sport: str, rows: list[dict], values: list[float],
                 projected_mean: Optional[float], teammates_out: list[str]):
    """Resolve out teammates, prefer the conditional (real games without them)
    sample, fall back to the flagged redistribution estimate.
    Returns (vacuum_context, values, projected_mean, mean_scale)."""
    out_ids: set[str] = set()
    out_usage = 0.0
    resolved, missing = [], []
    for name in teammates_out:
        mate = espn_search_player(sport, name)
        if mate is None:
            missing.append(name)
            continue
        mate_raw = espn_gamelog(sport, mate["id"])
        out_ids |= parse_espn_played_events(mate_raw)
        mate_usage = parse_usage_rows(mate_raw)
        if mate_usage:
            u, _ = weighted_moments(mate_usage)
            out_usage += u
        resolved.append(mate["name"])

    vac: dict = {"out": resolved}
    if missing:
        vac["unresolved"] = missing  # named, never silently dropped
    if not resolved:
        return vac, values, projected_mean, 1.0

    conditional = vacuum_conditional(rows, out_ids)
    if len(conditional) >= MIN_GAMES_BET:
        vac.update({"mode": "conditional", "games_without": len(conditional),
                    "with_avg": round(float(np.mean(values)), 2) if values else None,
                    "without_avg": round(float(np.mean(conditional)), 2)})
        # Conditional sample IS the model input now — real observed games.
        return vac, conditional, None, 1.0

    team_poss = TEAM_POSS_PER_GAME.get(sport)
    if team_poss and out_usage > 0:
        scale = vacuum_redistribution_scale(out_usage, team_poss)
        vac.update({"mode": "redistribution_estimate", "games_without": len(conditional),
                    "out_usage_per_game": round(out_usage, 1),
                    "mean_scale": round(scale, 3),
                    "note": (f"only {len(conditional)} games without them this season — "
                             "estimate, not observation: dampened usage redistribution")})
        return vac, values, projected_mean, scale

    vac.update({"mode": "flag_only", "games_without": len(conditional),
                "note": "no usage basis to size the bump — flagged, not priced"})
    return vac, values, projected_mean, 1.0


def build_report(sport: str, player: str, stat: str, kind: str,
                 values: list[float], line: float,
                 odds_over: Optional[float], odds_under: Optional[float],
                 source: str, context: Optional[dict] = None,
                 projected_mean: Optional[float] = None,
                 mean_scale: float = 1.0) -> dict:
    """Pure: game log -> full prop report (testable without network).

    projected_mean (minutes model) recenters the distribution; mean_scale
    (vacuum estimate) multiplies it. Variance keeps the sample's dispersion
    SHAPE: counts scale var with mean (steady NB index), volumes keep
    relative spread (sd scales with mean).
    """
    n = len(values)
    if n == 0:
        return {"status": "NO_DATA", "player": player, "stat": stat,
                "note": "no game log found — not estimating (cave law: real data or no pick)"}
    mean, var = weighted_moments(values)
    eff_mean = (projected_mean if projected_mean is not None else mean) * mean_scale
    if mean > 0 and eff_mean != mean:
        ratio = eff_mean / mean
        var = var * ratio if kind == "count" else var * ratio * ratio
    samples = simulate_stat(eff_mean, var, kind)
    probs = prop_probabilities(samples, line)
    report = {
        "status": "OK" if n >= MIN_GAMES_FULL else ("SMALL_SAMPLE" if n >= MIN_GAMES_BET else "LOW_DATA"),
        "sport": sport, "player": player, "stat": stat, "line": line,
        "source": source, "games_used": n,
        "recent_form": values[:10],
        "weighted_avg": round(mean, 2),
        "season_avg": round(float(np.mean(values)), 2),
        "model_mean": round(eff_mean, 2),
        "simulated": {"n_sims": N_SIMS,
                      "p10": round(float(np.percentile(samples, 10)), 1),
                      "median": round(float(np.percentile(samples, 50)), 1),
                      "p90": round(float(np.percentile(samples, 90)), 1)},
        **probs,
    }
    if context:
        report["context"] = context
    if n >= MIN_GAMES_BET:
        report["over"] = price_side(probs["p_over"], odds_over)
        report["under"] = price_side(probs["p_under"], odds_under)
    else:
        report["note"] = (f"only {n} games logged — below the {MIN_GAMES_BET}-game floor, "
                          "no bet signal (data-gated)")
    return report


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Simulate one player prop (LIVE network)")
    ap.add_argument("--sport", required=True, choices=sorted(ESPN_STATS))
    ap.add_argument("--player", required=True)
    ap.add_argument("--stat", required=True)
    ap.add_argument("--line", required=True, type=float)
    ap.add_argument("--odds", type=float, help="offered decimal odds for the OVER")
    ap.add_argument("--odds-under", type=float, help="offered decimal odds for the UNDER")
    ap.add_argument("--out", action="append", default=None, metavar="TEAMMATE",
                    help="teammate ruled OUT (repeatable) — triggers the vacuum model")
    ap.add_argument("--vs", default=None, metavar="OPPONENT",
                    help="opponent team — triggers the defense-allowed adjustment")
    args = ap.parse_args()
    print(json.dumps(simulate_player_prop(
        args.sport, args.player, args.stat, args.line,
        odds_over=args.odds, odds_under=args.odds_under,
        teammates_out=args.out, opponent=args.vs), indent=2))
