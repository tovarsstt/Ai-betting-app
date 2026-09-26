"""
judge_engines.py — plugs the sport engines into the winner-first Judge.

  SOCCER  market lens = devigged 1X2 -> market-calibrated lambdas;
          engine lens = Poisson-regression team ratings (_intl/_club_lambdas);
          SIM = n_sims scorelines drawn from the blended Dixon-Coles matrix
          -> 1X2 / double chance / draw-no-bet / over-under / BTTS.
  TENNIS  market lens = devigged ML; engine lens = points+serve fused model
          (edge_api.predict); SIM = n_sims best-of-N matches set by set
          -> ML / wins-a-set / set-1.
  MLB     margin Judge (winner_judge.judge_game) + pitcher-model lens
          (mlb_game_model: probable starters) on ML and run line.

Same rules as winner_judge: win probability first, price second; every
weighted lens must agree on the side; payout floor MIN_DECIMAL.
No network: engines read local data files only.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

import winner_judge as wj

W_MARKET, W_ENGINE, W_AGENTS = 0.65, 0.20, 0.15


def _row(label: str, price, lenses: dict, sim: float, push: float = 0.0,
         weights: Optional[dict] = None) -> dict:
    w = weights or {"market": W_MARKET, "engine": W_ENGINE, "agents": W_AGENTS}
    use = {k: v for k, v in lenses.items() if v is not None and k in w}
    tot = sum(w[k] for k in use) or 1.0
    p = sum(w[k] * v for k, v in use.items()) / tot
    dec = wj.to_decimal(price) if price is not None else None
    agree = all(v > 0.5 for v in use.values())
    ev = (p * dec - 1.0) if dec else None
    fair = 1.0 / p if p > 0 else None
    return {
        "label": label, "decimal": dec, "win_prob": round(p, 4), "push_prob": round(push, 4),
        "lenses": {**{k: round(v, 4) for k, v in use.items()}, "sim": round(sim, 4)},
        "worst_lens": round(min(list(use.values()) + [sim]), 4),
        "lenses_agree": agree, "grade": wj.grade(p, agree, use),
        "fair_decimal": round(fair, 2) if fair else None,
        "ev_pct": round(ev * 100, 1) if ev is not None else None,
        "price_note": (None if dec is None else "VALUE" if ev >= 0 else
                       f"OVERPRICED — fair {fair:.2f}, book pays {dec:.2f}"),
    }


def _finish(game: str, sport: str, rows: list[dict], flags: list[str], extra: dict,
            min_decimal: float) -> dict:
    eligible = [r for r in rows if r["decimal"] and r["decimal"] >= min_decimal and r["lenses_agree"]]
    eligible.sort(key=lambda r: (-r["win_prob"], -r["worst_lens"], -(r["ev_pct"] or 0)))
    rows.sort(key=lambda r: (-r["win_prob"], -(r["ev_pct"] or 0)))
    if not eligible:
        flags.append(f"NO_PICK: no priced market >= {min_decimal} with every lens agreeing")
    return {"game": game, "sport": sport, "best_winning_pick": eligible[0] if eligible else None,
            "markets": rows, "flags": flags, **extra}


# ── SOCCER ────────────────────────────────────────────────────────────────────
def _soccer_probs(m: np.ndarray, lines: list[float]) -> dict:
    n = m.shape[0]
    i, j = np.indices(m.shape)
    home, draw, away = m[i > j].sum(), m[i == j].sum(), m[i < j].sum()
    out = {"home": home, "draw": draw, "away": away,
           "dc_1x": home + draw, "dc_x2": away + draw, "dc_12": home + away,
           "dnb_home": home / (home + away), "dnb_away": away / (home + away),
           "btts_yes": m[(i > 0) & (j > 0)].sum()}
    out["btts_no"] = 1 - out["btts_yes"]
    tot = i + j
    for ln in lines:
        out[f"over_{ln}"] = m[tot > ln].sum()
        out[f"under_{ln}"] = m[tot < ln].sum()
    _ = n
    return {k: float(v) for k, v in out.items()}


def judge_soccer(home: str, away: str, prices: dict, neutral: bool = False,
                 n_sims: int = wj.N_SIMS, seed: int = 11,
                 min_decimal: float = wj.MIN_DECIMAL, agents: Optional[dict] = None) -> dict:
    """prices: {"home","draw","away"} required (American or decimal); optional
    "dc_1x","dc_x2","dc_12","dnb_home","dnb_away","btts_yes","btts_no",
    "over_2.5","under_2.5" (any line)."""
    import edge_api as ea
    import soccer_markets as sm
    if not ea.ALL_RATINGS:
        ea.load_all()
    flags: list[str] = []
    dv = sm.devig_3way(prices["home"], prices["draw"], prices["away"])
    lh_m, la_m, _ = sm.solve_lambdas_from_1x2(dv["home"], dv["draw"], dv["away"])
    eng = ea._intl_lambdas(home, away, neutral)
    src = "international Poisson-regression fit"
    if eng is None:
        eng, league = ea._club_lambdas(home, away, neutral)
        src = f"club Poisson-regression fit ({league})" if eng else None
    if eng is None:
        flags.append("ENGINE_NO_DATA: teams not in the soccer rating fits — market lens only")
    lines = sorted({float(k.split("_", 1)[1]) for k in prices if k.startswith(("over_", "under_"))} or {2.5})

    mat = lambda lh, la: np.array(sm.score_matrix(lh, la))
    p_mkt = _soccer_probs(mat(lh_m, la_m), lines)
    p_eng = _soccer_probs(mat(*eng), lines) if eng else None
    # blended lambdas -> Dixon-Coles matrix -> sample n_sims scorelines
    if eng:
        wsum = W_MARKET + W_ENGINE
        lh_b = (W_MARKET * lh_m + W_ENGINE * eng[0]) / wsum
        la_b = (W_MARKET * la_m + W_ENGINE * eng[1]) / wsum
    else:
        lh_b, la_b = lh_m, la_m
    mb = mat(lh_b, la_b)
    flat = mb.ravel() / mb.sum()
    rng = np.random.default_rng(seed)
    idx = rng.choice(flat.size, size=n_sims, p=flat)
    hg, ag = np.divmod(idx, mb.shape[1])
    tg = hg + ag
    sim = {"home": np.mean(hg > ag), "draw": np.mean(hg == ag), "away": np.mean(hg < ag),
           "dc_1x": np.mean(hg >= ag), "dc_x2": np.mean(hg <= ag), "dc_12": np.mean(hg != ag),
           "btts_yes": np.mean((hg > 0) & (ag > 0))}
    sim["btts_no"] = 1 - sim["btts_yes"]
    nd = np.count_nonzero(hg != ag)
    sim["dnb_home"] = np.count_nonzero(hg > ag) / nd
    sim["dnb_away"] = np.count_nonzero(hg < ag) / nd
    for ln in lines:
        sim[f"over_{ln}"] = np.mean(tg > ln)
        sim[f"under_{ln}"] = np.mean(tg < ln)

    names = {"home": f"{home} win", "draw": "Draw", "away": f"{away} win",
             "dc_1x": f"{home} or Draw (1X)", "dc_x2": f"{away} or Draw (X2)", "dc_12": "No draw (12)",
             "dnb_home": f"{home} DNB", "dnb_away": f"{away} DNB",
             "btts_yes": "BTTS Yes", "btts_no": "BTTS No"}
    rows = []
    agents = agents or {}
    for key in p_mkt:
        label = names.get(key) or key.replace("_", " ").title()
        push = p_mkt["draw"] if key.startswith("dnb_") else 0.0
        lenses = {"market": p_mkt[key], "engine": p_eng[key] if p_eng else None,
                  "agents": agents.get(label)}
        rows.append(_row(label, prices.get(key), lenses, float(sim[key]), push))
    return _finish(f"{home} vs {away}", "SOCCER", rows, flags,
                   {"lambdas": {"market": [round(lh_m, 3), round(la_m, 3)],
                                "engine": [round(x, 3) for x in eng] if eng else None,
                                "blended": [round(lh_b, 3), round(la_b, 3)],
                                "engine_source": src},
                    "n_sims": n_sims, "sim_note": "scorelines sampled from the Dixon-Coles matrix"},
                   min_decimal)


# ── TENNIS ────────────────────────────────────────────────────────────────────
def judge_tennis(home: str, away: str, prices: dict, surface: str = "Hard",
                 best_of: int = 3, n_sims: int = wj.N_SIMS, seed: int = 13,
                 min_decimal: float = wj.MIN_DECIMAL, agents: Optional[dict] = None) -> dict:
    """prices: {"home_ml","away_ml"} required; optional "home_wins_a_set",
    "away_wins_a_set","home_set1","away_set1"."""
    import edge_api as ea
    import tennis_live as tl
    if not ea.ALL_RATINGS:
        ea.load_all()
    flags: list[str] = []
    ph_mkt, _ = wj.devig_pair(prices["home_ml"], prices["away_ml"])
    t = ea.predict(ea.PredictReq(sport="TENNIS", home_team=home, away_team=away,
                                 home_odds=_american(prices["home_ml"]),
                                 away_odds=_american(prices["away_ml"]),
                                 surface=surface, best_of=best_of))
    ph_eng = t.get("home_cover_prob") if t.get("bet_signal") != "NO_DATA" else None
    if ph_eng is None:
        flags.append("ENGINE_NO_DATA: players not in tennis ratings — market lens only")
    if t.get("model_split"):
        flags.append(f"MODEL_SPLIT: {t['model_split']}")
    if t.get("ranks_stale"):
        flags.append(f"RANKS_STALE: {t['ranks_stale']}")

    def set_markets(pm: float) -> dict:
        ps = tl.implied_set_prob(pm, best_of)
        n = tl.sets_to_win(best_of)
        return {"home_ml": pm, "away_ml": 1 - pm,
                "home_wins_a_set": 1 - (1 - ps) ** n, "away_wins_a_set": 1 - ps ** n,
                "home_set1": ps, "away_set1": 1 - ps}

    m_mkt = set_markets(ph_mkt)
    m_eng = set_markets(ph_eng) if ph_eng else None
    pm_b = ((W_MARKET * ph_mkt + W_ENGINE * ph_eng) / (W_MARKET + W_ENGINE)) if ph_eng else ph_mkt
    ps_b = tl.implied_set_prob(pm_b, best_of)
    need = tl.sets_to_win(best_of)
    rng = np.random.default_rng(seed)
    sets = rng.random((n_sims, 2 * need - 1)) < ps_b          # True = home wins that set
    hw = np.cumsum(sets, axis=1)
    aw = np.cumsum(~sets, axis=1)
    # match ends when someone reaches `need`; count sets actually played
    home_won = (hw >= need).any(axis=1) & (np.argmax(hw >= need, axis=1) <
                                           np.where((aw >= need).any(axis=1), np.argmax(aw >= need, axis=1), 99))
    end = np.where(home_won, np.argmax(hw >= need, axis=1), np.argmax(aw >= need, axis=1))
    played = np.arange(2 * need - 1)[None, :] <= end[:, None]
    home_any = (sets & played).any(axis=1)
    away_any = (~sets & played).any(axis=1)
    sim = {"home_ml": np.mean(home_won), "away_ml": np.mean(~home_won),
           "home_wins_a_set": np.mean(home_any), "away_wins_a_set": np.mean(away_any),
           "home_set1": np.mean(sets[:, 0]), "away_set1": np.mean(~sets[:, 0])}
    names = {"home_ml": f"{home} ML", "away_ml": f"{away} ML",
             "home_wins_a_set": f"{home} wins a set", "away_wins_a_set": f"{away} wins a set",
             "home_set1": f"{home} set 1", "away_set1": f"{away} set 1"}
    agents = agents or {}
    rows = [_row(names[k], prices.get(k),
                 {"market": m_mkt[k], "engine": m_eng[k] if m_eng else None,
                  "agents": agents.get(names[k])}, float(sim[k]))
            for k in m_mkt]
    return _finish(f"{home} vs {away}", "TENNIS", rows, flags,
                   {"engine": {"method": t.get("method"), "points": t.get("points_model_home_prob"),
                               "serve": t.get("serve_model_home_prob"), "fused": ph_eng},
                    "surface": surface, "best_of": best_of, "n_sims": n_sims,
                    "sim_note": "matches simulated set by set"}, min_decimal)


def _american(price) -> float:
    d = wj.to_decimal(price)
    return (d - 1) * 100 if d >= 2 else -100 / (d - 1)


# ── MLB (pitcher lens on top of the margin Judge) ─────────────────────────────
def mlb_engine_probs(home: str, away: str) -> tuple[dict, Optional[dict]]:
    """Pitcher-adjusted probabilities keyed by the Judge's candidate labels."""
    try:
        import mlb_game_model as mgm
        r = mgm.predict(home, away)
        if r.get("error"):
            return {}, None
        probs = {f"{home} ML": float(r["ml"]["home"]), f"{away} ML": float(r["ml"]["away"])}
        rl = r.get("run_line") or {}
        if "home -1.5" in rl:
            probs[f"{home} -1.5"] = float(rl["home -1.5"])
            probs[f"{away} +1.5"] = float(rl.get("away +1.5", 1 - rl["home -1.5"]))
        starters = (r.get("context") or {}).get("probable_starters")
        return probs, starters
    except Exception:                                          # noqa: BLE001
        return {}, None


def judge_mlb(game: dict, n_sims: int = wj.N_SIMS, **kw) -> dict:
    probs, starters = mlb_engine_probs(game["home"], game["away"])
    g = {**game, "sport": "MLB", "engine_probs": probs}
    out = wj.judge_game(g, n_sims=n_sims, **kw)
    out["probable_starters"] = starters
    if not probs:
        out["flags"].append("PITCHER_ENGINE_NO_DATA — ratings + market only")
    return out
