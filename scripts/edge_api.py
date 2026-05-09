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
from scipy.stats import norm, poisson as sp_poisson
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

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
    prob = 0.0
    for hg in range(20):
        for ag in range(20):
            if (hg - ag) > spread:
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
    sigma  = SIGMA.get(sport, 11.5)
    h_r = get_ratings(sport, req.home_team)
    a_r = get_ratings(sport, req.away_team)

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
            lh = max(0.3, h_r.get("attack",1.4) * a_r.get("defense",1.2) * 1.3)
            la = max(0.3, a_r.get("attack",1.4) * h_r.get("defense",1.2))
            hcp = poisson_cover(lh, la, req.spread)
            extra = {"lambda_home": round(lh,2), "lambda_away": round(la,2), "method": "Poisson"}
        else:
            hcp = float(norm.cdf((pred_margin - req.spread) / sigma))
            extra = {}
        acp = 1.0 - hcp

    # ── Devig + EV + Kelly ─────────────────────────────────────────────────────
    hr, ar = implied_prob(req.home_odds), implied_prob(req.away_odds)
    vig = round((hr+ar-1)*100, 2)
    ht, at = hr/(hr+ar), ar/(hr+ar)  # devigged true probs
    hev, aev = ev(hcp, req.home_odds), ev(acp, req.away_odds)
    hk,  ak  = kelly(hcp, req.home_odds, req.bankroll), kelly(acp, req.away_odds, req.bankroll)

    # ── Signal ─────────────────────────────────────────────────────────────────
    edge = round(pred_margin - req.spread, 2)
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

@app.get("/health")
def health():
    return {"status":"ok","models":list(BUNDLES.keys()),"ratings":list(ALL_RATINGS.keys())}

@app.get("/teams/{sport}")
def teams(sport: str):
    return ALL_RATINGS.get(sport.upper(), {})

if __name__ == "__main__":
    uvicorn.run("edge_api:app", host="127.0.0.1", port=8001, reload=False, log_level="warning")
