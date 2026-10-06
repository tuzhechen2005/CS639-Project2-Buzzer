"""
Every allowed colour pair meets WCAG 2.1 AA in both themes (docs/plans/t9-theming.md,
"Allowed pairs"): 4.5:1 for text, 3:1 for graphics and control boundaries (1.4.11).

The values are read from frontend/host/src/theme/tokens.css (the three copies are identical;
test_theme_copies.py). `:root` holds the light theme; the `[data-theme="dark"]` block redefines
only the tokens that differ, so the dark theme inherits the rest from `:root`.

A pair the apps need that is not listed here is not allowed until it is added to the spec's list
and to this test, in the same commit. Run from the repo root:
    PYTHONPATH=backend pytest tests/unit
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TOKENS = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "host"
    / "src"
    / "theme"
    / "tokens.css"
)

RGB = tuple[float, float, float]


def _block(css: str, selector: str) -> dict[str, RGB]:
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, re.S)
    assert match, f"no {selector} block in {TOKENS}"
    return {
        name: (float(r), float(g), float(b))
        for name, r, g, b in re.findall(
            r"--([\w-]+):\s*(\d+)\s+(\d+)\s+(\d+)\s*;", match.group(1)
        )
    }


def load_themes() -> dict[str, dict[str, RGB]]:
    assert TOKENS.is_file(), f"missing {TOKENS}"
    css = TOKENS.read_text()
    light = _block(css, ":root")
    dark = {**light, **_block(css, '[data-theme="dark"]')}
    return {"light": light, "dark": dark}


def luminance(rgb: RGB) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: RGB, b: RGB) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def pressed(rgb: RGB) -> RGB:
    """`filter: brightness(0.9)`: every sRGB channel times 0.9 (text and fill alike)."""
    return tuple(c * 0.9 for c in rgb)  # type: ignore[return-value]


TEXT = 4.5
NON_TEXT = 3.0
SURFACES = ("page", "surface", "surface-raised")
OPTIONS = [f"option-{i}" for i in range(1, 9)]

# (foreground, background, minimum, pressed?) — the spec's "Allowed pairs", in its order.
PAIRS: list[tuple[str, str, float, bool]] = []
for fg in (
    "fg",
    "fg-muted",
    "fg-subtle",
    "accent-text",
    "success-text",
    "warning-text",
    "danger-text",
):
    PAIRS += [(fg, bg, TEXT, False) for bg in SURFACES]
PAIRS += [
    ("on-accent", "accent", TEXT, False),
    ("on-accent", "accent-hover", TEXT, False),
]
for status in ("success", "warning", "danger"):
    PAIRS += [
        (f"on-{status}", status, TEXT, False),
        (f"on-{status}", status, TEXT, True),
    ]
for option in OPTIONS:
    PAIRS += [
        (f"on-{option}", option, TEXT, False),
        (f"on-{option}", option, TEXT, True),
    ]
PAIRS += [
    ("fg-muted", "page", TEXT, False),  # canvas tick and band labels
    ("fg-subtle", "page", TEXT, False),  # canvas axes and bands, held to text contrast
    ("on-accent", "accent", TEXT, False),  # host plot dot counts
]
for name, text in (
    ("success", "success-text"),
    ("warning", "warning-text"),
    ("danger", "danger-text"),
    ("accent", "accent-text"),
):
    PAIRS += [(fg, f"{name}-subtle", TEXT, False) for fg in ("fg", "fg-muted", text)]
PAIRS += [("line-strong", bg, NON_TEXT, False) for bg in SURFACES]
PAIRS += [("focus", "page", NON_TEXT, False), ("focus", "surface", NON_TEXT, False)]
PAIRS += [
    (fill, "surface-raised", NON_TEXT, False)
    for fill in ("success", "warning", "danger")
]
PAIRS += [("accent", "surface", NON_TEXT, False), ("accent", "page", NON_TEXT, False)]
PAIRS += [
    (mark, "page", NON_TEXT, False)
    for mark in ("plot-overlay", "plot-point", "success")
]
PAIRS += [
    (fill, "surface-raised", NON_TEXT, False)
    for fill in ("accent", "success", "danger", "fg-subtle")
]
PAIRS += [
    ("on-accent", "accent", TEXT, False),
    ("on-success", "success", TEXT, False),
    ("surface", "fg-subtle", TEXT, False),
]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_allowed_pair_meets_aa(theme: str):
    tokens = load_themes()[theme]
    failures = []
    for fg, bg, minimum, is_pressed in PAIRS:
        assert fg in tokens and bg in tokens, f"unknown token in pair {fg} on {bg}"
        a, b = tokens[fg], tokens[bg]
        if is_pressed:
            a, b = pressed(a), pressed(b)
        ratio = contrast(a, b)
        if ratio < minimum:
            state = " (pressed)" if is_pressed else ""
            failures.append(f"{fg} on {bg}{state}: {ratio:.2f} < {minimum}")
    assert not failures, f"{theme} theme fails AA:\n" + "\n".join(failures)


def test_every_token_has_a_value_in_both_themes():
    themes = load_themes()
    assert set(themes["light"]) == set(themes["dark"])
    for name in ("page", "fg", "accent", "qr", *OPTIONS):
        assert name in themes["light"], name


def test_the_contrast_formula():
    white, black = (255.0, 255.0, 255.0), (0.0, 0.0, 0.0)
    assert contrast(white, black) == pytest.approx(21.0)
    assert contrast(white, white) == pytest.approx(1.0)
    # A known pair: #767676 on white is the classic 4.54:1.
    assert contrast((118.0, 118.0, 118.0), white) == pytest.approx(4.54, abs=0.01)
