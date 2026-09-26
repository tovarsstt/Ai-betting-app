"""Tests for fetch_tennis_form.aggregate() — pure function, synthetic rows,
no network. Covers the two 2026-07-01 fixes: H2H's longer lookback window
(separate from the short form/psych/clutch window) and that old H2H meetings
still count even when they fall outside the recency window."""
import fetch_tennis_form as ftf

CUR = ftf.CUR


def _row(winner="Tiafoe F.", loser="Fritz T.", year_offset=0, surface="Hard",
         best_of=3, sets=(("6", "4"), ("6", "4")), **overrides):
    wt = ftf.YEAR_WEIGHT.get(CUR - year_offset)
    h2h_wt = ftf.H2H_YEAR_WEIGHT.get(CUR - year_offset, 0.0)
    row = {"Winner": winner, "Loser": loser, "Surface": surface, "Best of": best_of,
           "__wt": wt, "__h2h_wt": h2h_wt}
    for i, (w, l) in enumerate(sets, start=1):
        row[f"W{i}"], row[f"L{i}"] = w, l
    row.update(overrides)
    return row


# ── recency window (form/psych/clutch/streak) ───────────────────────────────
def test_form_counts_matches_inside_recency_window():
    rows = [_row(year_offset=0) for _ in range(4)]  # weight 3.0 x4 = 12 >= MIN_MATCHES(8)
    out = ftf.aggregate(rows)
    assert "tiafoe|f" in out["players"]
    assert out["players"]["tiafoe|f"]["form"] == 0.5  # won every match -> 100% -> +0.5 vs 50%


def test_form_ignores_matches_outside_recency_window():
    # year_offset=5 -> __wt is None (outside YEAR_WEIGHT), only __h2h_wt is set.
    rows = [_row(year_offset=5) for _ in range(10)]
    out = ftf.aggregate(rows)
    assert "tiafoe|f" not in out["players"]  # no recency-window matches at all


# ── H2H long window (the actual bug fix) ─────────────────────────────────────
def test_h2h_counts_meetings_outside_the_recency_window():
    # Old meetings (year_offset=3, e.g. 2023 relative to 2026) have __wt=None
    # (invisible to form) but __h2h_wt>0 (visible to H2H) — this is exactly
    # the Muchova/Zhang Wimbledon-2021 shape that was silently dropped before
    # the fix (MIN_H2H is a WEIGHTED threshold, so this needs enough weighted
    # meetings to clear it — old-year weights are intentionally small).
    rows = [_row(winner="Muchova K.", loser="Zhang S.", surface="Grass", year_offset=3)
            for _ in range(4)]
    out = ftf.aggregate(rows)
    assert out["players"] == {}  # too few matches for the (short) form window
    pair = out["h2h"]["muchova|k"]["zhang|s"]
    assert pair["n"] == round(ftf.H2H_YEAR_WEIGHT[CUR - 3] * 4, 1)
    assert pair["all"] == 0.5   # Muchova won 100% of these meetings -> +0.5 vs 50%


def test_h2h_ignores_meetings_beyond_even_the_long_window():
    # year_offset=10 -> not in H2H_YEAR_WEIGHT either -> __h2h_wt defaults 0.0.
    rows = [_row(winner="Muchova K.", loser="Zhang S.", year_offset=10)]
    out = ftf.aggregate(rows)
    assert out["h2h"] == {}


def test_h2h_combines_recent_and_old_meetings_recency_weighted():
    # Recent win for Muchova (h2h_w=3.0) + old loss for Muchova (h2h_w=0.3 at
    # offset=5) -> her H2H share should be positive but pulled down from 1.0
    # by the older loss (not simply averaged 50/50 — recency still dominates).
    recent_win = _row(winner="Muchova K.", loser="Zhang S.", year_offset=0)
    old_loss = _row(winner="Zhang S.", loser="Muchova K.", year_offset=5)
    out = ftf.aggregate([recent_win, old_loss])
    share = out["h2h"]["muchova|k"]["zhang|s"]["all"]
    assert 0 < share < 0.5  # positive (net favours Muchova) but not the full 1.0


# ── unchanged existing behaviour (regression guard) ──────────────────────────
def test_decider_and_tiebreak_signals_still_computed_within_recency_window():
    rows = [
        _row(sets=(("7", "6"), ("4", "6"), ("7", "6")), best_of=3, year_offset=0)
        for _ in range(6)
    ]
    out = ftf.aggregate(rows)
    p = out["players"]["tiafoe|f"]
    assert "decider" in p and "tb" in p


def test_min_h2h_threshold_still_applies():
    # A single meeting (n=weight of one row, well under MIN_H2H=2) must still
    # be dropped even though it's inside the window and h2h_wt > 0.
    rows = [_row(winner="Muchova K.", loser="Zhang S.", year_offset=6)]  # h2h_w=0.2 < MIN_H2H
    out = ftf.aggregate(rows)
    assert "muchova|k" not in out["h2h"]
