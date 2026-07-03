#!/usr/bin/env python3
"""Tests for analyze_slips leg-count fix + ticket_type tagging.

The leg-count bug: a "7 Multi tramo" ticket whose legs are same-game blocks
("Multi apuesta del mismo partido (2/(3") was tagged with the LAST inner block's
count (3), not the ticket's own 7 — inflating the 2-3-leg band with big-combo wins.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import analyze_slips as az

NESTED_7LEG = """7 Multi tramo
Ganador
Multi apuesta del mismo partido (2 1,59 Inglaterra - Congo Democrático
Inglaterra 1x2 (90' + tiempo agregado)
Multi apuesta del mismo partido (2 2,61 Bélgica - Senegal
Sí Ambos equipos marcan (90' + tiempo agregado)
Multi apuesta del mismo partido (3 3,00 Estados Unidos - Bosnia y Herzegovina
Estados Unidos 1x2 (90' + tiempo agregado)
Cuotas 12,41 Apuesta 9.00000000 Pago 111.68158119
"""

PURE_SGM = """Multi apuesta del mismo partido (3
Perdida
Suiza - Argelia
Sí Ambos equipos marcan (90' + tiempo agregado)
más de 2.5 Totales asiáticos (90' + tiempo agregado)
más de 4.5 Tiros de esquina Suiza
Cuotas 4,08 Apuesta 20.00000000 Pago 0.00000000
"""

TENNIS_STACK = """8 Multi tramo
Ganador
Bergs, Zizou Ganador 1,48
Swiatek, Iga Ganador 1,27
Lorenzo Sonego (1.5) Hándicap de Set 1,45
Cuotas 12,15 Apuesta 5.00000000 Pago 60.76335141
"""

SINGLE = """más de 4.5 Tiros de esquina Suiza
Perdida
Cuotas 1,67 Apuesta 20.00000000 Pago 0.00000000
"""


def _parse_text(text: str) -> list:
    return az.parse(text)


def test_nested_ticket_uses_outer_leg_count():
    rows = _parse_text(NESTED_7LEG)
    assert rows[0]["legs"] == 7, f"nested combo must be 7 legs, got {rows[0]['legs']}"


def test_pure_sgm_uses_its_own_count():
    rows = _parse_text(PURE_SGM)
    assert rows[0]["legs"] == 3


def test_single_stays_single():
    rows = _parse_text(SINGLE)
    assert rows[0]["legs"] == 1


def test_type_tennis_stack():
    assert az.ticket_type(TENNIS_STACK) == "tennis stack"


def test_type_soccer_same_game():
    assert az.ticket_type(PURE_SGM) == "soccer same-game (1 match)"


def test_type_soccer_cross_match():
    assert az.ticket_type(NESTED_7LEG) == "soccer cross-match combo"


def test_type_unknown_when_no_markers():
    assert az.ticket_type("Cuotas 2,07 Apuesta 10.00 Pago 0.00") == "unknown"


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
