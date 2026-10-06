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
