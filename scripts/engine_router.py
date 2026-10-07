#!/usr/bin/env python3
"""
engine_router.py — exposes engine v2 / engine_all / the forward ledger to the app (FastAPI router, mounted by edge_api.py).

    GET  /engine/health            what is live: v2 on/off, calibration values, numba, freshness of the stored fits
    GET  /engine/registry          per-sport niche registry (family / validated / already-priced / watch / untested)
    POST /engine/analyze           any sport: price every market from (total, p_home) with the sport's calibrated family
    POST /engine/tennis            level-anchored hierarchical tennis sim (+ validated context: rest, load, altitude)
    POST /engine/ticket            independent-leg ticket maths incl. Stake Shield "N of M" and drawdown tail risk
    GET  /engine/forward-ledger    frozen watch-rules scored on never-analysed games (promotion needs n>=150 and Bonferroni p)

Everything degrades to an explicit error payload — a missing data file never takes the main API down.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
DATA = Path(__file__).parent.parent / "data"
router = APIRouter(prefix="/engine", tags=["engine-v2"])


def _warm() -> None:                         # compile the Numba kernel once, off the request path
    try:
        import tennis_vec as tv
        tv.simulate_nb(0.65, 0.62, 2000, (0.05, 0.05), 1)
    except Exception:
        pass


threading.Thread(target=_warm, daemon=True).start()


def _age_days(p: Path) -> Optional[float]:
    return round((time.time() - p.stat().st_mtime) / 86400, 1) if p.exists() else None


@router.get("/health")
def health() -> dict:
    out: dict = {"status": "OK"}
    try:
        import tennis_games_model as tgm
        import tennis_vec as tv
        out["tennis_v2_enabled"] = bool(getattr(tgm, "V2_ENABLED", False))
        out["numba"] = bool(getattr(tv, "HAVE_NUMBA", False))
    except Exception as e:
        out["tennis_v2_enabled"], out["error"] = False, repr(e)[:160]
    for name in ("engine_v2_calibration.json", "sport_math_calibration.json", "tennis_context_coefficients.json", "nfl_wind_totals_model.json", "forward_ledger.json"):
        out[name] = {"age_days": _age_days(DATA / name)}
    try:
        out["engine_v2_calibration"] = json.loads((DATA / "engine_v2_calibration.json").read_text())
    except Exception:
        out["engine_v2_calibration"] = None
    return out


@router.get("/registry")
def registry() -> dict:
    try:
        import engine_all
        return {"status": "OK", "registry": engine_all.REGISTRY}
    except Exception as e:
        return {"status": "ERROR", "error": repr(e)[:200]}


class AnalyzeReq(BaseModel):
    sport: str
    total: float
    p_home: float
    line: Optional[float] = None
    total_line: Optional[float] = None
    p_draw: Optional[float] = None
    wind_mph: Optional[float] = None              # RECORDED scale
    wind_openmeteo: Optional[float] = None        # raw Open-Meteo, converted
    cover_odds: Optional[List[float]] = None      # [home/side A decimal, other side]
    over_odds: Optional[List[float]] = None
    bankroll: float = 60.0


@router.post("/analyze")
def analyze(req: AnalyzeReq) -> dict:
    try:
        import engine_all
        return {"status": "OK", **engine_all.analyze_game(req.sport, req.total, req.p_home, req.line, req.total_line, req.p_draw, req.wind_mph, req.wind_openmeteo,
                                                         tuple(req.cover_odds) if req.cover_odds else None, tuple(req.over_odds) if req.over_odds else None, req.bankroll)}
    except Exception as e:
        return {"status": "ERROR", "error": repr(e)[:300]}


class TennisReq(BaseModel):
    player_a: str
    player_b: str
    ml_a: float                                    # decimal ML prices (both sides needed to de-vig)
    ml_b: float
    context: Optional[dict] = None                 # rest_days_a/b, games_last7d_a/b, altitude_m, narratives{}
    n: int = 200_000


@router.post("/tennis")
def tennis(req: TennisReq) -> dict:
    try:
        import engine_v2 as E
        S = E.simulate_match(req.player_a, req.player_b, (req.ml_a, req.ml_b), n=req.n, ctx=req.context)
        if S is None:
            return {"status": "NO_DATA", "note": "no serve stats for a player — no data, not estimating"}
        r = S["rows"]
        import numpy as np
        mar, tot = r[:, 5].astype(int) - r[:, 6].astype(int), r[:, 5].astype(int) + r[:, 6].astype(int) + S["off"]
        return {"status": "OK", "engine": "v2", "p_a_wins": float((r[:, 0] == 0).mean()), "p_a_straight_sets": float(((r[:, 1] == 2) & (r[:, 2] == 0)).mean()),
                "p_a_wins_a_set": float(1 - ((r[:, 1] == 0) & (r[:, 2] == 2)).mean()), "expected_total_games": float(np.mean(tot)),
                "games_margin_ladder_a": {f"{L:+g}": float(np.mean(mar + L > 0)) for L in (-5.5, -4.5, -3.5, -2.5, -1.5, 1.5, 2.5, 3.5, 4.5, 5.5)},
                "serve_sd": S["sd"], "serve_samples_matches": S["n_pts"], "context": S.get("context")}
    except Exception as e:
        return {"status": "ERROR", "error": repr(e)[:300]}


class LegModel(BaseModel):
    name: str
    p: float
    odds: float


class ShieldModel(BaseModel):
    need: int
    odds: float


class TicketReq(BaseModel):
    legs: List[LegModel]
    stake: float = 10.0
    shield: Optional[ShieldModel] = None


@router.post("/ticket")
def ticket(req: TicketReq) -> dict:
    try:
        import engine_v2 as E
        t = E.ticket([E.Leg(l.name, l.p, l.odds) for l in req.legs], req.stake, (req.shield.need, req.shield.odds) if req.shield else None)
        return {"status": "OK", **{k: v for k, v in t.items()}}
    except Exception as e:
        return {"status": "ERROR", "error": repr(e)[:300]}


@router.get("/forward-ledger")
def forward_ledger() -> dict:
    try:
        import forward_tests as F
        led = json.loads((DATA / "forward_ledger.json").read_text())
        return {"status": "OK", "frozen_on": led.get("frozen_on"), "n_games": len(led.get("games", {})), "scoreboard": F.scoreboard(led).splitlines(), "rules": led.get("rules")}
    except Exception as e:
        return {"status": "ERROR", "error": repr(e)[:300]}
