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
ADMIN = (
    ROOT / "frontend" / "admin" / "src" / "lib" / "plotGeometry.ts"
)  # the admin question editor draws the plane too


def test_plot_geometry_copies_are_byte_identical():
    for path in (PLAYER, HOST, ADMIN):
        assert path.is_file(), (
            f"missing {path} (run from a full checkout, not the backend container)"
        )
    player = PLAYER.read_bytes()
    for other in (HOST, ADMIN):
        assert player == other.read_bytes(), (
            f"{PLAYER.relative_to(ROOT)} and {other.relative_to(ROOT)} differ: "
            "edit all copies together (cp one over the others)"
        )
