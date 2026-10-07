"""
The prompt-formatting parser exists in both live frontends and must stay byte-identical: the
projector and the phones have to show a prompt the same way. The apps share no code, so this test
is the guard (same pattern as test_plot_geometry_copies.py).

It FAILS (never skips) when a file is missing. Run it from the repo root:
    PYTHONPATH=backend pytest tests/unit
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAYER = ROOT / "frontend" / "player" / "src" / "lib" / "promptMarkup.ts"
HOST = ROOT / "frontend" / "host" / "src" / "lib" / "promptMarkup.ts"
ADMIN = (
    ROOT / "frontend" / "admin" / "src" / "lib" / "promptMarkup.ts"
)  # the admin question editor shows prompts


def test_prompt_markup_copies_are_byte_identical():
    for path in (PLAYER, HOST, ADMIN):
        assert path.is_file(), (
            f"missing {path} (run from a full checkout, not the backend container)"
        )
    for other in (HOST, ADMIN):
        assert PLAYER.read_bytes() == other.read_bytes(), (
            f"{PLAYER.relative_to(ROOT)} and {other.relative_to(ROOT)} differ: "
            "edit all copies together (cp one over the others)"
        )
