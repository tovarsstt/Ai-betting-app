"""Tests for the ATP serve/break-point aggregation (fetch_tennis_serve_stats.py).
Pure function tests on synthetic rows — no network."""
import fetch_tennis_serve_stats as fss


def _row(winner="Frances Tiafoe", loser="Ben Shelton", wt=1.0, **overrides):
    row = {
        "winner_name": winner, "loser_name": loser, "__wt": wt,
        "w_ace": 10, "w_df": 2, "w_svpt": 80, "w_1stIn": 50, "w_1stWon": 40,
        "w_2ndWon": 18, "w_SvGms": 12, "w_bpSaved": 6, "w_bpFaced": 8,
        "l_ace": 5, "l_df": 4, "l_svpt": 75, "l_1stIn": 45, "l_1stWon": 30,
        "l_2ndWon": 12, "l_SvGms": 12, "l_bpSaved": 3, "l_bpFaced": 9,
    }
    row.update(overrides)
    return row


# ── name_key ─────────────────────────────────────────────────────────────────
def test_name_key_full_name():
    assert fss.name_key("Frances Tiafoe") == ("tiafoe", "f")


def test_name_key_initial_form():
    assert fss.name_key("Tiafoe F.") == ("tiafoe", "f")


def test_name_key_single_token_is_none():
    assert fss.name_key("Madonna") is None


# ── aggregate: basic math ────────────────────────────────────────────────────
def test_aggregate_computes_winner_serve_rates():
    rows = [_row() for _ in range(3)]  # 3x weight 1.0 -> svpt = 240 >= MIN_SVPT
    players = fss.aggregate(rows)
    w = players["tiafoe|f"]
    assert w["ace_rate"] == round(10 / 80, 4)
    assert w["first_serve_pct"] == round(50 / 80, 4)
    assert w["first_serve_win_pct"] == round(40 / 50, 4)
    assert w["second_serve_win_pct"] == round(18 / 30, 4)  # svpt - 1stIn = 30


def test_aggregate_bp_save_pct_from_own_faced_saved():
    rows = [_row() for _ in range(3)]
    players = fss.aggregate(rows)
    w = players["tiafoe|f"]
    assert w["bp_save_pct"] == round(6 / 8, 4)


def test_aggregate_bp_convert_pct_from_opponent_faced_saved():
    rows = [_row() for _ in range(3)]
    players = fss.aggregate(rows)
    # Loser's (Shelton's) return conversion vs Tiafoe's serve: Tiafoe faced 8,
    # saved 6 -> Shelton converted (8-6)/8 = 0.25 as the RETURNER in this match.
    l = players["shelton|b"]
    assert l["bp_convert_pct"] == round((8 - 6) / 8, 4)


# ── aggregate: thresholds ────────────────────────────────────────────────────
def test_aggregate_drops_player_below_min_svpt():
    rows = [_row()]  # single match, svpt=80 < MIN_SVPT(200)
    players = fss.aggregate(rows)
    assert "tiafoe|f" not in players


def test_aggregate_omits_bp_save_pct_below_threshold():
    # Enough svpt volume but bpFaced stays under MIN_BP_FACED(10) per match * 3.
    rows = [_row(w_bpFaced=2, w_bpSaved=1) for _ in range(3)]  # 6 total < 10
    players = fss.aggregate(rows)
    assert "bp_save_pct" not in players["tiafoe|f"]


def test_aggregate_weights_recency():
    heavy = [_row(wt=3.0, w_ace=20) for _ in range(3)]   # weight-3 rows, high aces
    light = [_row(wt=1.0, w_ace=0) for _ in range(1)]     # weight-1 row, zero aces
    players = fss.aggregate(heavy + light)
    # Weighted ace total dominated by the heavy rows -> ace_rate close to 20/80, not 0.
    assert players["tiafoe|f"]["ace_rate"] > 0.2


# ── aggregate: data integrity ────────────────────────────────────────────────
def test_aggregate_skips_row_with_missing_stat_for_a_player():
    rows = [_row() for _ in range(3)] + [_row(w_svpt=None)]  # 4th row: winner incomplete
    players = fss.aggregate(rows)
    # The incomplete row must NOT be counted for the winner (still exactly 3 rows' worth).
    assert players["tiafoe|f"]["n"] == 3.0


def test_aggregate_ignores_unparseable_names():
    rows = [_row(winner="Madonna", loser="Prince")]
    players = fss.aggregate(rows)
    assert players == {}
