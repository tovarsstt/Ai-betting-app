"""Tests for the tennis comparative-profile nudges (H2H / form / psych / clutch)."""
import edge_api as e
from fetch_tennis_form import name_key

# Human names → keys derived through the SAME keyer the model uses, so fixtures
# can never drift from production keying.
HOME, AWAY = "Carlos Alcaraz", "Jannik Sinner"
HK, AK = e._tennis_key(HOME), e._tennis_key(AWAY)


def _set_form(players=None, h2h=None):
    e.TENNIS_FORM.clear()
    e.TENNIS_FORM.update({"players": players or {}, "h2h": h2h or {}})
    e.TENNIS_SERVE.clear()  # every test starts with a clean serve store too


def _set_serve(players=None):
    e.TENNIS_SERVE.clear()
    e.TENNIS_SERVE.update({"players": players or {}})


def test_tennis_key_matches_fetch_name_key():
    # Arrange / Act: both keyers must agree so the form file lines up with predict.
    fetch_key = "%s|%s" % name_key("Frances Tiafoe")
    # Assert
    assert e._tennis_key("Frances Tiafoe") == fetch_key == "tiafoe|f"
    assert e._tennis_key("Tiafoe F.") == "tiafoe|f"      # source-style name
    assert e._tennis_key("Madonna") is None              # single token → no key


def test_h2h_prefers_same_surface_over_overall():
    # Arrange: home owns hard H2H but is crushed on grass.
    _set_form(h2h={HK: {AK: {"all": 0.1, "Hard": 0.25, "Grass": -0.5}}})

    # Act
    grass, gdetail = e._tennis_aux_logit(HOME, AWAY, "Grass")
    hard, hdetail = e._tennis_aux_logit(HOME, AWAY, "Hard")

    # Assert: grass H2H pulls the nudge negative, hard pushes it positive.
    assert gdetail["h2h"] == -0.5 and grass < 0
    assert hdetail["h2h"] == 0.25 and hard > 0


def test_h2h_falls_back_to_overall_when_surface_missing():
    # Arrange: no Clay entry → must use the "all" share.
    _set_form(h2h={HK: {AK: {"all": 0.2, "Hard": 0.4}}})
    # Act
    _, detail = e._tennis_aux_logit(HOME, AWAY, "Clay")
    # Assert
    assert detail["h2h"] == 0.2


def test_differential_dim_skipped_when_one_player_missing_field():
    # Arrange: only home carries clutch fields → no clutch differential possible.
    _set_form(players={
        HK: {"form": 0.3, "decider": 0.8, "tb": 0.8},
        AK: {"form": 0.1},
    })
    # Act
    _, detail = e._tennis_aux_logit(HOME, AWAY, "Hard")
    # Assert
    assert "form_diff" in detail            # both have form
    assert "clutch_diff" not in detail      # only one has clutch → skipped


def test_aux_logit_is_capped():
    # Arrange: extreme, contradiction-free edges in home's favour.
    _set_form(
        players={
            HK: {"form": 0.5, "comeback": 1.0, "decider": 1.0, "tb": 1.0, "streak": 6},
            AK: {"form": -0.5, "comeback": 0.0, "decider": 0.0, "tb": 0.0, "streak": -6},
        },
        h2h={HK: {AK: {"all": 0.5}}},
    )
    # Act
    nudge, detail = e._tennis_aux_logit(HOME, AWAY, "Hard")
    # Assert: never exceeds the cap that protects a clear points favourite.
    assert nudge == e.TENNIS_AUX_CAP
    assert detail["aux_logit"] == e.TENNIS_AUX_CAP


def test_no_data_returns_zero_nudge():
    # Arrange: empty form store.
    _set_form()
    # Act
    nudge, detail = e._tennis_aux_logit(HOME, AWAY, "Hard")
    # Assert
    assert nudge == 0.0 and detail == {}


# ── Real ATP break-point stats enrich the clutch bucket ─────────────────────
def test_serve_stats_add_clutch_signal_with_no_form_clutch_fields():
    # Arrange: neither player carries decider/tb, but both carry ATP serve data.
    _set_form(players={HK: {"form": 0.0}, AK: {"form": 0.0}})
    _set_serve(players={
        HK: {"bp_save_pct": 0.70, "bp_convert_pct": 0.45},
        AK: {"bp_save_pct": 0.60, "bp_convert_pct": 0.40},
    })
    # Act
    nudge, detail = e._tennis_aux_logit(HOME, AWAY, "Hard")
    # Assert: home is better on both break-point dims -> positive clutch_diff.
    assert "clutch_diff" in detail
    assert detail["clutch_diff"] > 0
    assert nudge > 0


def test_serve_stats_combine_with_decider_tb_in_same_bucket():
    # Arrange: home leads on decider/tb, away leads on break points — averaged.
    _set_form(players={
        HK: {"form": 0.0, "decider": 0.8, "tb": 0.8},
        AK: {"form": 0.0, "decider": 0.2, "tb": 0.2},
    })
    _set_serve(players={
        HK: {"bp_save_pct": 0.50, "bp_convert_pct": 0.30},
        AK: {"bp_save_pct": 0.70, "bp_convert_pct": 0.50},
    })
    # Act
    _, detail = e._tennis_aux_logit(HOME, AWAY, "Hard")
    # Assert: 4 sub-signals averaged (decider +0.6, tb +0.6, bp_save -0.2, bp_convert -0.2)
    expected = round((0.6 + 0.6 - 0.2 - 0.2) / 4, 3)
    assert detail["clutch_diff"] == expected


def test_serve_stats_skipped_when_only_one_player_has_them():
    # Arrange: only home carries ATP serve data (e.g. away is WTA, no source yet).
    _set_form(players={HK: {"form": 0.0}, AK: {"form": 0.0}})
    _set_serve(players={HK: {"bp_save_pct": 0.70, "bp_convert_pct": 0.45}})
    # Act
    _, detail = e._tennis_aux_logit(HOME, AWAY, "Hard")
    # Assert: no clutch signal at all — never invent the missing side.
    assert "clutch_diff" not in detail
