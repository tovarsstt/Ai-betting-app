"""
Caveman Multi-Sport Edge Model Trainer
Trains XGBoost margin-predictors for: NBA, WNBA, NFL, MLB, Tennis, Soccer
Saves one model per sport + unified team_ratings.json

Run: python3 scripts/train_all_sports.py
Then restart edge_api.py to serve all sports.
"""
import json, pickle, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error
import xgboost as xgb
warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

MODELS = {}   # sport -> bundle
RATINGS = {}  # sport -> {team: ratings}

# ─────────────────────────────────────────────────────────────────────────────
# NBA / WNBA
# ─────────────────────────────────────────────────────────────────────────────
def train_nba(league="NBA"):
    from nba_api.stats.endpoints import leaguegamelog, leaguedashteamstats
    seasons_map = {
        "NBA":  ["2021-22","2022-23","2023-24","2024-25"],
        "WNBA": ["2021","2022","2023","2024"],
    }
    league_id = "00" if league == "NBA" else "10"
    seasons = seasons_map[league]
    sigma = 11.5 if league == "NBA" else 9.5

    all_ratings = {}
    all_games   = []

    for season in seasons:
        try:
            print(f"  [{league}] season {season}...")
            time.sleep(0.7)
            stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                league_id_nullable=league_id,
                measure_type_detailed_defense="Advanced",
                per_mode_detailed="PerGame",
            ).get_data_frames()[0]
            for _, row in stats.iterrows():
                all_ratings[str(int(row["TEAM_ID"]))] = {
                    "off_rtg": float(row.get("OFF_RATING", 107)),
                    "def_rtg": float(row.get("DEF_RATING", 107)),
                    "net_rtg": float(row.get("NET_RATING", 0)),
                    "pace":    float(row.get("PACE", 90 if league=="WNBA" else 100)),
                    "ts_pct":  float(row.get("TS_PCT", 0.55)),
                }
            time.sleep(0.7)
            log = leaguegamelog.LeagueGameLog(
                season=season, league_id=league_id,
                season_type_all_star="Regular Season"
            ).get_data_frames()[0]
            log["is_home"] = log["MATCHUP"].str.contains(" vs. ").astype(int)
            log["GAME_DATE"] = pd.to_datetime(log["GAME_DATE"])
            home = log[log["is_home"]==1].copy()
            away = log[log["is_home"]==0].copy()
            m = home.merge(away, on="GAME_ID", suffixes=("_h","_a"))
            m["actual_margin"] = m["PTS_h"] - m["PTS_a"]
            def gr(tid, k, d): return all_ratings.get(str(int(tid)),{}).get(k,d)
            league_avg = 107.0 if league=="WNBA" else 114.0
            home_adv   = 2.2   if league=="WNBA" else 2.8
            for col,key,dflt in [
                ("h_off","off_rtg",league_avg),("h_def","def_rtg",league_avg),
                ("h_net","net_rtg",0),("h_pace","pace",90),
                ("a_off","off_rtg",league_avg),("a_def","def_rtg",league_avg),
                ("a_net","net_rtg",0),("a_pace","pace",90),
            ]:
                src = "TEAM_ID_h" if col.startswith("h_") else "TEAM_ID_a"
                m[col] = m[src].apply(lambda t: gr(t,key,dflt))
            m["pace_avg"] = (m["h_pace"]+m["a_pace"])/2
            m["formula_margin"] = (
                (m["h_off"]*m["a_def"]/league_avg - m["a_off"]*m["h_def"]/league_avg)
                * (m["pace_avg"]/100) + home_adv
            )
            FEATS = ["h_off","h_def","h_net","a_off","a_def","a_net",
                     "pace_avg","formula_margin",
                     f"{'h_off'}-{'a_off'}".replace("-","_minus_")]
            m["off_diff"] = m["h_off"] - m["a_off"]
            m["def_diff"] = m["h_def"] - m["a_def"]
            FEATS = ["off_diff","def_diff","h_net","a_net","pace_avg",
                     "formula_margin","h_off","h_def","a_off","a_def"]
            m = m[FEATS+["actual_margin","GAME_DATE_h","GAME_ID"]].dropna()
            all_games.append(m)
        except Exception as e:
            print(f"    WARN {season}: {e}")

    return _train_model(all_games, all_ratings, league, sigma,
                        ["off_diff","def_diff","h_net","a_net","pace_avg",
                         "formula_margin","h_off","h_def","a_off","a_def"])


# ─────────────────────────────────────────────────────────────────────────────
# NFL — ESPN public API
# ─────────────────────────────────────────────────────────────────────────────
def train_nfl():
    import requests
    print("  [NFL] fetching via ESPN public API...")
    all_games = []
    team_stats = {}  # rolling ppg/pag

    def update_team(team, pts_for, pts_against):
        if team not in team_stats:
            team_stats[team] = {"ppg": pts_for, "pag": pts_against, "n": 1}
        else:
            n = team_stats[team]["n"]
            team_stats[team]["ppg"] = (team_stats[team]["ppg"] * n + pts_for) / (n + 1)
            team_stats[team]["pag"] = (team_stats[team]["pag"] * n + pts_against) / (n + 1)
            team_stats[team]["n"] += 1

    # ESPN NFL scoreboard by week/year range
    date_ranges = [
        ("20190901","20200201"), ("20200901","20210201"),
        ("20210901","20220201"), ("20220901","20230201"),
        ("20230901","20240201"), ("20240901","20250201"),
    ]
    for start, end in date_ranges:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?limit=200&dates={start}-{end}"
            r = requests.get(url, timeout=10)
            events = r.json().get("events", [])
            for e in events:
                try:
                    comps = e["competitions"][0]
                    h = comps["competitors"][0]
                    a = comps["competitors"][1]
                    if h.get("homeAway") == "away": h, a = a, h
                    if not h.get("score") or not a.get("score"): continue
                    hs = int(h["score"]); as_ = int(a["score"])
                    ht = h["team"]["displayName"]; at = a["team"]["displayName"]
                    hstats = team_stats.get(ht, {"ppg": 22, "pag": 22})
                    astats = team_stats.get(at, {"ppg": 22, "pag": 22})
                    all_games.append({
                        "h_ppg": hstats["ppg"], "h_pag": hstats["pag"],
                        "a_ppg": astats["ppg"], "a_pag": astats["pag"],
                        "ppg_diff": hstats["ppg"] - astats["ppg"],
                        "pag_diff": hstats["pag"] - astats["pag"],
                        "scoring_edge": hstats["ppg"] - astats["pag"],
                        "defense_edge": astats["ppg"] - hstats["pag"],
                        "home_advantage": 2.5,
                        "actual_margin": hs - as_,
                        "game_date": pd.to_datetime(e.get("date", "2020-01-01")),
                        "game_id": e["id"],
                    })
                    update_team(ht, hs, as_)
                    update_team(at, as_, hs)
                except: pass
            print(f"    {start[:4]} season: {len(events)} events")
        except Exception as ex:
            print(f"    WARN {start[:4]}: {ex}")

    curr_ratings = {
        team: {"ppg": round(s["ppg"], 1), "pag": round(s["pag"], 1),
               "net": round(s["ppg"] - s["pag"], 1)}
        for team, s in team_stats.items()
    }
    FEATS = ["h_ppg","h_pag","a_ppg","a_pag","ppg_diff",
             "pag_diff","scoring_edge","defense_edge","home_advantage"]
    return _train_model([pd.DataFrame(all_games)] if all_games else [], curr_ratings, "NFL", 13.5, FEATS)


# ─────────────────────────────────────────────────────────────────────────────
# MLB — MLB Stats API (free, no key)
# ─────────────────────────────────────────────────────────────────────────────
def train_mlb():
    import requests
    print("  [MLB] fetching via MLB Stats API...")
    all_games = []
    team_stats = {}  # rolling runs scored/allowed

    def update_team(team, rs, ra):
        if team not in team_stats:
            team_stats[team] = {"rs": rs, "ra": ra, "n": 1}
        else:
            n = team_stats[team]["n"]
            team_stats[team]["rs"] = (team_stats[team]["rs"] * n + rs) / (n + 1)
            team_stats[team]["ra"] = (team_stats[team]["ra"] * n + ra) / (n + 1)
            team_stats[team]["n"] += 1

    season_ranges = {
        2019: ("2019-03-28","2019-10-01"), 2020: ("2020-07-23","2020-10-01"),
        2021: ("2021-04-01","2021-10-05"), 2022: ("2022-04-07","2022-10-06"),
        2023: ("2023-03-30","2023-10-02"), 2024: ("2024-03-20","2024-09-30"),
    }
    for season, (start, end) in season_ranges.items():
        try:
            url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1"
                   f"&gameType=R&start={start}&end={end}")
            r = requests.get(url, timeout=20)
            dates = r.json().get("dates", [])
            season_games = 0
            for d in dates:
                for g in d.get("games", []):
                    try:
                        home = g["teams"]["home"]
                        away = g["teams"]["away"]
                        hs = home.get("score")
                        as_ = away.get("score")
                        if hs is None or as_ is None: continue
                        hs, as_ = int(hs), int(as_)
                        ht = home["team"]["name"]
                        at = away["team"]["name"]
                        hstats = team_stats.get(ht, {"rs": 4.5, "ra": 4.5})
                        astats = team_stats.get(at, {"rs": 4.5, "ra": 4.5})
                        # Pythagorean run differential features
                        all_games.append({
                            "h_rs": hstats["rs"], "h_ra": hstats["ra"],
                            "a_rs": astats["rs"], "a_ra": astats["ra"],
                            "rs_diff": hstats["rs"] - astats["rs"],
                            "ra_diff": hstats["ra"] - astats["ra"],
                            "scoring_edge": hstats["rs"] - astats["ra"],
                            "defense_edge": astats["rs"] - hstats["ra"],
                            "home_advantage": 0.15,
                            "actual_margin": hs - as_,
                            "game_date": pd.to_datetime(d["date"]),
                            "game_id": str(g.get("gamePk", season_games)),
                        })
                        update_team(ht, hs, as_)
                        update_team(at, as_, hs)
                        season_games += 1
                    except: pass
            print(f"    {season}: {season_games} games")
        except Exception as e:
            print(f"    WARN {season}: {e}")

    curr_ratings = {
        team: {"rs": round(s["rs"], 2), "ra": round(s["ra"], 2),
               "net": round(s["rs"] - s["ra"], 2)}
        for team, s in team_stats.items()
    }
    FEATS = ["h_rs","h_ra","a_rs","a_ra","rs_diff","ra_diff",
             "scoring_edge","defense_edge","home_advantage"]
    return _train_model(
        [pd.DataFrame(all_games)] if all_games else [],
        curr_ratings, "MLB", 3.0, FEATS
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tennis — Jeff Sackmann free dataset (GitHub)
# Target: predict whether the BETTER-RANKED player wins (real prediction problem)
# Features: rank gap size, surface — no post-match stats (those are data leakage)
# ─────────────────────────────────────────────────────────────────────────────
def train_tennis():
    import requests, io
    print("  [Tennis] fetching ATP data from Jeff Sackmann GitHub...")
    base = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master"
    all_games = []
    all_ratings = {}

    for yr in [2020,2021,2022,2023,2024]:
        url = f"{base}/atp_matches_{yr}.csv"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text), low_memory=False)
            df = df[df["score"].notna()].copy()
            df["game_date"] = pd.to_datetime(df["tourney_date"], format="%Y%m%d", errors="coerce")

            for _, row in df.iterrows():
                try:
                    w_rank = float(row.get("winner_rank", 200) or 200)
                    l_rank = float(row.get("loser_rank", 200) or 200)
                    surface = str(row.get("surface", "Hard"))
                    surf_code = {"Hard": 0, "Clay": 1, "Grass": 2, "Carpet": 3}.get(surface, 0)

                    # signed: positive = the winner had a better (lower) rank number
                    # negative = upset (lower-ranked player won)
                    rank_diff = l_rank - w_rank
                    abs_gap   = abs(rank_diff)

                    # Target: actual_margin = rank_diff
                    # edge_api uses norm.cdf(rank_diff / sigma) where sigma=50
                    # → small gap (rank_diff near 0) → ~50/50
                    # → large gap (rank_diff=100) → norm.cdf(2) = 97.7% win prob for favorite
                    # This is a REAL predictive relationship, not circular,
                    # because rank_diff is NOT a feature (features are abs_gap + surface)
                    all_games.append({
                        "abs_rank_gap": abs_gap,
                        "surface": surf_code,
                        "actual_margin": rank_diff,  # signed: +ve = favorite won, -ve = upset
                        "game_date": row["game_date"],
                        "game_id": str(row.get("match_num", _)),
                    })
                    # Update player ratings
                    wp = str(row.get("winner_name",""))
                    lp = str(row.get("loser_name",""))
                    wp = str(row.get("winner_name", ""))
                    lp = str(row.get("loser_name", ""))
                    all_ratings[wp] = {"rank": w_rank}
                    if lp not in all_ratings:
                        all_ratings[lp] = {"rank": l_rank}
                except: pass
            print(f"    {yr}: {len(df)} matches")
        except Exception as e:
            print(f"    WARN {yr}: {e}")

    # sigma=50: std dev of rank_diff in ATP data (typical range 0–300)
    # norm.cdf(rank_diff / 50): rank gap 50 → 84%, gap 100 → 97%, gap 10 → 58%
    # This is a real signal: bigger rank gap → more certain favorite wins
    # Features: abs_rank_gap (magnitude) + surface — no post-match data (no leakage)
    FEATS = ["abs_rank_gap", "surface"]
    result = _train_model(
        [pd.DataFrame(all_games)] if all_games else [],
        all_ratings, "Tennis", 50.0, FEATS
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Soccer — ESPN public API
# ─────────────────────────────────────────────────────────────────────────────
def train_soccer():
    import requests
    print("  [Soccer] fetching from football-data.org free tier...")
    # Uses free football-data.org API (no key for tier 1 competitions limited)
    # Fallback to ESPN public endpoints
    all_games = []
    all_ratings = {}

    leagues = {
        "PL":  "Premier League",
        "PD":  "La Liga",
        "BL1": "Bundesliga",
        "SA":  "Serie A",
        "FL1": "Ligue 1",
    }
    base = "https://api.football-data.org/v4"
    headers = {"X-Auth-Token": ""}  # anonymous tier (very limited)

    for code, name in leagues.items():
        for season_yr in [2022,2023,2024]:
            try:
                url = f"{base}/competitions/{code}/matches?season={season_yr}&status=FINISHED"
                r = requests.get(url, headers=headers, timeout=8)
                if r.status_code == 403:
                    break  # need API key — use ESPN fallback
                data = r.json()
                for match in data.get("matches",[]):
                    try:
                        home = match["homeTeam"]["name"]
                        away = match["awayTeam"]["name"]
                        hg = int(match["score"]["fullTime"]["home"] or 0)
                        ag = int(match["score"]["fullTime"]["away"] or 0)
                        all_games.append({
                            "actual_margin": hg - ag,
                            "home_goals": hg,
                            "away_goals": ag,
                            "game_date": pd.to_datetime(match["utcDate"]),
                            "game_id": str(match["id"]),
                            "home": home, "away": away,
                        })
                    except: pass
                time.sleep(0.5)
            except: pass

    if not all_games:
        print("    football-data.org blocked (no API key) — using ESPN public...")
        # ESPN public scoreboard for recent soccer
        espn_leagues = [
            ("soccer","eng.1","Premier League"),
            ("soccer","esp.1","La Liga"),
            ("soccer","ger.1","Bundesliga"),
        ]
        for sport, league, lname in espn_leagues:
            for yr in [2023,2024]:
                try:
                    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?limit=200&dates={yr}0801-{yr+1}0531"
                    r = requests.get(url, timeout=8)
                    events = r.json().get("events",[])
                    for e in events:
                        try:
                            comps = e["competitions"][0]
                            h = comps["competitors"][0]
                            a = comps["competitors"][1]
                            if h.get("homeAway")=="away": h,a = a,h
                            hg = int(h.get("score",0))
                            ag = int(a.get("score",0))
                            all_games.append({
                                "actual_margin": hg-ag,
                                "home_goals": hg, "away_goals": ag,
                                "game_date": pd.to_datetime(e.get("date","2023-01-01")),
                                "game_id": e["id"],
                                "home": h["team"]["displayName"],
                                "away": a["team"]["displayName"],
                            })
                        except: pass
                except Exception as ex:
                    print(f"    ESPN {lname} {yr}: {ex}")

    if not all_games:
        print("  [Soccer] no data collected")
        return None, {}

    df = pd.DataFrame(all_games)

    # Build team attack/defense ratings from historical goals
    team_attack, team_defense, team_n = {}, {}, {}
    for _, r in df.sort_values("game_date").iterrows():
        for tm, gf, ga in [(r["home"],r["home_goals"],r["away_goals"]),
                            (r["away"],r["away_goals"],r["home_goals"])]:
            if tm not in team_n:
                team_attack[tm] = gf; team_defense[tm] = ga; team_n[tm] = 1
            else:
                n = team_n[tm]
                team_attack[tm]  = (team_attack[tm]*n  + gf)/(n+1)
                team_defense[tm] = (team_defense[tm]*n + ga)/(n+1)
                team_n[tm] += 1
        all_ratings[r["home"]] = {"attack": team_attack[r["home"]], "defense": team_defense[r["home"]]}
        all_ratings[r["away"]] = {"attack": team_attack[r["away"]], "defense": team_defense[r["away"]]}

    # Build features
    rows = []
    for _, r in df.iterrows():
        ht, at = r["home"], r["away"]
        ha = team_attack.get(ht,1.4); hd = team_defense.get(ht,1.2)
        aa = team_attack.get(at,1.4); ad = team_defense.get(at,1.2)
        rows.append({
            "h_attack": ha, "h_defense": hd,
            "a_attack": aa, "a_defense": ad,
            "attack_diff": ha - aa,
            "defense_diff": hd - ad,
            "expected_home_goals": ha * ad,  # Poisson lambda
            "expected_away_goals": aa * hd,
            "home_advantage": 0.3,
            "actual_margin": r["actual_margin"],
            "game_date": r["game_date"],
            "game_id": str(r["game_id"]),
        })

    FEATS = ["h_attack","h_defense","a_attack","a_defense","attack_diff",
             "defense_diff","expected_home_goals","expected_away_goals","home_advantage"]
    return _train_model([pd.DataFrame(rows)] if rows else [], all_ratings, "Soccer", 2.0, FEATS)


# ─────────────────────────────────────────────────────────────────────────────
# Core training function — honest holdout evaluation + size-based regularization
# ─────────────────────────────────────────────────────────────────────────────
def _train_model(dfs, ratings, sport, sigma, feature_cols):
    valid = [d for d in dfs if len(d) >= 20]
    if not valid:
        print(f"  [{sport}] not enough data — skipping model")
        return None, ratings

    combined = pd.concat(valid)
    date_col = "GAME_DATE_h" if "GAME_DATE_h" in combined.columns else "game_date"
    combined[date_col] = pd.to_datetime(combined[date_col], errors="coerce")
    df = combined.sort_values(date_col).reset_index(drop=True)
    df = df.dropna(subset=feature_cols+["actual_margin"])
    n_total = len(df)
    print(f"  [{sport}] {n_total} games total...")

    # ── Holdout: last 20% by date, minimum 50 games ───────────────────────────
    holdout_n = max(50, int(n_total * 0.20))
    train_df  = df.iloc[:-holdout_n]
    hold_df   = df.iloc[-holdout_n:]

    X_tr = train_df[feature_cols].values
    y_tr = train_df["actual_margin"].values
    X_ho = hold_df[feature_cols].values
    y_ho = hold_df["actual_margin"].values

    # Scale fitted on training data only (no leakage into holdout)
    scaler_tr = StandardScaler()
    X_sc_tr   = scaler_tr.fit_transform(X_tr)
    X_sc_ho   = scaler_tr.transform(X_ho)

    # ── Regularization by dataset size ────────────────────────────────────────
    n_tr = len(train_df)
    if n_tr < 500:
        params = dict(n_estimators=80,  max_depth=3, min_child_weight=8,
                      reg_alpha=1.5, reg_lambda=3.0)
    elif n_tr < 2000:
        params = dict(n_estimators=150, max_depth=3, min_child_weight=5,
                      reg_alpha=0.8, reg_lambda=2.0)
    else:
        params = dict(n_estimators=250, max_depth=4, min_child_weight=3,
                      reg_alpha=0.3, reg_lambda=1.0)

    # ── Cross-validation on training portion (time-series split) ─────────────
    tscv = TimeSeriesSplit(n_splits=min(5, n_tr // 50))
    cv_maes = []
    for tr_idx, val_idx in tscv.split(X_sc_tr):
        m = xgb.XGBRegressor(**params, learning_rate=0.05, subsample=0.8,
                              colsample_bytree=0.8, random_state=42,
                              n_jobs=-1, verbosity=0)
        m.fit(X_sc_tr[tr_idx], y_tr[tr_idx],
              eval_set=[(X_sc_tr[val_idx], y_tr[val_idx])], verbose=False)
        cv_maes.append(mean_absolute_error(y_tr[val_idx], m.predict(X_sc_tr[val_idx])))
    avg_mae = float(np.mean(cv_maes))
    print(f"  [{sport}] CV MAE: {avg_mae:.2f}  sigma: {sigma}")

    # ── Train-only model for honest holdout evaluation ────────────────────────
    eval_model = xgb.XGBRegressor(**params, learning_rate=0.04, subsample=0.8,
                                   colsample_bytree=0.8, random_state=42,
                                   n_jobs=-1, verbosity=0)
    eval_model.fit(X_sc_tr, y_tr)
    preds_ho  = eval_model.predict(X_sc_ho)
    hold_mae  = float(mean_absolute_error(y_ho, preds_ho))

    # HONEST: cover rate on out-of-sample holdout only
    typical_spread = 2.5 if sport in ("NBA","WNBA","NFL") else (1.5 if sport == "MLB" else 0.5)
    correct    = np.sum(np.sign(preds_ho - typical_spread) == np.sign(y_ho - typical_spread))
    cover_rate = float(correct / len(y_ho))
    print(f"  [{sport}] Holdout MAE: {hold_mae:.2f} | Holdout cover: {cover_rate:.1%} "
          f"(signal: {'✓ USEFUL' if avg_mae < sigma * 0.95 else '✗ NO SIGNAL — formula fallback'})")

    # ── Final model trained on ALL data, scaler fitted on all data ───────────
    scaler_all = StandardScaler()
    X_sc_all   = scaler_all.fit_transform(df[feature_cols].values)
    y_all      = df["actual_margin"].values
    final = xgb.XGBRegressor(**params, learning_rate=0.04, subsample=0.8,
                              colsample_bytree=0.8, random_state=42,
                              n_jobs=-1, verbosity=0)
    final.fit(X_sc_all, y_all)

    bundle = {
        "model": final, "scaler": scaler_all, "feature_cols": feature_cols,
        "avg_mae": avg_mae,         # CV MAE on training portion
        "holdout_mae": hold_mae,    # HONEST out-of-sample MAE
        "sigma": sigma,
        "approx_cover_rate": cover_rate,  # HONEST holdout cover rate
        "trained_on": n_total, "sport": sport,
    }
    path = DATA_DIR / f"edge_model_{sport.lower()}.pkl"
    with open(path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"  [{sport}] saved → {path}")
    return bundle, ratings


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=== CAVEMAN MULTI-SPORT TRAINING ===\n")
    all_ratings = {}

    # NBA
    print("[1/6] NBA")
    b, r = train_nba("NBA")
    if b: MODELS["NBA"] = b
    all_ratings["NBA"] = r

    # WNBA
    print("\n[2/6] WNBA")
    b, r = train_nba("WNBA")
    if b: MODELS["WNBA"] = b
    all_ratings["WNBA"] = r

    # NFL
    print("\n[3/6] NFL")
    b, r = train_nfl()
    if b: MODELS["NFL"] = b
    all_ratings["NFL"] = r

    # MLB
    print("\n[4/6] MLB")
    b, r = train_mlb()
    if b: MODELS["MLB"] = b
    all_ratings["MLB"] = r

    # Tennis
    print("\n[5/6] Tennis")
    b, r = train_tennis()
    if b: MODELS["Tennis"] = b
    all_ratings["Tennis"] = r

    # Soccer
    print("\n[6/6] Soccer")
    b, r = train_soccer()
    if b: MODELS["Soccer"] = b
    all_ratings["Soccer"] = r

    # Save unified ratings
    with open(DATA_DIR / "all_ratings.json", "w") as f:
        json.dump(all_ratings, f, indent=2)
    print(f"\nAll ratings saved → {DATA_DIR}/all_ratings.json")

    # Summary
    print("\n=== TRAINING SUMMARY ===")
    for sport, bundle in MODELS.items():
        print(f"  {sport}: {bundle['trained_on']} games | MAE ±{bundle['avg_mae']:.1f} | cover(sim) {bundle['approx_cover_rate']:.1%}")
    for sport in ["NBA","WNBA","NFL","MLB","Tennis","Soccer"]:
        if sport not in MODELS:
            print(f"  {sport}: SKIPPED (no data or package missing)")
    print("=== DONE ===")

if __name__ == "__main__":
    main()
