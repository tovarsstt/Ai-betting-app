#!/usr/bin/env python3
"""Tests for lint_portfolio — cross-slip exposure + same-game correlation gates.

Ground truth these encode (from the user's settled record, 2026-07-03 batch):
  - Jodar leak: one leg cloned into 3 tennis slips killed all 3 at once.
  - Suiza-Argelia leak: BTTS + totals + corners stacked in ONE match died twice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from slip_linter import lint_portfolio


def _slip(*legs):
    return {"legs": [{"decimal": d, "selection": s, **extra}
                     for d, s, extra in legs]}


def test_flags_leg_cloned_across_slips():
    # Jodar pattern: same selection in 3 slips = 1 bet bought 3 times.
    slips = [
        _slip((1.31, "Jodar ML", {}), (1.21, "Osaka ML", {})),
        _slip((1.31, "Jodar ML", {}), (1.26, "Sabalenka ML", {})),
        _slip((1.31, "Jodar ML", {}), (1.11, "Gauff ML", {})),
    ]
    result = lint_portfolio(slips)
    shared = [w for w in result["warnings"] if "Jodar ML" in w and "3 slips" in w]
    assert shared, f"expected shared-leg warning, got {result['warnings']}"


def test_no_warning_when_slips_independent():
    slips = [
        _slip((1.87, "Colombia U2.5", {}), (1.89, "USA-Belgium U2.75", {})),
        _slip((1.92, "Brazil U2.75", {}), (1.95, "Portugal-Spain U2.5", {})),
    ]
    result = lint_portfolio(slips)
    assert not [w for w in result["warnings"] if "slips" in w]


def test_flags_correlated_same_match_stack():
    # Suiza-Argelia pattern: 3 sub-markets of one match inside one slip.
    slips = [_slip(
        (1.85, "BTTS Yes", {"match": "Suiza v Argelia"}),
        (1.60, "Over 2.5", {"match": "Suiza v Argelia"}),
        (1.67, "Corners O4.5", {"match": "Suiza v Argelia"}),
    )]
    result = lint_portfolio(slips)
    corr = [w for w in result["warnings"] if "correlated" in w.lower()]
    assert corr, f"expected correlation warning, got {result['warnings']}"


def test_two_same_match_legs_allowed():
    # 2 legs same match is a normal same-game double — only 3+ gets flagged.
    slips = [_slip(
        (1.32, "Espana ML", {"match": "Espana v Austria"}),
        (1.49, "Over 2.25", {"match": "Espana v Austria"}),
    )]
    result = lint_portfolio(slips)
    assert not [w for w in result["warnings"] if "correlated" in w.lower()]


def test_joint_exposure_reported():
    # Shared-leg death probability: if the shared leg dies, ALL listed slips die.
    slips = [
        _slip((1.31, "Jodar ML", {}), (1.21, "Osaka ML", {})),
        _slip((1.31, "Jodar ML", {}), (1.26, "Sabalenka ML", {})),
    ]
    result = lint_portfolio(slips)
    assert result["shared_legs"] == {"Jodar ML": [0, 1]}


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"  FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
