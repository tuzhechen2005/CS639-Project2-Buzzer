"""
Question-type registry: everything that differs between question types, in one place.

Each type is one `QuestionType` handler (below). The module-level functions at the bottom
(`score_answer`, `answer_reveal`, `distribution_keys_for`, `validate_definition`,
`validate_answer`, `normalize_answer`, `accept_answer`, `payload_extras`, `known_types`,
`label_for`) are the only entry points
the rest of the backend uses; they add the behaviour that is the same for every type
(empty answers, COMPLETENESS grading, unknown types).

Handlers are pure: no database, no Redis, and no imports of routers or the gateway.
They take a *question-like* value: any object with the attributes `type`, `grading_type`,
`config`, `answer_data` and `points_value`. The ORM `Question` qualifies; code that only has
raw rows builds a `QuestionSpec`.

Adding a type = writing one handler and registering it in `_TYPES`.
Design: docs/plans/t7-numeric-estimate.md (A1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from rapidfuzz.distance import Levenshtein

from ..schemas.game import ScoreResult


class QuestionLike(Protocol):
    type: str
    grading_type: str
    config: dict
    answer_data: dict
    points_value: float


@dataclass
class QuestionSpec:
    """A question-like built from raw rows (the summary queries select columns, not
    ORM objects)."""

    type: str
    grading_type: str
    config: dict
    answer_data: dict
    points_value: float


def _unchanged(q: Any, answer_data: Any) -> Any:
    return answer_data


@dataclass(frozen=True)
class QuestionType:
    key: str
    label: str
    # Raise ValueError(message) if config / answer_data are structurally wrong.
    validate_definition: Callable[[Any], None]
    # Return an error message for an unacceptable submitted answer, else None.
    validate_answer: Callable[[Any, Any], str | None]
    # ACCURACY scoring of a non-empty answer.
    score: Callable[[Any, dict], ScoreResult]
    # Client-safe correct-answer facts for an ACCURACY question (a new dict).
    reveal: Callable[[Any], dict]
    # Distribution keys to count for an answer (may be empty or several).
    distribution_keys: Callable[[Any, dict], list[str]]
    # Extra client-safe keys for the new_question payload.
    payload_extras: Callable[[Any], dict]
    # Optional: the answer to score, bucket and store (e.g. a click snapped to its grid
    # cell). Pure, never raises, only sees answers validate_answer accepted.
    normalize_answer: Callable[[Any, Any], Any] = _unchanged


def _no_answer_check(q: Any, answer_data: Any) -> str | None:
    return None


def _no_extras(q: Any) -> dict:
    return {}


def _zero() -> ScoreResult:
    return ScoreResult(points_awarded=0, is_correct=False)


def _opts(q: Any) -> Any:
    return q.config.get("options") if isinstance(q.config, dict) else None


def _answer_data(q: Any) -> dict:
    return q.answer_data if isinstance(q.answer_data, dict) else {}


# ---------------------------------------------------------------------------
# multiple_choice
# ---------------------------------------------------------------------------


def _mc_validate_definition(q: Any) -> None:
    opts = _opts(q)
    if not isinstance(opts, list) or len(opts) < 2:
        raise ValueError(
            "multiple_choice config must have 'options' list with at least 2 items"
        )
    if q.grading_type == "ACCURACY":
        pts = _answer_data(q).get("answer_points")
        if not isinstance(pts, list) or len(pts) != len(opts):
            raise ValueError(
                "ACCURACY multiple_choice answer_data must have 'answer_points' list matching options length"
            )
        if any(not isinstance(p, (int, float)) or p < 0 for p in pts):
            raise ValueError("answer_points values must be non-negative numbers")


def _mc_score(q: Any, answer_data: dict) -> ScoreResult:
    selected = answer_data.get("selectedIndex")
    if selected is None:
        return _zero()
    pts_list: list[float] = _answer_data(q).get("answer_points", [])
    if not (0 <= selected < len(pts_list)):
        return _zero()
    points = pts_list[selected]
    return ScoreResult(points_awarded=points, is_correct=(points == q.points_value))


def _mc_reveal(q: Any) -> dict:
    pts: list = _answer_data(q).get("answer_points", [])
    correct = [i for i, p in enumerate(pts) if p >= q.points_value]
    return {"type": "multiple_choice", "correctIndices": correct}


def _mc_keys(q: Any, answer_data: dict) -> list[str]:
    idx = answer_data.get("selectedIndex")
    return [str(idx)] if idx is not None else []


# ---------------------------------------------------------------------------
# true_false
# ---------------------------------------------------------------------------


def _tf_validate_definition(q: Any) -> None:
    if q.grading_type != "ACCURACY":
        return
    pts = _answer_data(q).get("answer_points")
    if not isinstance(pts, dict) or set(pts.keys()) != {"true", "false"}:
        raise ValueError(
            "ACCURACY true_false answer_data must have 'answer_points' with 'true' and 'false' keys"
        )


def _tf_score(q: Any, answer_data: dict) -> ScoreResult:
    selected = answer_data.get("selectedValue")
    if selected is None:
        return _zero()
    pts_map: dict = _answer_data(q).get("answer_points", {})
    key = "true" if selected else "false"
    points = pts_map.get(key, 0)
    return ScoreResult(points_awarded=points, is_correct=(points == q.points_value))


def _tf_reveal(q: Any) -> dict:
    pts_map: dict = _answer_data(q).get("answer_points", {})
    return {
        "type": "true_false",
        "correctValue": pts_map.get("true", 0) >= q.points_value,
    }


def _tf_keys(q: Any, answer_data: dict) -> list[str]:
    val = answer_data.get("selectedValue")
    if val is None:
        return []
    return ["true" if val else "false"]


# ---------------------------------------------------------------------------
# fill_in_the_blank
# ---------------------------------------------------------------------------


def _normalise_text(raw: Any) -> str:
    """Lowercase and collapse all internal whitespace. Used for scoring and for the
    distribution key, so live charts, the game-over summary and the report agree."""
    return " ".join((raw or "").lower().split())


def _fitb_validate_definition(q: Any) -> None:
    if q.grading_type != "ACCURACY":
        return
    data = _answer_data(q)
    answers = data.get("acceptedAnswers")
    if not isinstance(answers, list) or len(answers) == 0:
        raise ValueError(
            "ACCURACY fill_in_the_blank answer_data must have 'acceptedAnswers' list with at least one item"
        )
    if any(not isinstance(a, str) or not a.strip() for a in answers):
        raise ValueError("acceptedAnswers entries must be non-empty strings")
    pts = data.get("answerPoints")
    if not isinstance(pts, list) or len(pts) != len(answers):
        raise ValueError(
            "ACCURACY fill_in_the_blank answer_data must have 'answerPoints' list matching acceptedAnswers length"
        )
    if any(not isinstance(p, (int, float)) or p < 0 for p in pts):
        raise ValueError("answerPoints values must be non-negative numbers")
    edit_dist = data.get("editDistance", 0)
    if not isinstance(edit_dist, int) or edit_dist < 0:
        raise ValueError("editDistance must be a non-negative integer")


def _fitb_score(q: Any, answer_data: dict) -> ScoreResult:
    text = _normalise_text(answer_data.get("text"))
    if not text:
        return _zero()
    data = _answer_data(q)
    accepted = [_normalise_text(a) for a in data.get("acceptedAnswers", [])]
    answer_pts: list[float] = data.get("answerPoints", [])
    max_dist = int(data.get("editDistance", 0))
    best: float = 0.0
    for i, a in enumerate(accepted):
        if Levenshtein.distance(text, a) <= max_dist:
            pts = answer_pts[i] if i < len(answer_pts) else q.points_value
            best = max(best, pts)
    return ScoreResult(points_awarded=best, is_correct=(best >= q.points_value))


def _fitb_reveal(q: Any) -> dict:
    data = _answer_data(q)
    return {
        "type": "fill_in_the_blank",
        "acceptedAnswers": data.get("acceptedAnswers", []),
        "editDistance": data.get("editDistance", 0),
    }


def _fitb_keys(q: Any, answer_data: dict) -> list[str]:
    text = _normalise_text(answer_data.get("text"))
    return [text] if text else []


def _fitb_extras(q: Any) -> dict:
    return {"editDistance": _answer_data(q).get("editDistance", 0)}


# ---------------------------------------------------------------------------
# multi_select
# ---------------------------------------------------------------------------


def _ms_validate_definition(q: Any) -> None:
    opts = _opts(q)
    if not isinstance(opts, list) or len(opts) < 2:
        raise ValueError(
            "multi_select config must have 'options' list with at least 2 items"
        )
    if q.grading_type == "ACCURACY":
        pts = _answer_data(q).get("answer_points")
        if not isinstance(pts, list) or len(pts) != len(opts):
            raise ValueError(
                "ACCURACY multi_select answer_data must have 'answer_points' list matching options length"
            )
        if any(not isinstance(p, (int, float)) for p in pts):
            raise ValueError("answer_points values must be numbers")


def _ms_validate_answer(q: Any, answer_data: Any) -> str | None:
    indices = (
        answer_data.get("selectedIndices") if isinstance(answer_data, dict) else None
    )
    if not isinstance(indices, list) or not all(isinstance(i, int) for i in indices):
        return "multi_select answer must include selectedIndices as a list of integers"
    num_opts = len(_opts(q) or [])
    if any(not (0 <= i < num_opts) for i in indices):
        return "selectedIndices contains an out-of-bounds index"
    return None


def _ms_score(q: Any, answer_data: dict) -> ScoreResult:
    selected = answer_data.get("selectedIndices")
    if not isinstance(selected, list):
        return _zero()
    pts_list: list[float] = _answer_data(q).get("answer_points", [])
    raw = sum(
        pts_list[i] for i in selected if isinstance(i, int) and 0 <= i < len(pts_list)
    )
    score = max(0.0, raw)
    return ScoreResult(
        points_awarded=score,
        is_correct=(score >= q.points_value and q.points_value > 0),
    )


def _ms_reveal(q: Any) -> dict:
    return {
        "type": "multi_select",
        "answerPoints": _answer_data(q).get("answer_points", []),
    }


def _ms_keys(q: Any, answer_data: dict) -> list[str]:
    indices = answer_data.get("selectedIndices")
    if not isinstance(indices, list):
        return []
    return [str(i) for i in indices if isinstance(i, int)]


# ---------------------------------------------------------------------------
# numeric_estimate
# ---------------------------------------------------------------------------
# A guess scored by banded tolerance around a hidden target (docs/plans/t7-numeric-estimate.md).
# answer_data (ACCURACY): {"target": n, "mode": "relative"|"absolute",
#                          "bands": [{"within": w, "points": p}, ...]}
# For "relative", `within` is a percentage; for "absolute" it is in the question's units.

_NUMERIC_LIMIT = 1e15
_MAX_BANDS = 5


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _in_range(v: Any) -> bool:
    """A JSON number within +-1e15. Compares first (valid for arbitrarily large ints, so no
    OverflowError); NaN fails every comparison and infinities fall outside the range."""
    return _is_number(v) and -_NUMERIC_LIMIT <= v <= _NUMERIC_LIMIT


def _finite_positive(v: Any) -> bool:
    return _is_number(v) and 0 < v <= _NUMERIC_LIMIT


def _numeric_validate_definition(q: Any) -> None:
    config = q.config if isinstance(q.config, dict) else {}
    if "unit" in config:
        unit = config["unit"]
        if not isinstance(unit, str) or not unit or len(unit) > 20:
            raise ValueError("unit must be a non-empty string of at most 20 characters")
    if q.grading_type != "ACCURACY":
        return
    data = _answer_data(q)
    target = data.get("target")
    if not _in_range(target):
        raise ValueError(
            "numeric_estimate target must be a finite number with absolute value at most 1e15"
        )
    mode = data.get("mode")
    if mode not in ("relative", "absolute"):
        raise ValueError("numeric_estimate mode must be 'relative' or 'absolute'")
    if mode == "relative" and target == 0:
        raise ValueError("relative mode needs a non-zero target")
    bands = data.get("bands")
    if not isinstance(bands, list) or not 1 <= len(bands) <= _MAX_BANDS:
        raise ValueError("bands must be a list of 1 to 5 items")
    for band in bands:
        if not (
            isinstance(band, dict)
            and _finite_positive(band.get("within"))
            and _finite_positive(band.get("points"))
        ):
            raise ValueError("each band needs numeric within > 0 and points > 0")
    withins = [b["within"] for b in bands]
    points = [b["points"] for b in bands]
    if any(b <= a for a, b in zip(withins, withins[1:])):
        raise ValueError("band within values must strictly increase")
    if any(b >= a for a, b in zip(points, points[1:])):
        raise ValueError("band points must strictly decrease")
    if not math.isclose(float(q.points_value), float(points[0]), abs_tol=1e-9):
        raise ValueError("points_value must equal the first band's points")


def _numeric_validate_answer(q: Any, answer_data: Any) -> str | None:
    if isinstance(answer_data, dict) and _in_range(answer_data.get("value")):
        return None
    return "numeric_estimate answer must include a finite numeric value"


def _numeric_band_index(q: Any, answer_data: dict) -> int | None:
    """Index of the first band the guess falls in, or None for a miss (also for a value
    that is not a usable number: never raises)."""
    value = answer_data.get("value")
    data = _answer_data(q)
    if not _in_range(value) or not _in_range(data.get("target")):
        return None
    target = data["target"]
    error = abs(value - target)
    if data.get("mode") == "relative":
        if target == 0:
            return None
        error = error / abs(target) * 100
    for i, band in enumerate(data.get("bands", [])):
        within = band.get("within") if isinstance(band, dict) else None
        if _is_number(within) and error <= within + 1e-9 * max(1.0, within):
            return i
    return None


def _numeric_score(q: Any, answer_data: dict) -> ScoreResult:
    index = _numeric_band_index(q, answer_data)
    if index is None:
        return _zero()
    points = _answer_data(q)["bands"][index]["points"]
    return ScoreResult(points_awarded=points, is_correct=(index == 0))


def _numeric_reveal(q: Any) -> dict:
    data = _answer_data(q)
    return {
        "type": "numeric_estimate",
        "target": data.get("target"),
        "mode": data.get("mode"),
        "bands": [
            {"within": b.get("within"), "points": b.get("points")}
            for b in data.get("bands", [])
            if isinstance(b, dict)
        ],
    }


def _numeric_keys(q: Any, answer_data: dict) -> list[str]:
    if q.grading_type != "ACCURACY":
        return []
    index = _numeric_band_index(q, answer_data)
    return ["miss"] if index is None else [str(index)]


# ---------------------------------------------------------------------------
# plot_point
# ---------------------------------------------------------------------------
# A point placed on a coordinate plane, scored by how many grid cells it is from the target
# (docs/plans/t7-plot-the-point.md). The phone answers grid indices {"col", "row"}; the
# target is stored in graph units {"x", "y"} and checked once to lie on a grid point, so
# scoring and buckets only ever compare whole numbers.
# config: {"xMin", "xMax", "xStep", "yMin", "yMax", "yStep", "xLabel"?, "yLabel"?,
#          "overlays"?, "image_id"? (T8, checked by image_service)}
# answer_data (ACCURACY): {"target": {"x", "y"}, "bands": [{"within": cells, "points": p}]}

_PLOT_LIMIT = 1e6
_PLOT_TOL = 1e-9
_PLOT_MAX_CELLS = 20
_PLOT_MAX_OVERLAYS = 20
_PLOT_LABEL_MAX = 20
# Allowed steps: 1, 2 or 5 times a power of ten, 0.001 ... 500000.
_PLOT_STEPS = tuple(m * 10.0**k for k in range(-3, 6) for m in (1, 2, 5))
_PLOT_ANSWER_ERROR = "plot_point answer must be a grid point inside the plane"


def _plot_number(v: Any) -> bool:
    """A Number (int or float, not bool, finite) with |v| <= 1e6. The range comparison also
    rejects NaN and infinities, and is safe for arbitrarily large ints."""
    return _is_number(v) and -_PLOT_LIMIT <= v <= _PLOT_LIMIT


def _plot_label_ok(v: Any) -> bool:
    """An optional label: absent (None) or a 1-20 character string, not whitespace only."""
    return v is None or (
        isinstance(v, str) and 1 <= len(v) <= _PLOT_LABEL_MAX and bool(v.strip())
    )


def _plot_whole(v: float) -> bool:
    return abs(v - round(v)) <= _PLOT_TOL


def _plot_axes_problem(config: Any) -> str | None:
    """Rules 1-4 (limits, steps, multiples, cell counts): the first problem, or None."""
    c = config if isinstance(config, dict) else {}
    limits = [c.get(k) for k in ("xMin", "xMax", "yMin", "yMax")]
    if not all(_plot_number(v) for v in limits) or not (
        c["xMin"] < c["xMax"] and c["yMin"] < c["yMax"]
    ):
        return "plot_point axis limits must be finite numbers with min < max"
    steps = (c.get("xStep"), c.get("yStep"))
    if not all(
        _is_number(s)
        and any(math.isclose(s, a, rel_tol=_PLOT_TOL) for a in _PLOT_STEPS)
        for s in steps
    ):
        return "plot_point steps must be 1, 2 or 5 times a power of ten"
    for lo, hi, step in (
        (c["xMin"], c["xMax"], c["xStep"]),
        (c["yMin"], c["yMax"], c["yStep"]),
    ):
        if not (_plot_whole(lo / step) and _plot_whole(hi / step)):
            return "plot_point axis limits must be multiples of their step"
    for lo, hi, step in (
        (c["xMin"], c["xMax"], c["xStep"]),
        (c["yMin"], c["yMax"], c["yStep"]),
    ):
        if not 1 <= round((hi - lo) / step) <= _PLOT_MAX_CELLS:
            return "plot_point allows 1 to 20 cells per axis"
    return None


def _plot_grid(config: Any) -> tuple[int, int] | None:
    """(nCols, nRows) for a config that passes rules 1-4, else None. Never raises."""
    if _plot_axes_problem(config) is not None:
        return None
    return (
        round((config["xMax"] - config["xMin"]) / config["xStep"]),
        round((config["yMax"] - config["yMin"]) / config["yStep"]),
    )


def _plot_overlay_ok(item: Any) -> bool:
    """Rule 6 for one overlay. Unknown keys are ignored."""
    if not isinstance(item, dict) or not _plot_label_ok(item.get("label")):
        return False
    kind = item.get("kind")
    if kind == "point":
        return all(_plot_number(item.get(k)) for k in ("x", "y"))
    if kind == "line":
        pts = [item.get(k) for k in ("x1", "y1", "x2", "y2")]
        return all(_plot_number(v) for v in pts) and (pts[0], pts[1]) != (
            pts[2],
            pts[3],
        )
    if kind == "polynomial":
        coeffs = item.get("coefficients")
        return (
            isinstance(coeffs, list)
            and 1 <= len(coeffs) <= 4
            and all(_plot_number(v) for v in coeffs)
        )
    return False


def _plot_target(q: Any) -> tuple[int, int] | None:
    """Rule 8: the target's grid indices (tcol, trow), or None if the config is unusable or
    the target is not a grid point inside the plane. The only float comparison in the type."""
    grid = _plot_grid(q.config)
    target = _answer_data(q).get("target")
    if grid is None or not isinstance(target, dict):
        return None
    x, y = target.get("x"), target.get("y")
    if not (_plot_number(x) and _plot_number(y)):
        return None
    c = q.config
    kx = (x - c["xMin"]) / c["xStep"]
    ky = (y - c["yMin"]) / c["yStep"]
    if not (_plot_whole(kx) and _plot_whole(ky)):
        return None
    tcol, trow = round(kx), round(ky)
    if not (0 <= tcol <= grid[0] and 0 <= trow <= grid[1]):
        return None
    return tcol, trow


def _plot_index(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _plot_validate_definition(q: Any) -> None:
    config = q.config if isinstance(q.config, dict) else {}
    problem = _plot_axes_problem(config)
    if problem:
        raise ValueError(problem)
    if not (
        _plot_label_ok(config.get("xLabel")) and _plot_label_ok(config.get("yLabel"))
    ):
        raise ValueError("plot_point labels must be 1 to 20 characters")
    overlays = config.get("overlays")
    if overlays is not None and not (
        isinstance(overlays, list)
        and len(overlays) <= _PLOT_MAX_OVERLAYS
        and all(_plot_overlay_ok(item) for item in overlays)
    ):
        raise ValueError("plot_point overlay is invalid")
    if q.grading_type != "ACCURACY":
        return
    if _plot_target(q) is None:
        raise ValueError("plot_point target must be a grid point inside the plane")
    n_cols, n_rows = _plot_grid(config)  # rules 1-4 passed above
    bands = _answer_data(q).get("bands")
    if not isinstance(bands, list) or not 1 <= len(bands) <= _MAX_BANDS:
        raise ValueError("bands must be a list of 1 to 5 items")
    for band in bands:
        if not (
            isinstance(band, dict)
            and _plot_index(band.get("within"))
            and 0 <= band["within"] <= max(n_cols, n_rows)
            and _is_number(band.get("points"))
            and 0 < band["points"] <= _PLOT_LIMIT
        ):
            raise ValueError("each band needs whole-cell within ≥ 0 and points > 0")
    withins = [b["within"] for b in bands]
    points = [b["points"] for b in bands]
    if any(b <= a for a, b in zip(withins, withins[1:])):
        raise ValueError("band within values must strictly increase")
    if any(b >= a for a, b in zip(points, points[1:])):
        raise ValueError("band points must strictly decrease")
    if not math.isclose(float(q.points_value), float(points[0]), abs_tol=1e-9):
        raise ValueError("points_value must equal the first band's points")


def _plot_validate_answer(q: Any, answer_data: Any) -> str | None:
    grid = _plot_grid(q.config)
    if grid is None or not isinstance(answer_data, dict):
        return _PLOT_ANSWER_ERROR
    col, row = answer_data.get("col"), answer_data.get("row")
    if not (_plot_index(col) and _plot_index(row)):
        return _PLOT_ANSWER_ERROR
    if not (0 <= col <= grid[0] and 0 <= row <= grid[1]):
        return _PLOT_ANSWER_ERROR
    return None


def _plot_normalize_answer(q: Any, answer_data: Any) -> Any:
    """Only called for answers validate_answer accepted: keep exactly {col, row}."""
    return {"col": answer_data["col"], "row": answer_data["row"]}


def plot_band_index(q: Any, col: Any, row: Any) -> int | None:
    """Index of the first band a grid point falls in (cell distance max(|dcol|, |drow|)),
    or None for a miss or anything unusable. Never raises. Also used by the report."""
    target = _plot_target(q)
    if target is None or not (_plot_index(col) and _plot_index(row)):
        return None
    distance = max(abs(col - target[0]), abs(row - target[1]))
    bands = _answer_data(q).get("bands")
    for i, band in enumerate(bands if isinstance(bands, list) else []):
        within = band.get("within") if isinstance(band, dict) else None
        if _plot_index(within) and distance <= within:
            return i
    return None


def _plot_score(q: Any, answer_data: dict) -> ScoreResult:
    index = plot_band_index(q, answer_data.get("col"), answer_data.get("row"))
    if index is None:
        return _zero()
    points = _answer_data(q)["bands"][index].get("points")
    if not _is_number(points):
        return _zero()
    return ScoreResult(points_awarded=points, is_correct=(index == 0))


def _plot_reveal(q: Any) -> dict:
    data = _answer_data(q)
    target = data.get("target") if isinstance(data.get("target"), dict) else {}
    bands = data.get("bands") if isinstance(data.get("bands"), list) else []
    return {
        "type": "plot_point",
        "target": {"x": target.get("x"), "y": target.get("y")},
        "bands": [
            {"within": b.get("within"), "points": b.get("points")}
            for b in bands
            if isinstance(b, dict)
        ],
    }


def _plot_keys(q: Any, answer_data: dict) -> list[str]:
    """The grid point, for both grading types (a COMPLETENESS poll still gets a scatter)."""
    col, row = answer_data.get("col"), answer_data.get("row")
    if not (_plot_index(col) and _plot_index(row)):
        return []
    return [f"{col},{row}"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TYPES: dict[str, QuestionType] = {
    t.key: t
    for t in (
        QuestionType(
            key="multiple_choice",
            label="Multiple Choice",
            validate_definition=_mc_validate_definition,
            validate_answer=_no_answer_check,
            score=_mc_score,
            reveal=_mc_reveal,
            distribution_keys=_mc_keys,
            payload_extras=_no_extras,
        ),
        QuestionType(
            key="true_false",
            label="True / False",
            validate_definition=_tf_validate_definition,
            validate_answer=_no_answer_check,
            score=_tf_score,
            reveal=_tf_reveal,
            distribution_keys=_tf_keys,
            payload_extras=_no_extras,
        ),
        QuestionType(
            key="fill_in_the_blank",
            label="Fill in the Blank",
            validate_definition=_fitb_validate_definition,
            validate_answer=_no_answer_check,
            score=_fitb_score,
            reveal=_fitb_reveal,
            distribution_keys=_fitb_keys,
            payload_extras=_fitb_extras,
        ),
        QuestionType(
            key="multi_select",
            label="Multi Select",
            validate_definition=_ms_validate_definition,
            validate_answer=_ms_validate_answer,
            score=_ms_score,
            reveal=_ms_reveal,
            distribution_keys=_ms_keys,
            payload_extras=_no_extras,
        ),
        QuestionType(
            key="numeric_estimate",
            label="Numeric Estimate",
            validate_definition=_numeric_validate_definition,
            validate_answer=_numeric_validate_answer,
            score=_numeric_score,
            reveal=_numeric_reveal,
            distribution_keys=_numeric_keys,
            payload_extras=_no_extras,
        ),
        QuestionType(
            key="plot_point",
            label="Plot the Point",
            validate_definition=_plot_validate_definition,
            validate_answer=_plot_validate_answer,
            score=_plot_score,
            reveal=_plot_reveal,
            distribution_keys=_plot_keys,
            payload_extras=_no_extras,
            normalize_answer=_plot_normalize_answer,
        ),
    )
}


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def known_types() -> frozenset[str]:
    return frozenset(_TYPES)


def label_for(question_type: str) -> str:
    handler = _TYPES.get(question_type)
    return handler.label if handler else question_type


def _is_answer(answer_data: Any) -> bool:
    """An answer is a non-empty dict; None, {} and anything else count as no answer."""
    return isinstance(answer_data, dict) and bool(answer_data)


def validate_definition(q: QuestionLike) -> None:
    """Raise ValueError if the question's config / answer_data are structurally wrong
    for its type and grading type."""
    handler = _TYPES.get(q.type)
    if handler is None:
        raise ValueError(f"Unknown question type '{q.type}'")
    handler.validate_definition(q)


def validate_answer(q: QuestionLike, answer_data: Any) -> str | None:
    """An error message if the submitted answer is unacceptable for this question, else
    None. Never raises."""
    handler = _TYPES.get(q.type)
    return handler.validate_answer(q, answer_data) if handler else None


def normalize_answer(q: QuestionLike, answer_data: Any) -> Any:
    """The answer to score, bucket and store; unchanged unless the type normalizes it.
    Runs for every grading type. Never raises."""
    handler = _TYPES.get(q.type)
    return handler.normalize_answer(q, answer_data) if handler else answer_data


def accept_answer(q: QuestionLike, answer_data: Any) -> tuple[str | None, Any]:
    """What the gateway does with a submitted answer, in order: validate it, then
    normalize it. Returns (error message, None) for a rejected answer, which is never
    normalized, or (None, the answer to score and store)."""
    problem = validate_answer(q, answer_data)
    if problem:
        return problem, None
    return None, normalize_answer(q, answer_data)


def score_answer(q: QuestionLike, answer_data: Any) -> ScoreResult:
    """Points for a submitted answer. No answer scores 0; COMPLETENESS gives full points
    for any answer; otherwise the type decides. An unknown type scores 0."""
    if not _is_answer(answer_data):
        return _zero()
    if q.grading_type == "COMPLETENESS":
        return ScoreResult(points_awarded=q.points_value, is_correct=True)
    handler = _TYPES.get(q.type)
    return handler.score(q, answer_data) if handler else _zero()


def answer_reveal(q: QuestionLike) -> dict:
    """Client-safe correct-answer facts, sent only after the question closes."""
    if q.grading_type == "COMPLETENESS":
        return {"type": "completeness"}
    handler = _TYPES.get(q.type)
    return handler.reveal(q) if handler else {}


def distribution_keys_for(q: QuestionLike, answer_data: Any) -> list[str]:
    """Keys to count in the answer distribution for one answer (live in Redis, and
    recomputed from stored answers for the game-over summary and the report)."""
    if not _is_answer(answer_data):
        return []
    handler = _TYPES.get(q.type)
    return handler.distribution_keys(q, answer_data) if handler else []


def payload_extras(q: QuestionLike) -> dict:
    handler = _TYPES.get(q.type)
    return handler.payload_extras(q) if handler else {}
