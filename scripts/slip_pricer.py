#!/usr/bin/env python3
"""
slip_pricer.py — paste an OPEN Stake slip, get the real hit chance of every leg
and of the whole ticket. Win probability first, price (EV) second.

  python3 scripts/slip_pricer.py slip.txt [--sims 2000000]
  echo "<slip text>" | python3 scripts/slip_pricer.py -

Legs it prices (NFL, from the local nflverse feed — no paid API calls):
  - spread / moneyline / game total  -> the Judge's blended margin + fitted σ
  - player props (pass/rush/rec yds, receptions, pass TDs, anytime TD, ...)
    -> the player's real 2025-2026 game logs (play-by-play), recency weighted,
       shrunk toward a fitted distribution; per-stat settings, opponent-defense
       factor, TD base rates and logit recalibration all chosen by walk-forward
       log-loss (scripts/backtest_props.py; every stat beats the base rate)
  - same-game blocks -> correlation MEASURED from games where all legs had a
    result (e.g. Allen yards + Allen pass TDs), shrunk toward independence
Anything else (college, other leagues) is listed as UNPRICED — never guessed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm, poisson

sys.path.insert(0, str(Path(__file__).parent))
import cfb_model as cm  # noqa: E402
import nflverse_feed as nf  # noqa: E402
import winner_judge as wj  # noqa: E402

HALFLIFE = 8          # games back for half weight
PRIOR_K = 4.0         # pseudo-games given to the fitted distribution
CORR_K = 8.0          # shared games before a measured correlation counts fully
MIN_GAMES = 2         # below this a prop is UNPRICED
FULL_GAMES = 8        # below this the read is pulled toward 50% (SMALL SAMPLE)
SMALL_K = 4.0         # pseudo-games of 50/50 added to a small sample
MIN_CV = 0.3          # yardage never less spread than 30% of its mean (NFL game-to-game)

ODDS = re.compile(r"^\d+[.,]\d+$")
TICKET = re.compile(r"^(\d+)\s+(?:Multi tramo|Leg Multi|Multi Leg)$", re.I)
SGP = re.compile(r"^(?:Multi apuesta del mismo partido|Same Game Multi)\s*\((\d+)", re.I)
SPREAD_SEL = re.compile(r"^(.+?)\s*\(([+-]?\d+(?:\.\d+)?)\)$")
OU = r"(Sobre|Over|Más de|Mas de|Bajo|Under|Menos de)"
TOTAL_SEL = re.compile(rf"^{OU}\s+(\d+(?:\.\d+)?)$", re.I)
PROP_SEL = re.compile(rf"^{OU}\s+(\d+(?:\.\d+)?)\s+(.+)$", re.I)
MARKET_SPREAD = ("hándicap", "handicap", "spread")
MARKET_ML = ("ganador", "winner", "moneyline")
MARKET_TOTAL = ("total",)

# stat words on the slip -> (pbp id column, pbp value column | None = count rows)
PROP_STATS = [
    (("yardas por pases", "passing yards"), "passer_player_id", "passing_yards"),
    (("yardas por acarreo", "rushing yards"), "rusher_player_id", "rushing_yards"),
    (("yardas de recepción", "yardas de recepcion", "receiving yards"), "receiver_player_id", "receiving_yards"),
    (("pases de touchdown", "passing touchdown"), "passer_player_id", "pass_touchdown"),
    (("pases completados", "completions"), "passer_player_id", "complete_pass"),
    (("intentos de pase", "pass attempts"), "passer_player_id", "pass_attempt"),
    (("recepciones", "receptions"), "receiver_player_id", "complete_pass"),
    (("touchdown en cualquier momento", "anytime touchdown", "anytime td"), "td_player_id", None),
]
COUNT_STATS = {"pass_touchdown", "complete_pass", "pass_attempt", None}
TD_STATS = {"pass_touchdown", None}   # scoring events: clumpy, priced by shrunk frequency
# Per-stat settings picked by walk-forward log-loss on 2025-26 play-by-play
# (scripts/backtest_props.py → data/benchmarks/props_backtest.json).
# opp_k: pseudo-games that shrink the opponent-defense factor (None = no opponent adjustment;
# it only helped passing yards / catches). freq_k: pseudo-games of league base rate for TD props.
# platt: (a, b) logit recalibration of P(over), fit 2025 → tested on 2026 out of sample; kept
# only where it improved 2026 log-loss (rush, rec yds, catches, anytime TD — not pass yds/TDs).
PROP_PARAMS = {
    "passing_yards": {"halflife": 12, "prior_k": 24, "min_cv": 0.45, "opp_k": 16.0},
    "rushing_yards": {"halflife": 8, "prior_k": 8, "min_cv": 0.6, "opp_k": None, "platt": (-0.212, 1.102)},
    "receiving_yards": {"halflife": 8, "prior_k": 12, "min_cv": 0.8, "opp_k": 16.0, "platt": (-0.297, 0.959)},
    "complete_pass": {"halflife": 8, "prior_k": 8, "min_cv": 0.3, "opp_k": 16.0, "platt": (-0.227, 0.774)},
    "pass_attempt": {"halflife": 8, "prior_k": 8, "min_cv": 0.3, "opp_k": 16.0},
    "pass_touchdown": {"halflife": 16, "freq_k": 16.0},
    None: {"halflife": 8, "freq_k": 16.0, "platt": (0.072, 1.546)},
}
# Players who actually carry the stat (league base rates are measured over these).
VOLUME_FLOOR = {"passing_yards": 150, "rushing_yards": 30, "receiving_yards": 25, "complete_pass": 2.5,
                "pass_attempt": 20, "pass_touchdown": 0.8, None: 0.2}
ROLES = ("passer_player_id", "rusher_player_id", "receiver_player_id")


@dataclass
class Leg:
    kind: str                      # spread | ml | total | prop
    label: str
    team: Optional[str] = None
    line: Optional[float] = None
    over: bool = True
    player: Optional[str] = None
    stat: Optional[str] = None
    decimal: Optional[float] = None
    matchup: Optional[tuple] = None


@dataclass
class Block:                        # one outer leg of a ticket: a single leg or a same-game block
    decimal: Optional[float]
    legs: list = field(default_factory=list)
    sgp: bool = False
    matchup: Optional[tuple] = None


@dataclass
class Ticket:
    header: str
    decimal: Optional[float]
    blocks: list = field(default_factory=list)
    stake: Optional[float] = None
    payout: Optional[float] = None
    closed: bool = False


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _is_market(line: str, words: tuple) -> bool:
    low = line.lower()
    return any(low.startswith(w) for w in words)


def _leg_from(sel: str, market: str) -> Optional[Leg]:
    if _is_market(market, MARKET_SPREAD) and (m := SPREAD_SEL.match(sel)):
        return Leg("spread", f"{sel} spread", team=m.group(1).strip(), line=_num(m.group(2)))
    if _is_market(market, MARKET_ML):
        return Leg("ml", f"{sel} to win", team=sel.strip())
    if _is_market(market, MARKET_TOTAL) and (m := TOTAL_SEL.match(sel)):
        over = m.group(1).lower() in ("sobre", "over", "más de", "mas de")
        return Leg("total", f"{'Over' if over else 'Under'} {m.group(2)} total", line=_num(m.group(2)), over=over)
    return None


def parse(text: str) -> list[Ticket]:
    """Stake slip text (Spanish or English) -> tickets -> outer blocks -> legs."""
    L = [x.strip() for x in text.splitlines() if x.strip()]
    tickets: list[Ticket] = []
    cur: Optional[Ticket] = None
    grp: Optional[Block] = None
    nxt = lambda i: L[i + 1] if i + 1 < len(L) else ""   # noqa: E731
    for i, line in enumerate(L):
        if m := TICKET.match(line):
            cur = Ticket(line, _num(nxt(i)) if ODDS.match(nxt(i)) else None)
            tickets.append(cur)
            grp = None
        elif m := SGP.match(line):
            dec = _num(nxt(i)) if ODDS.match(nxt(i)) else None
            grp = Block(dec, sgp=True)
            if cur is None or cur.closed:
                cur = Ticket(line, dec)
                tickets.append(cur)
            cur.blocks.append(grp)
        elif cur is None:
            continue
        elif line.lower() in ("apuesta", "stake", "importe") and ODDS.match(nxt(i)):
            cur.stake = _num(nxt(i))
        elif line.lower() in ("pago", "payout", "pago estimado", "est. payout") and ODDS.match(nxt(i)):
            cur.payout, cur.closed, grp = _num(nxt(i)), True, None
        elif " - " in line and not re.search(r"\d", line) and grp is not None:
            home, away = (s.strip() for s in line.split(" - ", 1))
            grp.matchup = (home, away)
        elif (m := PROP_SEL.match(line)) and i + 1 < len(L):
            words = m.group(3).lower()
            spec = next(((idc, val) for keys, idc, val in PROP_STATS if any(k in words for k in keys)), None)
            over = m.group(1).lower() in ("sobre", "over", "más de", "mas de")
            leg = Leg("prop", f"{nxt(i)} {'over' if over else 'under'} {m.group(2)} {m.group(3)}",
                      line=_num(m.group(2)), over=over, player=nxt(i),
                      stat=json.dumps(spec) if spec else None)
            _attach(cur, grp, leg, None)
        elif i > 0 and (leg := _leg_from(L[i - 1], line)):
            dec = _num(nxt(i)) if ODDS.match(nxt(i)) else None
            if dec is not None:
                leg.decimal = dec
                leg.matchup = _matchup_after(L, i + 2)
                grp = None
            _attach(cur, grp, leg, dec)
    return tickets


def _matchup_after(L: list, j: int) -> Optional[tuple]:
    """Single legs list the game AFTER the price: date, time, home, away."""
    known = TEAMS | cm.teams()
    names = [x for x in L[j:j + 6] if x in known]
    return (names[0], names[1]) if len(names) >= 2 else None


def _attach(cur: Ticket, grp: Optional[Block], leg: Leg, dec: Optional[float]) -> None:
    if grp is not None and dec is None:
        leg.matchup = leg.matchup or grp.matchup
        grp.legs.append(leg)
    else:
        cur.blocks.append(Block(dec, [leg], matchup=leg.matchup))


TEAMS = set(nf.TEAM_NAMES.values())


# ── pricing ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=4)
def _slate(season: int, week: int) -> dict:
    sl = nf.week_slate(season, week, overrides=nf.load_overrides(season))
    out = {}
    for g in sl["games"]:
        r = wj.judge_game(g, n_sims=20_000, seed=7)
        tp = r.get("total_projection") or {}
        out[(g["home"], g["away"])] = {
            "mu": r["expected_home_margin"]["blended"],
            "total": tp.get("blended", (g.get("total") or {}).get("points")),
        }
    return out


def _game_for(team: Optional[str], matchup: Optional[tuple], slate: dict):
    if matchup and tuple(matchup) in slate:
        return tuple(matchup), slate[tuple(matchup)]
    if matchup and tuple(reversed(matchup)) in slate:
        return tuple(reversed(matchup)), slate[tuple(reversed(matchup))]
    for k, v in slate.items():
        if team in k:
            return k, v
    return None, None


def price_game_leg(leg: Leg, slate: dict) -> tuple[Optional[float], str]:
    key, g = _game_for(leg.team, leg.matchup, slate)
    if g is None:
        return _cfb_leg(leg)
    if leg.kind == "total":
        if g["total"] is None:
            return None, "no total projection"
        sd = wj.TOTAL_SIGMA["NFL"]
        p_over = 1 - norm.cdf(leg.line, g["total"], sd)
        return float(p_over if leg.over else 1 - p_over), f"proj. total {g['total']:.1f}"
    sgn = 1 if leg.team == key[0] else -1
    pmf = wj.margin_pmf("NFL", g["mu"], wj.SIGMA["NFL"])
    shift = 0.0 if leg.kind == "ml" else leg.line
    p = sum(v for m, v in pmf.items() if sgn * m + shift > 0)
    return float(p), f"exp. margin {sgn * g['mu']:+.1f}"


def _cfb_view(leg: Leg) -> Optional[dict]:
    if not leg.matchup:
        return None
    home, away = leg.matchup
    ln = cm.market_lines().get(f"{away} @ {home}", {})
    return cm.game_view(home, away, market_spread=ln.get("home_spread"), market_total=ln.get("total"),
                        neutral=bool(ln.get("neutral")))


def _cfb_spec(leg: Leg, v: dict):
    if leg.kind == "total":
        return ("total", leg.line, leg.over)
    return ("side", leg.team == v["home"], 0.0 if leg.kind == "ml" else leg.line)


def _cfb_leg(leg: Leg) -> tuple[Optional[float], str]:
    v = _cfb_view(leg)
    if v is None or (leg.kind != "total" and leg.team not in (v["home"], v["away"])):
        return None, "no model for this game (NFL + college FBS only)"
    spec = _cfb_spec(leg, v)
    p = cm.p_total(v["total"], spec[1], spec[2]) if spec[0] == "total" else cm.p_side(v["mu"], spec[2], spec[1])
    side = v["mu"] if leg.kind == "total" or leg.team == v["home"] else -v["mu"]
    note = (f"college {v['source']}: exp. margin {side:+.1f}, total {v['total']:.1f}" if leg.kind != "total"
            else f"college {v['source']}: proj. total {v['total']:.1f}")
    return p, note


@lru_cache(maxsize=1)
def _pbp() -> pd.DataFrame:
    cols = ["game_id", "season", "week", "season_type", "posteam", "defteam", "passer_player_id", "rusher_player_id",
            "receiver_player_id", "td_player_id", "passing_yards", "rushing_yards", "receiving_yards",
            "pass_touchdown", "complete_pass", "pass_attempt"]
    frames = [pd.read_csv(p, usecols=lambda c: c in cols, low_memory=False)
              for p in sorted(nf.DATA.glob("pbp_*.csv.gz"))]
    d = pd.concat(frames, ignore_index=True)
    return d[d.season_type == "REG"]


@lru_cache(maxsize=1)
def _roster_ids() -> dict:
    out = {}
    for p in sorted(nf.DATA.glob("roster_weekly_*.csv")):
        r = pd.read_csv(p, usecols=["full_name", "gsis_id", "team", "week"], low_memory=False)
        for row in r.sort_values("week").itertuples():
            out[str(row.full_name).lower()] = (row.gsis_id, row.team)
    return out


def player_games(pid: str) -> pd.Index:
    """game_ids the player shows up in (any pass/rush/target/TD)."""
    d = _pbp()
    mask = np.zeros(len(d), bool)
    for c in ("passer_player_id", "rusher_player_id", "receiver_player_id", "td_player_id"):
        mask |= (d[c] == pid).to_numpy()
    g = d.loc[mask, ["game_id", "season", "week"]].drop_duplicates("game_id")
    return pd.Index(g.sort_values(["season", "week"]).game_id)


def player_log(pid: str, idc: str, val: Optional[str]) -> pd.Series:
    """Per-game stat in chronological order (0 in games he played but didn't record it)."""
    d = _pbp()
    rows = d[d[idc] == pid]
    s = rows.groupby("game_id").size() if val is None else rows.groupby("game_id")[val].sum()
    return s.reindex(player_games(pid), fill_value=0).astype(float)


def prop_prob(values: np.ndarray, line: float, over: bool, count: bool,
              halflife: float = HALFLIFE, prior_k: float = PRIOR_K, min_cv: float = MIN_CV,
              freq_base: Optional[float] = None, freq_k: float = 16.0) -> float:
    n = len(values)
    w = 0.5 ** (np.arange(n)[::-1] / halflife)
    hit = (values > line) if over else (values < line)
    if freq_base is not None:                  # TD props: player's hit rate shrunk to the league's
        return float((np.sum(w * hit) + freq_k * freq_base) / (np.sum(w) + freq_k))
    mean = float(np.average(values, weights=w))
    if count:
        prior = float(1 - poisson.cdf(np.floor(line), max(mean, 1e-6)))
    else:
        sd = max(float(np.sqrt(np.average((values - mean) ** 2, weights=w))), min_cv * abs(mean), 1.0)
        prior = float(1 - norm.cdf(line, mean, sd))
    prior = prior if over else 1 - prior
    return float((np.sum(w * hit) + prior_k * prior) / (np.sum(w) + prior_k))


@lru_cache(maxsize=16)
def stat_logs(idc: str, val: Optional[str]) -> pd.DataFrame:
    """One row per (player, game) the player took part in (any pass/rush/target), stat 0 if
    none, with team and opponent defense. Players who never record the stat are dropped."""
    d = _pbp()
    played = pd.concat([d[[c, "game_id", "posteam", "defteam", "season", "week"]].dropna(subset=[c])
                        .set_axis(["pid", "game_id", "team", "defteam", "season", "week"], axis=1)
                        for c in ROLES]).drop_duplicates(["pid", "game_id"])
    rows = d[d[idc].notna()]
    agg = rows.groupby([idc, "game_id"]).size() if val is None else rows.groupby([idc, "game_id"])[val].sum()
    agg = agg.rename("v").reset_index().rename(columns={idc: "pid"})
    out = played.merge(agg, on=["pid", "game_id"], how="left").fillna({"v": 0.0})
    return out[out.pid.isin(agg.pid)].sort_values(["pid", "season", "week"]).reset_index(drop=True)


@lru_cache(maxsize=64)
def league_base(idc: str, val: Optional[str], line: float, over: bool) -> float:
    """How often a regular (volume-floor) player clears this line — the TD-prop prior."""
    logs = stat_logs(idc, val)
    regular = logs.groupby("pid").v.transform("mean") >= VOLUME_FLOOR.get(val, 0.0)
    v = logs.loc[regular, "v"]
    return float(((v > line) if over else (v < line)).mean())


def opp_factor(idc: str, val: Optional[str], defteam: Optional[str]) -> tuple[float, int]:
    """Stat allowed per player-game by this defense / league (last season + this one)."""
    if not defteam:
        return 1.0, 0
    logs = stat_logs(idc, val)
    logs = logs[logs.season >= logs.season.max() - 1]
    g = logs[logs.defteam == defteam]
    league = logs.v.mean()
    return (float(g.v.mean() / league) if len(g) and league > 0 else 1.0), int(len(g))


def prop_estimate(values: np.ndarray, line: float, over: bool, idc: str, val: Optional[str],
                  opp: tuple[float, int] = (1.0, 0)) -> float:
    """Production prop probability with the backtested per-stat settings."""
    prm = PROP_PARAMS.get(val, PROP_PARAMS["complete_pass"])
    if val in TD_STATS:
        p_over = prop_prob(values, line, True, True, prm["halflife"],
                           freq_base=league_base(idc, val, line, True), freq_k=prm["freq_k"])
    else:
        f, n = opp
        if prm["opp_k"]:
            values = values * (1 + (f - 1) * n / (n + prm["opp_k"]))
        p_over = prop_prob(values, line, True, val in COUNT_STATS, prm["halflife"], prm["prior_k"], prm["min_cv"])
    if prm.get("platt"):
        a, b = prm["platt"]
        x = np.log(np.clip(p_over, 1e-4, 1 - 1e-4) / np.clip(1 - p_over, 1e-4, 1))
        p_over = float(1 / (1 + np.exp(-(a + b * x))))
    return p_over if over else 1 - p_over


def _opponent(team: Optional[str]) -> Optional[str]:
    """This week's opponent from the nflverse schedule."""
    if not team:
        return None
    g = nf.load_games()
    season = int(g.season.max())
    wk = g[(g.season == season) & (g.week == nf.current_week(season, g))]
    row = wk[(wk.home_team == team) | (wk.away_team == team)]
    if row.empty:
        return None
    r = row.iloc[0]
    return r.away_team if r.home_team == team else r.home_team


def price_prop(leg: Leg) -> tuple[Optional[float], str, Optional[pd.Series]]:
    if not leg.stat:
        return None, "stat not supported yet", None
    info = _roster_ids().get((leg.player or "").lower())
    if info is None:
        return None, "player not found in 2026 rosters", None
    idc, val = json.loads(leg.stat)
    log = player_log(info[0], idc, val)
    if len(log) < MIN_GAMES:
        return None, f"only {len(log)} NFL games — too few", None
    opp_team = _opponent(info[1])
    opp = opp_factor(idc, val, opp_team)
    p = prop_estimate(log.to_numpy(), leg.line, leg.over, idc, val, opp)
    small = len(log) < FULL_GAMES
    if small:                                   # thin history: don't trust it like a full one
        p = 0.5 + (p - 0.5) * len(log) / (len(log) + SMALL_K)
    hit = (log > leg.line) if leg.over else (log < leg.line)
    last = ", ".join(str(int(x)) for x in log.tail(5))
    prm = PROP_PARAMS.get(val, PROP_PARAMS["complete_pass"])
    vs = (f"; vs {opp_team} D ×{opp[0]:.2f}" if opp_team and prm.get("opp_k") else "")
    return p, (f"{'SMALL SAMPLE — ' if small else ''}{len(log)} gms, avg {log.mean():.1f}, "
               f"hit {hit.mean():.0%}; last 5: {last}{vs}"), hit


def _game_hits(leg: Leg) -> Optional[pd.Series]:
    """Historical indicator for a game leg (by game_id) — used only to MEASURE correlation."""
    team = next((k for k, v in nf.TEAM_NAMES.items() if v == leg.team), None)
    if team is None or leg.kind == "total":
        return None
    g = nf.load_games().dropna(subset=["result"])
    g = g[(g.home_team == team) | (g.away_team == team)]
    margin = np.where(g.home_team == team, g.result, -g.result)
    shift = 0.0 if leg.kind == "ml" else leg.line
    return pd.Series(margin + shift > 0, index=g.game_id)


# League-wide lift of "player over his median line" when HIS team wins, 2025-26
# play-by-play (game script: winning teams run the ball, score more). Used as the
# prior a same-game block shrinks toward when the pair has few shared games.
LEAGUE_WIN_CORR = {"passing_yards": 1.088, "rushing_yards": 1.247, "receiving_yards": 1.028,
                   "complete_pass": 0.947, "pass_touchdown": 1.174, None: 1.154}


def win_corr_prior(block_legs: list) -> float:
    """Product of league lifts for each prop whose player's team is a moneyline/spread
    favourite leg in the same block (player + 'his team wins')."""
    teams = {next((k for k, v in nf.TEAM_NAMES.items() if v == leg.team), None)
             for leg in block_legs if leg.kind in ("ml", "spread") and (leg.line or 0) <= 0}
    f = 1.0
    for leg in block_legs:
        if leg.kind != "prop" or not leg.stat:
            continue
        info = _roster_ids().get((leg.player or "").lower())
        if info and info[1] in teams:
            val = json.loads(leg.stat)[1]
            f *= LEAGUE_WIN_CORR.get(val, 1.0) if leg.over else 1.0
    return f


def sgp_factor(hits: list, prior: float = 1.0) -> tuple[float, int]:
    """Measured joint / product of marginals over games where every leg has a result,
    shrunk toward `prior` (league-wide lift) by the number of shared games."""
    hits = [h for h in hits if h is not None]
    if len(hits) < 2:
        return prior, 0
    idx = hits[0].index
    for h in hits[1:]:
        idx = idx.intersection(h.index)
    n = len(idx)
    if n == 0:
        return prior, 0
    M = np.column_stack([hits_i.reindex(idx).to_numpy(bool) for hits_i in hits])
    prod = float(np.prod(M.mean(0)))
    joint = float(M.all(1).mean())
    raw = joint / prod if prod > 0 else 1.0
    f = prior + (raw - prior) * n / (n + CORR_K)
    return float(np.clip(f, 0.5, 2.0)), n


def price_ticket(t: Ticket, slate: dict, n_sims: int = 2_000_000, seed: int = 11) -> dict:
    blocks, probs, unpriced = [], [], []
    for b in t.blocks:
        legs, hits, ps = [], [], []
        for leg in b.legs:
            if leg.kind == "prop":
                p, note, h = price_prop(leg)
            else:
                p, note = price_game_leg(leg, slate)
                h = _game_hits(leg)
            legs.append({"label": leg.label, "prob": p, "note": note, "decimal": leg.decimal})
            ps.append(p)
            hits.append(h)
            if p is None:
                unpriced.append(leg.label)
        if any(p is None for p in ps) or not ps:
            bp, corr = None, (1.0, 0)
        else:
            corr = sgp_factor(hits, win_corr_prior(b.legs)) if b.sgp else (1.0, 0)
            bp = min(float(np.prod(ps)) * corr[0], min(ps))
            cfb = _cfb_view(b.legs[0]) if b.sgp and all("college" in x["note"] for x in legs) else None
            if cfb is not None:          # one college game: margin + total simulated jointly
                bp = cm.joint_prob(cfb, [_cfb_spec(leg, cfb) for leg in b.legs], n_sims)
                corr = (bp / float(np.prod(ps)), cm.BACKTEST_GAMES)
        probs.append(bp)
        blocks.append({"sgp": b.sgp, "decimal": b.decimal, "prob": bp, "legs": legs,
                       "corr_factor": round(corr[0], 3), "corr_games": corr[1],
                       "need": 1 / b.decimal if b.decimal else None,
                       "ev_pct": (bp * b.decimal - 1) * 100 if bp is not None and b.decimal else None})
    out = {"header": t.header, "decimal": t.decimal, "stake": t.stake, "payout": t.payout,
           "blocks": blocks, "unpriced": unpriced}
    if (any(p is None for p in probs) and any(p is not None for p in probs)
            and all(b["decimal"] for b in blocks)):
        # unpriced blocks taken at their own break-even price — labelled, never mixed in silently
        fill = [p if p is not None else 1 / b["decimal"] for p, b in zip(probs, blocks)]
        dec = t.decimal or float(np.prod([b["decimal"] for b in blocks]))
        out["prob_all_if_unpriced_fair"] = float(np.prod(fill))
        out["ev_pct_if_unpriced_fair"] = (float(np.prod(fill)) * dec - 1) * 100
    if probs and all(p is not None for p in probs):
        rng = np.random.default_rng(seed)
        hits = (rng.random((n_sims, len(probs))) < np.array(probs)).sum(1)
        p_all = float(np.prod(probs))
        dec = t.decimal or float(np.prod([b["decimal"] for b in blocks if b["decimal"]]))
        n = len(probs)
        weakest = min(range(n), key=lambda i: probs[i])
        out.update({"prob_all": p_all, "sim_all": float(np.mean(hits == n)), "need": 1 / dec,
                    "ev_pct": (p_all * dec - 1) * 100, "sims": n_sims,
                    "hits_dist": {k: float(np.mean(hits == k)) for k in range(n, -1, -1)},
                    "weakest": (" + ".join(x["label"] for x in blocks[weakest]["legs"]) if blocks[weakest]["sgp"]
                                else blocks[weakest]["legs"][0]["label"])})
    return out


def price_text(text: str, n_sims: int = 2_000_000, season: Optional[int] = None) -> dict:
    tickets = parse(text)
    season = season or int(nf.load_games().season.max())
    week = nf.current_week(season)
    slate = _slate(season, week)
    return {"season": season, "week": week, "freshness": nf.freshness(),
            "tickets": [price_ticket(t, slate, n_sims) for t in tickets]}


def _pct(x):
    if x is None:
        return "—"
    return f"{x * 100:.1f}%" if x >= 0.01 or x == 0 else f"{x * 100:.3f}%"


def to_markdown(res: dict) -> str:
    L = [f"# Slip check — NFL {res['season']} week {res['week']} + college FBS", ""]
    for t in res["tickets"]:
        L.append(f"## {t['header']} @ {t['decimal']} (stake {t['stake']}, pays {t['payout']})")
        for b in t["blocks"]:
            head = f"same-game @{b['decimal']}" if b["sgp"] else f"@{b['decimal']}"
            ev = f", EV {b['ev_pct']:+.1f}%" if b["ev_pct"] is not None else ""
            corr = f", corr ×{b['corr_factor']} from {b['corr_games']} games" if b["sgp"] and b["corr_games"] else ""
            L.append(f"- **{head}: {_pct(b['prob'])}** (needs {_pct(b['need'])}{ev}{corr})")
            for leg in b["legs"]:
                L.append(f"  - {leg['label']}: {_pct(leg['prob'])} — {leg['note']}")
        if "prob_all" in t:
            L.append(f"\n**All hit: {_pct(t['prob_all'])}** (needs {_pct(t['need'])}) · EV {t['ev_pct']:+.1f}% · "
                     f"weakest: {t['weakest']}")
            L.append("Hits: " + " · ".join(f"{k}: {_pct(v)}" for k, v in t["hits_dist"].items()))
        if "prob_all_if_unpriced_fair" in t:
            L.append(f"\nIf the unpriced legs are exactly fair at the book's price: all hit "
                     f"{_pct(t['prob_all_if_unpriced_fair'])} · EV {t['ev_pct_if_unpriced_fair']:+.1f}%")
        if t["unpriced"]:
            L.append(f"\nUNPRICED (no model, not guessed): {', '.join(t['unpriced'])}")
        L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slip", help="slip text file, or - for stdin")
    ap.add_argument("--sims", type=int, default=2_000_000)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = sys.stdin.read() if a.slip == "-" else Path(a.slip).read_text()
    res = price_text(text, a.sims)
    print(json.dumps(res, indent=2, default=float) if a.json else to_markdown(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
