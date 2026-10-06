"""
Unit tests for the question-type registry (backend/app/services/question_types.py).

No Docker stack needed.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_question_types.py -v
"""
from __future__ import annotations

import pytest

from app.services import question_types
from app.services.question_types import (
    QuestionSpec,
    QuestionType,
    accept_answer,
    answer_reveal,
    distribution_keys_for,
    known_types,
    label_for,
    normalize_answer,
    payload_extras,
    score_answer,
    validate_answer,
    validate_definition,
)


def q(type_, grading="ACCURACY", config=None, answer_data=None, points=1.0):
    return QuestionSpec(
        type=type_,
        grading_type=grading,
        config=config or {},
        answer_data=answer_data or {},
        points_value=points,
    )


MC = q("multiple_choice", config={"options": ["A", "B", "C"]},
       answer_data={"answer_points": [0, 1, 0.5]}, points=1)
TF = q("true_false", answer_data={"answer_points": {"true": 1, "false": 0}})
FITB = q("fill_in_the_blank",
         answer_data={"acceptedAnswers": ["New York", "NYC"], "answerPoints": [2, 1], "editDistance": 1},
         points=2)
MS = q("multi_select", config={"options": ["A", "B", "C"]},
       answer_data={"answer_points": [1, 1, -2]}, points=2)


def test_known_types_and_labels():
    assert known_types() == {"multiple_choice", "true_false", "fill_in_the_blank", "multi_select"}
    assert label_for("multi_select") == "Multi Select"
    assert label_for("something_else") == "something_else"


# --- scoring ---------------------------------------------------------------


@pytest.mark.parametrize(
    "question, answer, points, correct",
    [
        (MC, {"selectedIndex": 1}, 1, True),
        (MC, {"selectedIndex": 2}, 0.5, False),
        (MC, {"selectedIndex": 0}, 0, False),
        (MC, {"selectedIndex": 9}, 0, False),
        (MC, {}, 0, False),
        (TF, {"selectedValue": True}, 1, True),
        (TF, {"selectedValue": False}, 0, False),
        (FITB, {"text": "  new   YORK "}, 2, True),
        (FITB, {"text": "new yorc"}, 2, True),  # within edit distance 1
        (FITB, {"text": "boston"}, 0, False),
        (FITB, {"text": ""}, 0, False),
        (MS, {"selectedIndices": [0, 1]}, 2, True),
        (MS, {"selectedIndices": [0]}, 1, False),
        (MS, {"selectedIndices": [0, 2]}, 0, False),  # floored at 0
        (MS, {"selectedIndices": "x"}, 0, False),
    ],
)
def test_score_accuracy(question, answer, points, correct):
    result = score_answer(question, answer)
    assert result.points_awarded == points
    assert result.is_correct is correct


def test_score_completeness_and_empty_and_unknown():
    mc = q("multiple_choice", "COMPLETENESS", {"options": ["A", "B"]}, points=3)
    assert score_answer(mc, {"selectedIndex": 0}).points_awarded == 3
    assert score_answer(mc, {"selectedIndex": 0}).is_correct is True
    assert score_answer(mc, {}).points_awarded == 0
    assert score_answer(mc, None).points_awarded == 0
    assert score_answer(MC, "not a dict").points_awarded == 0
    assert score_answer(q("mystery", answer_data={"x": 1}), {"a": 1}).points_awarded == 0


# --- reveal ----------------------------------------------------------------


def test_reveal_shapes():
    assert answer_reveal(MC) == {"type": "multiple_choice", "correctIndices": [1]}
    assert answer_reveal(TF) == {"type": "true_false", "correctValue": True}
    assert answer_reveal(FITB) == {
        "type": "fill_in_the_blank", "acceptedAnswers": ["New York", "NYC"], "editDistance": 1}
    assert answer_reveal(MS) == {"type": "multi_select", "answerPoints": [1, 1, -2]}
    assert answer_reveal(q("multiple_choice", "COMPLETENESS")) == {"type": "completeness"}
    assert answer_reveal(q("mystery")) == {}


def test_reveal_is_a_new_dict_and_never_exposes_extra_keys():
    data = {"answer_points": [0, 1], "secret": "x"}
    question = q("multiple_choice", config={"options": ["A", "B"]}, answer_data=data)
    reveal = answer_reveal(question)
    assert set(reveal) == {"type", "correctIndices"}
    reveal["correctIndices"].append(99)
    assert data == {"answer_points": [0, 1], "secret": "x"}


# --- distribution keys -----------------------------------------------------


def test_distribution_keys():
    assert distribution_keys_for(MC, {"selectedIndex": 2}) == ["2"]
    assert distribution_keys_for(TF, {"selectedValue": False}) == ["false"]
    assert distribution_keys_for(FITB, {"text": "  New   YORK "}) == ["new york"]
    assert distribution_keys_for(MS, {"selectedIndices": [0, 2, "x"]}) == ["0", "2"]
    assert distribution_keys_for(MC, {}) == []
    assert distribution_keys_for(MC, None) == []
    assert distribution_keys_for(q("mystery"), {"a": 1}) == []


def test_fitb_key_collapses_whitespace_the_same_everywhere():
    # live counting, the game-over summary and the report all call this one function
    assert distribution_keys_for(FITB, {"text": "New  York"}) == distribution_keys_for(
        FITB, {"text": "new york"}
    )


# --- payload extras --------------------------------------------------------


def test_payload_extras():
    assert payload_extras(FITB) == {"editDistance": 1}
    assert payload_extras(MC) == {}
    assert payload_extras(q("fill_in_the_blank", answer_data={})) == {"editDistance": 0}


# --- validate_answer -------------------------------------------------------


@pytest.mark.parametrize(
    "answer, expected",
    [
        ({"selectedIndices": [0, 1]}, None),
        ({"selectedIndices": []}, None),
        ({"selectedIndices": "x"}, "multi_select answer must include selectedIndices as a list of integers"),
        ({"selectedIndices": [0, "1"]}, "multi_select answer must include selectedIndices as a list of integers"),
        ({}, "multi_select answer must include selectedIndices as a list of integers"),
        ("nope", "multi_select answer must include selectedIndices as a list of integers"),
        ({"selectedIndices": [3]}, "selectedIndices contains an out-of-bounds index"),
        ({"selectedIndices": [-1]}, "selectedIndices contains an out-of-bounds index"),
    ],
)
def test_validate_answer_multi_select(answer, expected):
    assert validate_answer(MS, answer) == expected


def test_validate_answer_other_types_accept_anything_and_never_raise():
    for question in (MC, TF, FITB, q("mystery")):
        for answer in ({"selectedIndex": "x"}, None, "x", 5, []):
            assert validate_answer(question, answer) is None


# --- validate_definition ---------------------------------------------------


@pytest.mark.parametrize(
    "question, message",
    [
        (q("multiple_choice", config={"options": ["A"]}),
         "multiple_choice config must have 'options' list with at least 2 items"),
        (q("multiple_choice", config={"options": ["A", "B"]}, answer_data={"answer_points": [1]}),
         "ACCURACY multiple_choice answer_data must have 'answer_points' list matching options length"),
        (q("multiple_choice", config={"options": ["A", "B"]}, answer_data={"answer_points": [1, -1]}),
         "answer_points values must be non-negative numbers"),
        (q("true_false", answer_data={"answer_points": {"true": 1}}),
         "ACCURACY true_false answer_data must have 'answer_points' with 'true' and 'false' keys"),
        (q("fill_in_the_blank", answer_data={}),
         "ACCURACY fill_in_the_blank answer_data must have 'acceptedAnswers' list with at least one item"),
        (q("fill_in_the_blank", answer_data={"acceptedAnswers": ["a", " "], "answerPoints": [1, 1]}),
         "acceptedAnswers entries must be non-empty strings"),
        (q("fill_in_the_blank", answer_data={"acceptedAnswers": ["a"], "answerPoints": [1, 2]}),
         "ACCURACY fill_in_the_blank answer_data must have 'answerPoints' list matching acceptedAnswers length"),
        (q("fill_in_the_blank", answer_data={"acceptedAnswers": ["a"], "answerPoints": [-1]}),
         "answerPoints values must be non-negative numbers"),
        (q("fill_in_the_blank", answer_data={"acceptedAnswers": ["a"], "answerPoints": [1], "editDistance": -1}),
         "editDistance must be a non-negative integer"),
        (q("multi_select", config={"options": ["A"]}),
         "multi_select config must have 'options' list with at least 2 items"),
        (q("multi_select", config={"options": ["A", "B"]}, answer_data={"answer_points": [1]}),
         "ACCURACY multi_select answer_data must have 'answer_points' list matching options length"),
        (q("multi_select", config={"options": ["A", "B"]}, answer_data={"answer_points": [1, "x"]}),
         "answer_points values must be numbers"),
        (q("mystery"), "Unknown question type 'mystery'"),
    ],
)
def test_validate_definition_rejects(question, message):
    with pytest.raises(ValueError) as exc:
        validate_definition(question)
    assert str(exc.value) == message


def test_validate_definition_accepts_valid_and_completeness():
    for question in (MC, TF, FITB, MS):
        validate_definition(question)
    # COMPLETENESS needs no answer key (but MC and multi_select still need options)
    validate_definition(q("true_false", "COMPLETENESS"))
    validate_definition(q("fill_in_the_blank", "COMPLETENESS"))
    validate_definition(q("multiple_choice", "COMPLETENESS", {"options": ["A", "B"]}))
    with pytest.raises(ValueError):
        validate_definition(q("multiple_choice", "COMPLETENESS", {"options": ["A"]}))


# ---------------------------------------------------------------------------
# normalize_answer (requested for the Canvas type, docs/plans/t7-plot-the-point.md)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,answer",
    [
        (MC, {"selectedIndex": 1}),
        (TF, {"selectedValue": True}),
        (FITB, {"text": "  new   york "}),
        (MS, {"selectedIndices": [2, 0]}),
        (q("multiple_choice", grading="COMPLETENESS", config={"options": ["A", "B"]}), {"selectedIndex": 0}),
        (q("no_such_type"), {"anything": 1}),
    ],
)
def test_normalize_answer_default_returns_the_answer_unchanged(question, answer):
    before = repr(answer)
    assert normalize_answer(question, answer) is answer
    assert accept_answer(question, answer) == (None, answer)
    assert repr(answer) == before


def _snapping_type(calls: list) -> QuestionType:
    def validate(q, a):
        return None if isinstance(a, dict) and isinstance(a.get("x"), (int, float)) else "need x"

    def normalize(q, a):
        calls.append(a)
        return {"cell": int(a["x"] // 10)}

    return QuestionType(
        key="snap",
        label="Snap",
        validate_definition=lambda q: None,
        validate_answer=validate,
        score=lambda q, a: question_types._zero(),
        reveal=lambda q: {},
        distribution_keys=lambda q, a: [str(a.get("cell"))],
        payload_extras=lambda q: {},
        normalize_answer=normalize,
    )


@pytest.mark.parametrize("grading", ["ACCURACY", "COMPLETENESS"])
def test_accept_answer_validates_then_normalizes_for_every_grading_type(monkeypatch, grading):
    calls: list = []
    monkeypatch.setitem(question_types._TYPES, "snap", _snapping_type(calls))
    question = q("snap", grading=grading)

    assert accept_answer(question, {"x": 37.5}) == (None, {"cell": 3})
    assert normalize_answer(question, {"x": 5}) == {"cell": 0}
    # The normalized answer is what the distribution keys are computed from.
    assert distribution_keys_for(question, accept_answer(question, {"x": 99})[1]) == ["9"]

    calls.clear()
    assert accept_answer(question, {"y": 1}) == ("need x", None)
    assert calls == [], "a rejected answer is never normalized"
