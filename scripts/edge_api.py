"""
Caveman Edge API — port 8001
Unified model server for NBA, WNBA, NFL, MLB, Tennis, Soccer.
Spawned automatically by server.ts on startup.

POST /predict  {"sport","home_team","away_team","spread","home_odds","away_odds"}
GET  /health
GET  /teams/{sport}
"""
import json, pickle, numpy as np
from pathlib import Path
from typing import Optional
from scipy.stats import norm, poisson as sp_poisson
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

import soccer_markets as sm
import ufc_markets as um

BASE = Path(__file__).parent.parent / "data"
app = FastAPI(title="Caveman Edge API", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BUNDLES: dict = {}
ALL_RATINGS: dict = {}
SIGMA = {"NBA": 11.5, "WNBA": 9.5, "NFL": 13.5, "MLB": 3.0, "TENNIS": 30.0, "SOCCER": 2.0, "Tennis": 30.0, "Soccer": 2.0}

@app.on_event("startup")
def load_all():
    for sport in ["nba", "wnba", "nfl", "mlb", "tennis", "soccer"]:
        p = BASE / f"edge_model_{sport}.pkl"
        if p.exists():
            with open(p, "rb") as f:
                BUNDLES[sport.upper()] = pickle.load(f)
    if (BASE / "all_ratings.json").exists():
        with open(BASE / "all_ratings.json") as f:
            ALL_RATINGS.update(json.load(f))
    # Sanitize NaN values from training output — they poison predictions and
    # crash JSON serialization. A field with NaN is treated as missing.
    for sport_key, teams_map in list(ALL_RATINGS.items()):
        if isinstance(teams_map, dict):
            ALL_RATINGS[sport_key] = {
                team: {k: v for k, v in (ratings or {}).items()
                       if not (isinstance(v, float) and v != v)}
                for team, ratings in teams_map.items()
            }
    if (BASE / "mlb_ratings.json").exists():
        with open(BASE / "mlb_ratings.json") as f:
            ALL_RATINGS["MLB"] = json.load(f)
    print(f"[EdgeAPI] {len(BUNDLES)} models: {list(BUNDLES.keys())}")

# ── Team resolution ───────────────────────────────────────────────────────────
NBA_IDS = {
    "atlanta hawks":1610612737,"boston celtics":1610612738,"brooklyn nets":1610612751,
    "charlotte hornets":1610612766,"chicago bulls":1610612741,"cleveland cavaliers":1610612739,
    "dallas mavericks":1610612742,"denver nuggets":1610612743,"detroit pistons":1610612765,
    "golden state warriors":1610612744,"houston rockets":1610612745,"indiana pacers":1610612754,
    "la clippers":1610612746,"los angeles clippers":1610612746,"los angeles lakers":1610612747,
    "memphis grizzlies":1610612763,"miami heat":1610612748,"milwaukee bucks":1610612749,
    "minnesota timberwolves":1610612750,"new orleans pelicans":1610612740,"new york knicks":1610612752,
    "oklahoma city thunder":1610612760,"orlando magic":1610612753,"philadelphia 76ers":1610612755,
    "phoenix suns":1610612756,"portland trail blazers":1610612757,"sacramento kings":1610612758,
    "san antonio spurs":1610612759,"toronto raptors":1610612761,"utah jazz":1610612762,
    "washington wizards":1610612764,
    "hawks":1610612737,"celtics":1610612738,"nets":1610612751,"hornets":1610612766,
    "bulls":1610612741,"cavs":1610612739,"cavaliers":1610612739,"mavs":1610612742,
    "mavericks":1610612742,"nuggets":1610612743,"pistons":1610612765,"warriors":1610612744,
    "gsw":1610612744,"rockets":1610612745,"pacers":1610612754,"clippers":1610612746,
    "lakers":1610612747,"grizzlies":1610612763,"heat":1610612748,"bucks":1610612749,
    "timberwolves":1610612750,"twolves":1610612750,"pelicans":1610612740,"knicks":1610612752,
    "thunder":1610612760,"okc":1610612760,"magic":1610612753,"76ers":1610612755,
    "sixers":1610612755,"suns":1610612756,"blazers":1610612757,"kings":1610612758,
    "spurs":1610612759,"raptors":1610612761,"jazz":1610612762,"wizards":1610612764,
}

def resolve_nba_id(name: str):
    k = name.lower().strip()
    if k in NBA_IDS: return str(NBA_IDS[k])
    for alias, tid in NBA_IDS.items():
        if k in alias or alias in k: return str(tid)
    return None

def get_ratings(sport: str, name: str) -> dict:
    su = sport.upper()
    # all_ratings.json uses mixed-case keys ("Tennis", "Soccer") — find case-insensitively
    src = ALL_RATINGS.get(su) or next(
        (v for k, v in ALL_RATINGS.items() if k.upper() == su), {}
    )
    if su in ("NBA", "WNBA"):
        tid = resolve_nba_id(name)
        r = src.get(tid or "", {})
        return r or {"off_rtg":114.0,"def_rtg":114.0,"net_rtg":0.0,"pace":100.0,"ts_pct":0.565}
    k = name.strip()
    if k in src: return src[k]
    kl = k.lower()
    for ck, cv in src.items():
        if kl in ck.lower() or ck.lower() in kl: return cv
    defaults = {
        "NFL":    {"ppg":22.5,"pag":22.5,"net":0.0},
        "MLB":    {"rs":4.5,"ra":4.5,"net":0.0},
        "Soccer": {"attack":1.4,"defense":1.2},
        "Tennis": {"rank":100},
    }
    return defaults.get(su, {})

# ── Feature builders ──────────────────────────────────────────────────────────
def feats_nba(h, a, la=114.0, ha=2.8):
    pa = (h.get("pace",100) + a.get("pace",100)) / 2
    fm = ((h.get("off_rtg",la)*a.get("def_rtg",la)/la - a.get("off_rtg",la)*h.get("def_rtg",la)/la) * (pa/100) + ha)
    return [h.get("off_rtg",la)-a.get("off_rtg",la), h.get("def_rtg",la)-a.get("def_rtg",la),
            h.get("net_rtg",0)-a.get("net_rtg",0), pa,
            h.get("off_rtg",la)-a.get("def_rtg",la), a.get("off_rtg",la)-h.get("def_rtg",la),
            h.get("ts_pct",0.565)-a.get("ts_pct",0.565), ha, fm,
            h.get("off_rtg",la), h.get("def_rtg",la), a.get("off_rtg",la), a.get("def_rtg",la)]

def feats_nfl(h, a):
    hp,ap,hpa,apa = h.get("ppg",22.5),a.get("ppg",22.5),h.get("pag",22.5),a.get("pag",22.5)
    return [hp,hpa,ap,apa,hp-ap,hpa-apa,hp-apa,ap-hpa,2.5]

def feats_mlb(h, a):
    hrs,hra,ars,ara = h.get("rs",4.5),h.get("ra",4.5),a.get("rs",4.5),a.get("ra",4.5)
    return [hrs,hra,ars,ara,hrs-ars,hra-ara,hrs-ara,ars-hra,0.15]

def feats_soccer(h, a):
    ha,hd,aa,ad = h.get("attack",1.4),h.get("defense",1.2),a.get("attack",1.4),a.get("defense",1.2)
    return [ha,hd,aa,ad,ha-aa,hd-ad,ha*ad,aa*hd,0.3]

def feats_tennis(h, a):
    # Features match new train_tennis: abs_rank_gap, surface (0=Hard default)
    gap = abs(a.get("rank",100) - h.get("rank",100))
    return [gap, 0]  # surface=0 (Hard) — unknown at prediction time

BUILDERS = {"NBA":feats_nba,"WNBA":lambda h,a:feats_nba(h,a,107.0,2.2),
            "NFL":feats_nfl,"MLB":feats_mlb,"SOCCER":feats_soccer,"TENNIS":feats_tennis,
            "Soccer":feats_soccer,"Tennis":feats_tennis}

# ── Poisson for Soccer ────────────────────────────────────────────────────────
def poisson_cover(lh: float, la: float, spread: float) -> float:
    # Home covers when margin + spread > 0 (spread is negative for favorites).
    # The old `margin > spread` test had the sign flipped: Swiss -1.75 was
    # scored as "lose by 1 or less" instead of "win by 2+" → 92% vs real ~40%.
    prob = 0.0
    for hg in range(20):
        for ag in range(20):
            if (hg - ag) + spread > 0:
                prob += sp_poisson.pmf(hg, lh) * sp_poisson.pmf(ag, la)
    return prob

# ── Math helpers ──────────────────────────────────────────────────────────────
def implied_prob(o: float) -> float:
    return (-o)/(-o+100) if o < 0 else 100/(o+100)

def ev(mp: float, o: float) -> float:
    d = (o/100+1) if o>=0 else (100/(-o)+1)
    return round(mp*(d-1)-(1-mp), 4)

def kelly(mp: float, o: float, br: float) -> float:
    d = (o/100+1) if o>=0 else (100/(-o)+1)
    b = d - 1
    if b<=0 or mp<=0: return 0
    f = (b*mp-(1-mp))/b
    return round(max(0,min(f/2,0.25))*br, 2)

# ── Predict endpoint ──────────────────────────────────────────────────────────
class PredictReq(BaseModel):
    sport: str = "NBA"
    home_team: str
    away_team: str
    spread: float = 0.0
    home_odds: float = -110.0
    away_odds: float = -110.0
    bankroll: float = 1000.0
    neutral: bool = False  # neutral venue (World Cup) — no home boost

def _formula_margin(sport: str, h_r: dict, a_r: dict) -> float:
    """Pure-formula margin prediction — used when model is missing or degenerate."""
    if sport in ("NBA", "WNBA"):
        la = 114.0 if sport == "NBA" else 107.0
        ha = 2.8   if sport == "NBA" else 2.2
        return ((h_r.get("off_rtg",la)*a_r.get("def_rtg",la)/la
                 - a_r.get("off_rtg",la)*h_r.get("def_rtg",la)/la) + ha)
    if sport == "NFL":
        return ((h_r.get("ppg",22.5)-h_r.get("pag",22.5))
                - (a_r.get("ppg",22.5)-a_r.get("pag",22.5)) + 2.5)
    if sport == "MLB":
        return ((h_r.get("rs",4.5)-h_r.get("ra",4.5))
                - (a_r.get("rs",4.5)-a_r.get("ra",4.5)) + 0.15)
    return 0.0

def _model_is_usable(bundle: dict, sigma: float) -> bool:
    """Model is usable only when CV MAE is meaningfully below sigma (adds real signal)."""
    if bundle is None: return False
    mae = bundle.get("avg_mae", sigma)
    # Must beat sigma by at least 5% to be considered useful
    return mae < sigma * 0.95

@app.post("/predict")
def predict(req: PredictReq):
    sport = req.sport.upper()
    bundle = BUNDLES.get(sport)
    # Use model's own MAE as sigma if available, else fall back to industry-standard
    sigma = bundle.get("avg_mae", SIGMA.get(sport, 11.5)) if bundle else SIGMA.get(sport, 11.5)

    h_r = get_ratings(sport, req.home_team)
    a_r = get_ratings(sport, req.away_team)

    # ── Data gate: unknown teams → NO prediction. With default ratings the
    # model's prob is pure noise; comparing noise to market odds fabricates
    # "EV" and Kelly recommendations from nothing. Refuse honestly instead.
    if not h_r or not a_r:
        hr_i, ar_i = implied_prob(req.home_odds), implied_prob(req.away_odds)
        ht_i, at_i = hr_i / (hr_i + ar_i), ar_i / (hr_i + ar_i)
        return {
            "sport": sport, "home_team": req.home_team, "away_team": req.away_team,
            "predicted_margin": None, "spread": req.spread, "model_edge": None,
            "home_cover_prob": None, "away_cover_prob": None,
            "home_ev_pct": None, "away_ev_pct": None,
            "home_kelly_usd": 0.0, "away_kelly_usd": 0.0,
            "home_true_prob": round(ht_i, 4), "away_true_prob": round(at_i, 4),
            "vig_pct": round((hr_i + ar_i - 1) * 100, 2),
            "bet_signal": "NO_DATA", "edge_strength": "NO_DATA",
            "home_ratings": h_r, "away_ratings": a_r,
            "model_mae": None, "trained_on": 0, "model_loaded": False,
            "model_note": "teams not in training data — only market-implied probs returned, no model opinion",
        }

    # ── Tennis: logistic win-probability model (rank-difference based) ─────────
    # The trained XGBoost tennis model is degenerate (it predicts rank_diff → rank_diff
    # which is circular and produces MAE=0 on training but zero real signal).
    # Use a calibrated logistic curve on rank difference instead.
    if sport == "TENNIS":
        h_rank = float(h_r.get("rank", 100))
        a_rank = float(a_r.get("rank", 100))
        # Positive rank_diff → home player has a better (lower) rank number
        rank_diff = a_rank - h_rank
        import math
        # k=0.010 calibrated to ATP data: rank gap of 100 → ~73% favorite win prob
        hcp = 1.0 / (1.0 + math.exp(-rank_diff * 0.010))
        acp = 1.0 - hcp
        pred_margin = rank_diff * 0.1  # proxy for display
        extra = {"method": "LogisticRank", "rank_diff": round(rank_diff, 1)}
        model_used = False
    else:
        # ── Run model only when it adds real signal (MAE < 95% of sigma) ──────
        pred_margin = 0.0
        model_used  = False
        if _model_is_usable(bundle, sigma) and sport in BUILDERS:
            try:
                feats = BUILDERS[sport](h_r, a_r)
                n     = len(bundle["feature_cols"])
                feats = (feats + [0.0]*n)[:n]
                X_sc  = bundle["scaler"].transform(np.array(feats).reshape(1,-1))
                pred_margin = float(bundle["model"].predict(X_sc)[0])
                model_used  = True
            except Exception as e:
                print(f"[EdgeAPI] model error for {sport}: {e}")

        if not model_used:
            pred_margin = _formula_margin(sport, h_r, a_r)

        # ── Cover probability ──────────────────────────────────────────────────
        if sport in ("Soccer", "SOCCER"):
            home_boost = 1.0 if req.neutral else 1.3
            lh = max(0.3, h_r.get("attack",1.4) * a_r.get("defense",1.2) * home_boost)
            la = max(0.3, a_r.get("attack",1.4) * h_r.get("defense",1.2))
            hcp = poisson_cover(lh, la, req.spread)
            extra = {"lambda_home": round(lh,2), "lambda_away": round(la,2), "method": "Poisson"}
        else:
            # Cover condition: margin + spread > 0 (same sign fix as poisson_cover)
            hcp = float(norm.cdf((pred_margin + req.spread) / sigma))
            extra = {}
        acp = 1.0 - hcp

    # ── Devig + EV + Kelly ─────────────────────────────────────────────────────
    hr, ar = implied_prob(req.home_odds), implied_prob(req.away_odds)
    vig = round((hr+ar-1)*100, 2)
    ht, at = hr/(hr+ar), ar/(hr+ar)  # devigged true probs
    hev, aev = ev(hcp, req.home_odds), ev(acp, req.away_odds)
    hk,  ak  = kelly(hcp, req.home_odds, req.bankroll), kelly(acp, req.away_odds, req.bankroll)

    # ── Signal ─────────────────────────────────────────────────────────────────
    # Edge vs market = predicted margin minus market-expected margin (-spread)
    edge = round(pred_margin + req.spread, 2)
    ea   = abs(edge)
    best_ev = max(hev, aev)
    strength = ("STRONG" if ea>=5.0 and best_ev>0.05
                else "MODERATE" if ea>=3.0 and best_ev>0.025
                else "WEAK" if ea>=1.5 and best_ev>0.01
                else "NO_EDGE")
    signal   = ("HOME_COVER" if edge>1.5 and hev>0 and hev>=aev
                else "AWAY_COVER" if edge<-1.5 and aev>0 and aev>=hev
                else "NO_EDGE")

    return {
        "sport": sport, "home_team": req.home_team, "away_team": req.away_team,
        "predicted_margin": round(pred_margin,2), "spread": req.spread,
        "model_edge": edge,
        "home_cover_prob": round(hcp,4), "away_cover_prob": round(acp,4),
        "home_ev_pct": round(hev*100,2), "away_ev_pct": round(aev*100,2),
        "home_kelly_usd": hk, "away_kelly_usd": ak,
        "home_true_prob": round(ht,4), "away_true_prob": round(at,4),
        "vig_pct": vig,
        "bet_signal": signal, "edge_strength": strength,
        "home_ratings": h_r, "away_ratings": a_r,
        "model_mae": round(bundle["avg_mae"] if (bundle and model_used) else sigma, 2),
        "trained_on": bundle["trained_on"] if bundle else 0,
        "model_loaded": model_used,
        **extra,
    }

# ── Full soccer market board (1X2 / DC / DNB / O-U / BTTS / corners) ───────────
class SoccerMarketReq(BaseModel):
    home_team: str
    away_team: str
    neutral: bool = True          # World Cup = neutral venue, no home boost
    rho: float = sm.DEFAULT_RHO   # Dixon-Coles draw/low-score correction
    # Optional book prices (American). Provide to get EV/edge per market.
    home_odds: Optional[float] = None
    draw_odds: Optional[float] = None
    away_odds: Optional[float] = None
    dc_home_draw_odds: Optional[float] = None
    dc_away_draw_odds: Optional[float] = None
    dnb_home_odds: Optional[float] = None
    dnb_away_odds: Optional[float] = None
    over_2_5_odds: Optional[float] = None
    under_2_5_odds: Optional[float] = None
    btts_yes_odds: Optional[float] = None
    btts_no_odds: Optional[float] = None


@app.post("/predict-soccer")
def predict_soccer(req: SoccerMarketReq):
    """
    Full World-Cup-ready soccer board. Unlike /predict (which devigged soccer
    as a 2-way market and ignored the draw), this prices every market from one
    bivariate Poisson + Dixon-Coles score matrix, then recommends draw-insured
    plays (Double Chance / Draw No Bet) when the favourite is better but the
    draw is live.
    """
    h_r = get_ratings("Soccer", req.home_team)
    a_r = get_ratings("Soccer", req.away_team)
    if not h_r or not a_r:
        return {"status": "NO_DATA",
                "note": "team(s) not in soccer ratings — no model opinion",
                "home_ratings": h_r, "away_ratings": a_r}

    # Goal rates: prefer MARKET-CALIBRATED lambdas (fit to the devigged 1X2) when
    # full 3-way odds are supplied — the sharp market beats our national-team
    # ratings. Fall back to ratings only when odds are missing.
    calibrated = False
    lambda_source = "ratings"
    if None not in (req.home_odds, req.draw_odds, req.away_odds):
        dv0 = sm.devig_3way(req.home_odds, req.draw_odds, req.away_odds)
        lh, la, _resid = sm.solve_lambdas_from_1x2(dv0["home"], dv0["draw"], dv0["away"])
        calibrated = True
        lambda_source = "market_calibrated"
    else:
        home_boost = 1.0 if req.neutral else 1.3
        lh = max(0.3, h_r.get("attack", 1.4) * a_r.get("defense", 1.2) * home_boost)
        la = max(0.3, a_r.get("attack", 1.4) * h_r.get("defense", 1.2))

    matrix = sm.score_matrix(lh, la, rho=req.rho)
    book = sm.derive_markets(matrix)
    market_odds = sm.MarketOdds(
        home=req.home_odds, draw=req.draw_odds, away=req.away_odds,
        dc_home_draw=req.dc_home_draw_odds, dc_away_draw=req.dc_away_draw_odds,
        dnb_home=req.dnb_home_odds, dnb_away=req.dnb_away_odds,
        over_2_5=req.over_2_5_odds, under_2_5=req.under_2_5_odds,
        btts_yes=req.btts_yes_odds, btts_no=req.btts_no_odds,
    )
    rec = sm.recommend(book, req.home_team, req.away_team, market_odds)

    # 3-way devig + model-vs-market edge when full 1X2 odds are supplied.
    # market_recommendation runs the draw-insurance logic on the SHARP MARKET
    # probabilities — authoritative when ratings are unreliable (WC nat. teams).
    market_3way = None
    market_recommendation = None
    if None not in (req.home_odds, req.draw_odds, req.away_odds):
        dv = sm.devig_3way(req.home_odds, req.draw_odds, req.away_odds)
        market_3way = {
            "devigged": {k: round(v, 4) for k, v in dv.items() if k != "vig_pct"},
            "vig_pct": dv["vig_pct"],
            "model_edge": {
                "home": round(book.home_win - dv["home"], 4),
                "draw": round(book.draw - dv["draw"], 4),
                "away": round(book.away_win - dv["away"], 4),
            },
        }
        market_recommendation = sm.recommend_1x2(
            dv["home"], dv["draw"], dv["away"], req.home_team, req.away_team,
            req.home_odds, req.draw_odds, req.away_odds,
        )

    return {
        "status": "OK",
        "home_team": req.home_team, "away_team": req.away_team,
        "neutral_venue": req.neutral,
        "lambda_home": round(lh, 3), "lambda_away": round(la, 3),
        "lambda_source": lambda_source,
        "method": f"{'MarketCalibrated' if calibrated else 'Ratings'}Poisson+DixonColes(rho={req.rho})",
        "markets": {
            "1x2": {"home": round(book.home_win, 4), "draw": round(book.draw, 4),
                    "away": round(book.away_win, 4)},
            "double_chance": {"1X": round(book.dc_home_draw, 4),
                              "X2": round(book.dc_away_draw, 4),
                              "12": round(book.dc_home_away, 4)},
            "draw_no_bet": {"home": round(book.dnb_home, 4),
                            "away": round(book.dnb_away, 4)},
            "totals": {str(ln): {"over": round(v["over"], 4),
                                 "under": round(v["under"], 4)}
                       for ln, v in book.over_under.items()},
            "btts": {"yes": round(book.btts_yes, 4), "no": round(book.btts_no, 4)},
            "expected_total_goals": round(book.expected_total_goals, 3),
            "corners": sm.estimate_corners(lh, la),
        },
        "market_3way": market_3way,
        "market_recommendation": market_recommendation,
        "recommendation": rec,
        "home_ratings": h_r, "away_ratings": a_r,
    }


# ── UFC / MMA full board (ML / method / rounds / distance) ─────────────────────
class UFCReq(BaseModel):
    fighter_a: str
    fighter_b: str
    scheduled_rounds: int = 3       # 3 = prelim/main-card, 5 = main event / title
    # Win-prob source (priority: explicit probs → moneyline → 50/50)
    a_win_prob: Optional[float] = None
    b_win_prob: Optional[float] = None
    ml_a: Optional[float] = None
    ml_b: Optional[float] = None
    # Fighter finish profiles (omit → documented UFC empirical priors, flagged)
    a_finish_rate: Optional[float] = None
    a_ko_share: Optional[float] = None
    a_sub_share: Optional[float] = None
    b_finish_rate: Optional[float] = None
    b_ko_share: Optional[float] = None
    b_sub_share: Optional[float] = None
    # Optional derivative odds for EV
    fav_ko_odds: Optional[float] = None
    fav_dec_odds: Optional[float] = None
    not_distance_odds: Optional[float] = None
    goes_distance_odds: Optional[float] = None


@app.post("/predict-ufc")
def predict_ufc(req: UFCReq):
    """
    Full UFC board from one fight model. No ratings file needed — win prob comes
    from explicit estimates or the devigged moneyline; method/round/distance
    markets use fighter finish profiles when supplied, else documented UFC-wide
    empirical priors (flagged in data_note).
    """
    a = um.Fighter(req.fighter_a, req.a_win_prob, req.a_finish_rate,
                   req.a_ko_share, req.a_sub_share)
    b = um.Fighter(req.fighter_b, req.b_win_prob, req.b_finish_rate,
                   req.b_ko_share, req.b_sub_share)
    moneyline = (req.ml_a, req.ml_b) if None not in (req.ml_a, req.ml_b) else None
    rounds = 5 if req.scheduled_rounds == 5 else 3

    fb = um.build_fight(a, b, scheduled_rounds=rounds, moneyline=moneyline)
    odds = um.UFCOdds(ml_a=req.ml_a, ml_b=req.ml_b, fav_ko=req.fav_ko_odds,
                      fav_dec=req.fav_dec_odds, not_distance=req.not_distance_odds,
                      goes_distance=req.goes_distance_odds)
    rec = um.recommend(fb, odds)

    return {
        "status": "OK",
        "fighter_a": fb.name_a, "fighter_b": fb.name_b,
        "scheduled_rounds": fb.scheduled_rounds,
        "method": "FightModel(finish_split+round_decay)",
        "markets": {
            "moneyline": {fb.name_a: round(fb.p_a, 4), fb.name_b: round(fb.p_b, 4)},
            "method": {
                fb.name_a: {"ko": round(fb.a_ko, 4), "sub": round(fb.a_sub, 4),
                            "dec": round(fb.a_dec, 4)},
                fb.name_b: {"ko": round(fb.b_ko, 4), "sub": round(fb.b_sub, 4),
                            "dec": round(fb.b_dec, 4)},
                "grouped": {"ko_any": round(fb.ko_any, 4),
                            "sub_any": round(fb.sub_any, 4),
                            "decision_any": round(fb.decision_any, 4)},
            },
            "distance": {"goes_distance": round(fb.goes_distance, 4),
                         "not_distance": round(fb.not_distance, 4)},
            "round_totals": fb.round_totals,
            "finish_by_round": fb.finish_by_round,
        },
        "recommendation": rec,
        "used_empirical_priors": fb.used_empirical,
    }


@app.get("/health")
def health():
    return {"status":"ok","models":list(BUNDLES.keys()),"ratings":list(ALL_RATINGS.keys())}

@app.get("/teams/{sport}")
def teams(sport: str):
    # Ratings keys are mixed-case ("Tennis", "Soccer") — match case-insensitively
    su = sport.upper()
    return ALL_RATINGS.get(su) or next(
        (v for k, v in ALL_RATINGS.items() if k.upper() == su), {})

if __name__ == "__main__":
    uvicorn.run("edge_api:app", host="127.0.0.1", port=8001, reload=False, log_level="warning")
