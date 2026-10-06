"""
The plot_point geometry module exists in both frontends and must stay byte-identical
(docs/plans/t7-plot-the-point.md, P5): the phone and the projector have to agree on where every
point is. The apps share no code, so this test is the guard.

It FAILS (never skips) when a file is missing. Run it from the repo root, where both frontends
are present (the backend container mounts only backend/):
    PYTHONPATH=backend pytest tests/unit
CI runs no pytest job, so the merge request records a local run.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAYER = ROOT / "frontend" / "player" / "src" / "lib" / "plotGeometry.ts"
HOST = ROOT / "frontend" / "host" / "src" / "lib" / "plotGeometry.ts"


def test_plot_geometry_copies_are_byte_identical():
    for path in (PLAYER, HOST):
        assert path.is_file(), f"missing {path} (run from a full checkout, not the backend container)"
    player, host = PLAYER.read_bytes(), HOST.read_bytes()
    assert player == host, (
        f"{PLAYER.relative_to(ROOT)} and {HOST.relative_to(ROOT)} differ: "
        "edit both copies together (cp one over the other)"
    )
