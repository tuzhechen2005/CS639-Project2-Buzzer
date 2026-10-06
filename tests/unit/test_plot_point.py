"""
Unit tests for the plot_point question type (docs/plans/t7-plot-the-point.md, P1-P3).

No Docker stack needed. Run from the repo root:
    PYTHONPATH=backend pytest tests/unit/test_plot_point.py -v
"""

from __future__ import annotations

import copy

import pytest

from app.services.question_types import (
    QuestionSpec,
    accept_answer,
    answer_reveal,
    distribution_keys_for,
    label_for,
    normalize_answer,
    plot_band_index,
    score_answer,
    validate_answer,
    validate_definition,
)

CONFIG = {"xMin": -10, "xMax": 10, "xStep": 1, "yMin": -10, "yMax": 10, "yStep": 1}
# Target (3, -2) is grid point col 13, row 8 on the -10..10 plane.
ANSWER = {
    "target": {"x": 3, "y": -2},
    "bands": [{"within": 0, "points": 100}, {"within": 1, "points": 50}],
}


def pq(config=None, answer_data=None, grading="ACCURACY", points=100):
    return QuestionSpec(
        type="plot_point",
        grading_type=grading,
        config=copy.deepcopy(CONFIG if config is None else config),
        answer_data=copy.deepcopy(ANSWER if answer_data is None else answer_data),
        points_value=points,
    )


def with_config(**changes):
    return {**CONFIG, **changes}


def with_answer(**changes):
    return {**ANSWER, **changes}


def rejects(question, message):
    with pytest.raises(ValueError) as exc:
        validate_definition(question)
    assert str(exc.value) == message


AXES = "plot_point axis limits must be finite numbers with min < max"
STEPS = "plot_point steps must be 1, 2 or 5 times a power of ten"
MULTIPLES = "plot_point axis limits must be multiples of their step"
CELLS = "plot_point allows 1 to 20 cells per axis"
LABELS = "plot_point labels must be 1 to 20 characters"
OVERLAY = "plot_point overlay is invalid"
TARGET = "plot_point target must be a grid point inside the plane"
BAND_COUNT = "bands must be a list of 1 to 5 items"
BAND_ITEM = "each band needs whole-cell within ≥ 0 and points > 0"
WITHIN_ORDER = "band within values must strictly increase"
POINTS_ORDER = "band points must strictly decrease"
POINTS_VALUE = "points_value must equal the first band's points"
ANSWER_ERROR = "plot_point answer must be a grid point inside the plane"


# --- definition: accepted --------------------------------------------------


def test_label():
    assert label_for("plot_point") == "Plot the Point"


def test_valid_definition_with_everything():
    config = with_config(
        xLabel="x",
        yLabel="y",
        image_id="0b0c4f0e-2f6d-4f6e-9a55-3a8f5f2b7c11",  # ignored here (image_service checks it)
        overlays=[
            {"kind": "line", "x1": 0, "y1": 1, "x2": 1, "y2": 3, "label": "y = 2x + 1"},
            {"kind": "polynomial", "coefficients": [-3, -2, 1], "label": "y = x² − 2x − 3"},
            {"kind": "point", "x": 0, "y": 7, "label": "A", "colour": "red"},  # unknown key
            {"kind": "line", "x1": 2, "y1": -50, "x2": 2, "y2": 50},  # vertical, past the plane
        ],
    )
    validate_definition(pq(config))


@pytest.mark.parametrize(
    "config",
    [
        with_config(xLabel=None, yLabel=None, overlays=None),  # null counts as absent
        with_config(overlays=[]),
        with_config(xLabel="x" * 20),
        with_config(xMin=0, xMax=2, xStep=0.1, yMin=0, yMax=1, yStep=0.05),  # decimal steps
        with_config(xMin=0, xMax=100, xStep=5, yMin=0, yMax=1000, yStep=50),
        with_config(xMin=0, xMax=1_000_000, xStep=500_000),
        with_config(xMin=0, xMax=0.01, xStep=0.001),
        with_config(xMin=0, xMax=1),  # a single cell
    ],
)
def test_valid_configs(config):
    validate_definition(pq(config, {"target": {"x": config["xMin"], "y": config["yMin"]},
                                    "bands": [{"within": 0, "points": 100}]}))


def test_target_on_a_decimal_grid_is_accepted():
    config = with_config(xMin=0, xMax=2, xStep=0.1, yMin=0, yMax=2, yStep=0.1)
    validate_definition(pq(config, with_answer(target={"x": 0.3, "y": 0.30000000000000004})))


def test_completeness_needs_no_answer_data():
    validate_definition(pq(answer_data={}, grading="COMPLETENESS", points=10))


def test_completeness_still_checks_the_plane():
    rejects(pq(with_config(xStep=3), {}, grading="COMPLETENESS"), STEPS)


# --- definition: rejected, in rule order -----------------------------------


@pytest.mark.parametrize(
    "config",
    [
        with_config(xMin=10),  # min == max
        with_config(yMin=11),  # min > max
        with_config(xMin=True),  # bool limit
        with_config(xMax="10"),
        with_config(xMax=float("inf")),
        with_config(xMax=float("nan")),
        with_config(xMax=2_000_000),
        {k: v for k, v in CONFIG.items() if k != "yMax"},
    ],
)
def test_rule_1_limits(config):
    rejects(pq(config), AXES)


@pytest.mark.parametrize("step", [3, 0.3, 0, -1, 0.0001, 1_000_000, True, "1", None])
def test_rule_2_steps(step):
    rejects(pq(with_config(xStep=step)), STEPS)


def test_rule_3_limit_off_its_step():
    rejects(pq(with_config(xMin=-9, xMax=10, xStep=2)), MULTIPLES)


@pytest.mark.parametrize(
    "config",
    [
        with_config(xMin=-10, xMax=11),  # 21 cells
        with_config(yMin=0, yMax=100, yStep=1),
    ],
)
def test_rule_4_cells(config):
    rejects(pq(config), CELLS)


@pytest.mark.parametrize("label", ["", "   ", "x" * 21, 5])
def test_rule_5_axis_labels(label):
    rejects(pq(with_config(yLabel=label)), LABELS)


@pytest.mark.parametrize(
    "overlays",
    [
        "not a list",
        [{"kind": "point", "x": 0, "y": 0}] * 21,
        [{"kind": "circle", "x": 0, "y": 0}],
        [{"kind": "polynomial", "coefficients": [1, 2, 3, 4, 5]}],
        [{"kind": "polynomial", "coefficients": []}],
        [{"kind": "polynomial", "coefficients": [1, True]}],
        [{"kind": "line", "x1": 1, "y1": 1, "x2": 1, "y2": 1}],
        [{"kind": "point", "x": True, "y": 0}],
        [{"kind": "point", "x": 0, "y": 2_000_000}],
        [{"kind": "point", "x": 0}],
        [{"kind": "point", "x": 0, "y": 0, "label": "   "}],
        [{"kind": "point", "x": 0, "y": 0, "label": "x" * 21}],
        ["point"],
    ],
)
def test_rule_6_overlays(overlays):
    rejects(pq(with_config(overlays=overlays)), OVERLAY)


def test_overlay_label_null_is_absent():
    validate_definition(pq(with_config(overlays=[{"kind": "point", "x": 0, "y": 0, "label": None}])))


@pytest.mark.parametrize(
    "target",
    [
        {"x": 3.5, "y": -2},  # off the grid
        {"x": 11, "y": 0},  # outside
        {"x": 0, "y": -11},
        {"x": True, "y": 0},  # bool
        {"x": "3", "y": 0},
        {"x": 3},
        None,
    ],
)
def test_rule_8_target(target):
    rejects(pq(answer_data=with_answer(target=target)), TARGET)


@pytest.mark.parametrize("bands", [[], [{"within": i, "points": 10 - i} for i in range(6)], None])
def test_rule_9_band_count(bands):
    rejects(pq(answer_data=with_answer(bands=bands)), BAND_COUNT)


@pytest.mark.parametrize(
    "band",
    [
        {"within": 0.5, "points": 100},  # float within
        {"within": True, "points": 100},  # bool within
        {"within": -1, "points": 100},
        {"within": 21, "points": 100},  # more than the larger cell count
        {"within": 0, "points": 0},
        {"within": 0, "points": True},
        {"within": 0, "points": 2_000_000},
        "band",
    ],
)
def test_rule_9_band_items(band):
    rejects(pq(answer_data=with_answer(bands=[band])), BAND_ITEM)


def test_rule_9_order():
    rejects(
        pq(answer_data=with_answer(bands=[{"within": 1, "points": 100}, {"within": 1, "points": 50}])),
        WITHIN_ORDER,
    )
    rejects(
        pq(answer_data=with_answer(bands=[{"within": 0, "points": 50}, {"within": 1, "points": 50}])),
        POINTS_ORDER,
    )


def test_rule_10_points_value():
    rejects(pq(points=99), POINTS_VALUE)
    validate_definition(pq(points=100.0))


def test_first_failing_rule_wins():
    # Steps and target are both wrong: the step rule (2) is reported, not the target (8).
    rejects(pq(with_config(xStep=3), with_answer(target={"x": 0.5, "y": 0})), STEPS)


# --- answers -----------------------------------------------------------------


@pytest.mark.parametrize(
    "answer", [{"col": 13, "row": 8}, {"col": 0, "row": 0}, {"col": 20, "row": 20}, {"col": 0, "row": 20}]
)
def test_answers_accepted(answer):
    assert validate_answer(pq(), answer) is None


@pytest.mark.parametrize(
    "answer",
    [
        {"col": -1, "row": 0},
        {"col": 21, "row": 0},
        {"col": 0, "row": 21},
        {"col": 1.0, "row": 0},
        {"col": "1", "row": 0},
        {"col": True, "row": 0},
        {"col": 1},
        [1, 2],
        None,
    ],
)
def test_answers_rejected(answer):
    assert validate_answer(pq(), answer) == ANSWER_ERROR


def test_answer_rejected_when_config_is_unusable():
    assert validate_answer(pq(with_config(xStep=3)), {"col": 0, "row": 0}) == ANSWER_ERROR


def test_accept_answer_drops_extra_keys():
    problem, accepted = accept_answer(pq(), {"col": 4, "row": 9, "x": 999, "debug": True})
    assert problem is None
    assert accepted == {"col": 4, "row": 9}
    assert normalize_answer(pq(), {"col": 4, "row": 9, "extra": 1}) == {"col": 4, "row": 9}


def test_rejected_answer_is_not_normalized():
    problem, accepted = accept_answer(pq(), {"col": 99, "row": 0})
    assert problem == ANSWER_ERROR and accepted is None


# --- scoring -----------------------------------------------------------------
# Spec worked example: target (3, -2) = col 13, row 8; bands exact -> 100, within 1 -> 50.


@pytest.mark.parametrize(
    "point,points,correct",
    [
        ((13, 8), 100, True),  # (3, -2) exact
        ((14, 9), 50, False),  # (4, -1) diagonal neighbour
        ((14, 8), 50, False),  # (4, -2)
        ((12, 7), 50, False),  # (2, -3)
        ((15, 8), 0, False),  # (5, -2): 2 cells, a miss
        ((8, 13), 0, False),  # (-2, 3): x and y swapped
        ((0, 20), 0, False),
    ],
)
def test_scoring(point, points, correct):
    result = score_answer(pq(), {"col": point[0], "row": point[1]})
    assert result.points_awarded == points and result.is_correct is correct


def test_band_boundaries():
    bands = [{"within": 0, "points": 100}, {"within": 2, "points": 60}, {"within": 4, "points": 20}]
    q3 = pq(answer_data=with_answer(bands=bands))
    expected = {0: 100, 1: 60, 2: 60, 3: 20, 4: 20, 5: 0}
    for distance, points in expected.items():
        assert score_answer(q3, {"col": 13 + distance, "row": 8}).points_awarded == points


def test_corner_answer_is_an_answer_and_scores():
    # Target at (xMin, yMin) = col 0, row 0: {col: 0, row: 0} is a real, non-empty answer.
    q0 = pq(answer_data=with_answer(target={"x": -10, "y": -10}))
    result = score_answer(q0, {"col": 0, "row": 0})
    assert result.points_awarded == 100 and result.is_correct is True


def test_completeness_full_points_for_any_point():
    qc = pq(answer_data={}, grading="COMPLETENESS", points=10)
    result = score_answer(qc, {"col": 2, "row": 17})
    assert result.points_awarded == 10 and result.is_correct is True


def test_score_never_raises_on_malformed_input():
    assert score_answer(pq(), {"col": "x", "row": None}).points_awarded == 0
    broken = pq(answer_data={"target": "nowhere", "bands": "none"})
    assert score_answer(broken, {"col": 1, "row": 1}).points_awarded == 0
    assert score_answer(pq(with_config(xStep=3)), {"col": 1, "row": 1}).points_awarded == 0


def test_plot_band_index_agrees_with_score():
    bands = [{"within": 0, "points": 100}, {"within": 1, "points": 50}, {"within": 3, "points": 10}]
    q3 = pq(answer_data=with_answer(bands=bands))
    for col in range(0, 21):
        for row in range(0, 21):
            index = plot_band_index(q3, col, row)
            result = score_answer(q3, {"col": col, "row": row})
            expected = 0 if index is None else bands[index]["points"]
            assert result.points_awarded == expected
            assert result.is_correct is (index == 0)


# --- buckets and reveal --------------------------------------------------------


def test_buckets_for_both_grading_types():
    assert distribution_keys_for(pq(), {"col": 13, "row": 8}) == ["13,8"]
    qc = pq(answer_data={}, grading="COMPLETENESS", points=10)
    assert distribution_keys_for(qc, {"col": 0, "row": 0}) == ["0,0"]
    assert distribution_keys_for(pq(), {"col": "13", "row": 8}) == []


def test_reveal_has_exactly_type_target_bands():
    reveal = answer_reveal(pq())
    assert set(reveal) == {"type", "target", "bands"}
    assert reveal == {"type": "plot_point", "target": {"x": 3, "y": -2}, "bands": ANSWER["bands"]}


def test_completeness_reveal_is_the_shared_one():
    assert answer_reveal(pq(answer_data={}, grading="COMPLETENESS", points=10)) == {
        "type": "completeness"
    }


# --- report (P4): step decimals, target line, band bars ----------------------

from app.services.report_service import (  # noqa: E402
    _fmt_coord,
    _render_bar_chart,
    _step_decimals,
)


@pytest.mark.parametrize(
    "step,decimals",
    [(1, 0), (2, 0), (5, 0), (500000, 0), (0.5, 1), (0.2, 1), (0.1, 1), (0.05, 2), (0.001, 3)],
)
def test_report_step_decimals(step, decimals):
    assert _step_decimals(step) == decimals


@pytest.mark.parametrize(
    "value,step,text",
    [
        (0.30000000000000004, 0.1, "0.3"),  # float noise never shows
        (3, 1, "3"),
        (-2, 1, "−2"),  # typographic minus
        (2.5, 0.5, "2.5"),
        (2.0, 0.5, "2"),  # trailing zeros dropped
        (-0.05, 0.05, "−0.05"),
        (-0.0000000001, 0.1, "0"),  # no "-0"
        (1500000.0, 500000, "1500000"),
    ],
)
def test_report_coordinate_format(value, step, text):
    assert _fmt_coord(value, step) == text


def test_report_band_bars_and_target_line():
    bands = [{"within": 0, "points": 100}, {"within": 1, "points": 50}, {"within": 3, "points": 10}]
    q3 = pq(answer_data=with_answer(bands=bands))
    # target col 13, row 8: two exact, one at distance 1, one at 2 (within 3), one miss
    dist = {"13,8": 2, "14,9": 1, "15,8": 1, "0,0": 1, "garbage": 4}
    html = _render_bar_chart(q3, dist, answer_reveal(q3), total_players=5)
    assert "Target: (3, −2)" in html
    labels_counts = [
        ("Exact", 2),
        ("Within 1 cell", 1),
        ("Within 3 cells", 1),
        ("Missed", 1),
    ]
    for label, count in labels_counts:
        assert f'<span class="bar-label">{label}</span>' in html
        segment = html.split(f'<span class="bar-label">{label}</span>', 1)[1].split("bar-row", 1)[0]
        assert f'<span class="bar-count">{count}</span>' in segment
    assert html.count("\u2713") == 1  # only the best band is marked correct


def test_report_target_on_a_decimal_grid():
    config = with_config(xMin=0, xMax=2, xStep=0.1, yMin=0, yMax=2, yStep=0.1)
    q01 = pq(config, with_answer(target={"x": 0.30000000000000004, "y": 0.3}))
    html = _render_bar_chart(q01, {}, answer_reveal(q01), total_players=0)
    assert "Target: (0.3, 0.3)" in html


def test_report_completeness_has_no_chart():
    qc = pq(answer_data={}, grading="COMPLETENESS", points=10)
    assert _render_bar_chart(qc, {"1,1": 3}, answer_reveal(qc), total_players=3) == ""
