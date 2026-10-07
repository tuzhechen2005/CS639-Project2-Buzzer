"""
No hard-coded colours in the three frontends (docs/plans/t9-theming.md, "test_no_raw_colours").

Every colour must come from the theme's tokens (src/theme/), so both themes cover every screen.
This scans each app's src/**/*.{ts,tsx,css} and index.html, skipping *.test.ts and the src/theme/
folder (the one place colour values are written), and fails with file:line on:
  - a raw Tailwind palette class (bg-slate-800, hover:text-indigo-400, border-amber-500/40,
    text-white, ...), with any variant prefix and opacity suffix;
  - an arbitrary colour value (bg-[#123456], text-[rgb(...)], ...);
  - a colour literal: a hex colour after a quote, backtick or colon (as in `background: #0f172a`),
    rgb( / rgba( / hsl( / hsla(, or the named colours 'white' / 'black' as string literals.
There are no exceptions. It FAILS (never skips) when an app folder is missing. Run from the repo
root:
    PYTHONPATH=backend pytest tests/unit
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ("host", "player", "admin")

_PALETTE = (
    "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|"
    "blue|indigo|violet|purple|fuchsia|pink|rose"
)
_UTILITY = (
    "bg|text|border|border-[trblxy]|ring|ring-offset|divide|outline|fill|stroke|from|via|to|"
    "placeholder|shadow|decoration|caret|accent"
)
# Variant prefixes: hover:, group-hover:, md:, [&:not(:active)]:, ... (any number of them).
_VARIANTS = r"(?:(?:[a-z0-9-]+|\[[^\]\s]+\]):)*"
RAW_CLASS = re.compile(
    rf"(?<![\w-]){_VARIANTS}(?:{_UTILITY})-(?:(?:{_PALETTE})-\d{{2,3}}|white|black)(?:/\d+)?(?![\w-])"
)
ARBITRARY = re.compile(r"-\[(?:#|rgba?\(|hsla?\()")
LITERALS = (
    re.compile(r"""['"`:]\s*#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b"""),
    re.compile(r"\b(?:rgba?|hsla?)\("),
    re.compile(r"""(['"`])(?:white|black)\1"""),
)


def scanned_files(frontend: Path) -> list[Path]:
    files: list[Path] = []
    for app in APPS:
        root = frontend / app
        assert (root / "src").is_dir(), (
            f"missing {root / 'src'} (run from a full checkout)"
        )
        for path in sorted((root / "src").rglob("*")):
            if path.suffix not in (".ts", ".tsx", ".css") or path.name.endswith(
                ".test.ts"
            ):
                continue
            if (root / "src" / "theme") in path.parents:
                continue
            files.append(path)
        files.append(root / "index.html")
    return files


def find_violations(frontend: Path) -> list[str]:
    """Every hard-coded colour under `frontend`, as 'file:line: match' strings."""
    problems: list[str] = []
    for path in scanned_files(frontend):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            found = [m.group(0) for m in RAW_CLASS.finditer(line)]
            found += [m.group(0) for m in ARBITRARY.finditer(line)]
            for pattern in LITERALS:
                found += [m.group(0).strip() for m in pattern.finditer(line)]
            for match in found:
                problems.append(
                    f"{path.relative_to(frontend.parent)}:{number}: {match}"
                )
    return problems


def test_no_hard_coded_colours_in_the_frontends():
    problems = find_violations(ROOT / "frontend")
    assert not problems, (
        f"{len(problems)} hard-coded colour(s); use a token from src/theme/ instead "
        "(docs/plans/t9-theming.md):\n" + "\n".join(problems[:60])
    )


def test_the_rules_catch_what_they_should():
    # The patterns themselves, so a regex slip cannot make the main test pass vacuously.
    must_match = [
        'className="bg-slate-800"',
        "hover:text-indigo-400",
        "group-hover:text-slate-200",
        "border-amber-500/40",
        "text-white",
        "hover:[&:not(:active)]:bg-red-500",
        "placeholder-slate-400",
        "accent-indigo-500",
    ]
    for text in must_match:
        assert RAW_CLASS.search(text), text
    assert ARBITRARY.search("bg-[#0f172a]") and ARBITRARY.search("text-[rgb(1,2,3)]")
    for text in (
        "background: #0f172a;",
        "color: '#fff'",
        "fill: rgb(0 0 0)",
        "c = 'white'",
    ):
        assert any(p.search(text) for p in LITERALS), text
    must_not_match = [
        "bg-surface text-fg-muted border-line-strong",
        "text-on-accent bg-option-3 ring-focus",
        "accent-accent",
        "&#039;",
        "white-space: nowrap",
        "text-whitespace",
        "bg-white-ish",
    ]
    for text in must_not_match:
        assert not RAW_CLASS.search(text) and not ARBITRARY.search(text), text
        assert not any(p.search(text) for p in LITERALS), text
