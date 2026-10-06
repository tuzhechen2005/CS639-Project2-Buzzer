"""
Every interactive element in the three frontends shows the shared focus ring
(docs/plans/t9-theming.md, "Mapping rules", Focus): WCAG 2.4.7 asks for a visible focus state,
and the browser's default outline is faint on the coloured answer buttons.

This scans each app's src/**/*.tsx (skipping src/theme/) for `button`, `a`, `input`, `select`,
`textarea`, `Link` and `NavLink` tags and fails with file:line when an opening tag has no
`focus-visible:ring` / `focus:ring`. The tag is read with braces balanced, so the `>` of an
`=>` inside `onClick={() => ...}` does not end it. A class built by a helper counts when the tag
names the helper (`className={tabClass}`) and the helper's string has the ring; known helpers
are listed in HELPERS. Skipped: inputs hidden with `className="hidden"` (file inputs opened by a
labelled button) and `sr-only` elements. Run from the repo root:
    PYTHONPATH=backend pytest tests/unit
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ("host", "player", "admin")
TAGS = re.compile(r"<(button|a|input|select|textarea|Link|NavLink)\b")
RING = re.compile(r"focus(?:-visible)?:ring")
# Class helpers whose returned string carries the ring; checked in test_helpers_carry_the_ring.
HELPERS = {
    "tabClass": "host/src/pages/course/CourseLayout.tsx",
    "linkClass": "admin/src/App.tsx",
    "SELECT": "host/src/pages/course/PlotPointEditor.tsx",
}


def opening_tag(text: str, start: int) -> str:
    """The attributes of the tag starting at `start`, up to its closing `>` outside braces."""
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth == 0:
            return text[start:i]
    return text[start:]


def has_focus_ring(attrs: str) -> bool:
    if RING.search(attrs):
        return True
    if any(re.search(rf"\b{name}\b", attrs) for name in HELPERS):
        return True
    return 'className="hidden"' in attrs or "sr-only" in attrs


def find_missing(frontend: Path) -> list[str]:
    problems: list[str] = []
    for app in APPS:
        src = frontend / app / "src"
        assert src.is_dir(), f"missing {src} (run from a full checkout)"
        for path in sorted(src.rglob("*.tsx")):
            if (src / "theme") in path.parents:
                continue
            text = path.read_text()
            for match in TAGS.finditer(text):
                if not has_focus_ring(opening_tag(text, match.end())):
                    line = text.count("\n", 0, match.start()) + 1
                    problems.append(
                        f"{path.relative_to(frontend.parent)}:{line}: <{match.group(1)}>"
                    )
    return problems


def test_every_interactive_element_has_the_focus_ring():
    problems = find_missing(ROOT / "frontend")
    assert not problems, (
        f"{len(problems)} interactive element(s) without the focus ring; add "
        "'focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 "
        "ring-offset-page' (docs/plans/t9-theming.md):\n" + "\n".join(problems)
    )


def test_helpers_carry_the_ring():
    for name, rel in HELPERS.items():
        text = (ROOT / "frontend" / rel).read_text()
        match = re.search(rf"\b{name}\b\s*=.*?;\n", text, re.S)
        assert match, f"{name} not defined in {rel}"
        assert RING.search(match.group(0)), f"{name} in {rel} has no focus ring"


def test_the_scanner():
    text = """<button onClick={() => go()} className="px-4">Go</button>"""
    assert not has_focus_ring(opening_tag(text, len("<button")))
    text = (
        """<button onClick={() => go()} className="focus-visible:ring-2">Go</button>"""
    )
    assert has_focus_ring(opening_tag(text, len("<button")))
    assert has_focus_ring('<input className="hidden" type="file"')
    assert has_focus_ring('<NavLink to="x" className={tabClass}')
    assert not TAGS.search("<abbr>") and not TAGS.search("<Label>")
    assert TAGS.search("<a href='x'>") and TAGS.search("<Link to='/'>")
