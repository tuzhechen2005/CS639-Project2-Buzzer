"""
Everything theme-related lives in frontend/<app>/src/theme/ and must be byte-identical in the
host, player and admin apps (docs/plans/t9-theming.md, Decision 3): one palette for the product.
The apps share no code, so this test is the guard (same pattern as test_plot_geometry_copies.py).

It FAILS (never skips) on a missing file, an extra file or a difference. Run it from the repo root:
    PYTHONPATH=backend pytest tests/unit
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ("host", "player", "admin")
EXPECTED = {"tokens.css", "colors.js", "colors.d.ts", "theme.ts"}


def _theme_dir(app: str) -> Path:
    return ROOT / "frontend" / app / "src" / "theme"


def _files(app: str) -> dict[str, bytes]:
    folder = _theme_dir(app)
    assert folder.is_dir(), f"missing {folder} (run from a full checkout)"
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_theme_folder_has_the_expected_files_in_every_app():
    for app in APPS:
        names = set(_files(app))
        missing = EXPECTED - names
        assert not missing, f"frontend/{app}/src/theme/ is missing {sorted(missing)}"


def test_theme_folders_are_byte_identical():
    host = _files("host")
    for app in APPS[1:]:
        other = _files(app)
        assert set(other) == set(host), (
            f"frontend/{app}/src/theme/ has files {sorted(other)}, host has {sorted(host)}: "
            "the three theme folders must hold the same files"
        )
        for name, data in host.items():
            assert other[name] == data, (
                f"frontend/{app}/src/theme/{name} differs from the host copy: "
                "edit all three together (copy one over the others)"
            )
