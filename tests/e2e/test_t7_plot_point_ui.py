"""T7 plot_point in the browser (docs/plans/t7-plot-the-point.md, Tests: Browser): authored in the
host editor by clicking the preview to set the target, answered on a phone by tapping the canvas
and with the "Type coordinates" panel, with full points on the phone and the class scatter on the
host results screen."""

from __future__ import annotations

from .conftest import guest_token
from .helpers import start_game

MINUS = "−"
TARGET = (12, 15)  # (2, 5) on the default plane: x and y from -10 to 10, step 1
N_ROWS = 20


def tap_grid(page, selector: str, col: int, row: int, n_rows: int = N_ROWS) -> None:
    """Click a grid point using the plot rectangle the canvas publishes (spec P6):
    data-plot-left + col*data-cell-px, data-plot-top + (nRows - row)*data-cell-px."""
    page.wait_for_function(
        "s => Number(document.querySelector(s)?.dataset.cellPx) > 0", arg=selector
    )
    canvas = page.locator(selector)
    left, top, cell = (
        float(canvas.get_attribute(a))
        for a in ("data-plot-left", "data-plot-top", "data-cell-px")
    )
    canvas.click(position={"x": left + col * cell, "y": top + (n_rows - row) * cell})


def test_plot_point_from_editor_to_phone_and_scatter(api, web, game, pages):
    gid = game["game"]
    page = pages(api.token)
    page.goto(f"{web}/host/courses/{game['course']}/games/{gid}/questions")
    page.get_by_role("button", name="Add Question").click()
    page.locator("select").first.select_option("plot_point")
    page.get_by_placeholder("Question text…").fill(
        "Where do y = 2x + 1 and y = −x + 7 meet?"
    )
    save = page.get_by_role("button", name="Save Question")
    # A new question has no target: Save waits for a click on the preview.
    page.get_by_test_id("plot-problems").get_by_text(
        "plot_point target must be a grid point inside the plane"
    ).wait_for()
    assert save.is_disabled()

    page.get_by_role("button", name="Add overlay").click()
    for key, value in {"x1": "0", "y1": "1", "x2": "1", "y2": "3"}.items():
        page.get_by_label(f"Overlay 1 {key}").fill(value)
    page.get_by_label("Overlay 1 label").fill("y = 2x + 1")
    tap_grid(page, "[data-testid=plot-scatter]", *TARGET)
    page.get_by_test_id("plot-target").get_by_text("(2, 5)").wait_for()
    assert save.is_enabled()
    save.click()
    page.get_by_text("Target (2, 5) · 20×20 grid").wait_for()

    (q,) = api.get(f"/games/{gid}/questions").json()
    assert q["type"] == "plot_point" and q["grading_type"] == "ACCURACY"
    assert q["answer_data"] == {
        "target": {"x": 2, "y": 5},
        "bands": [{"within": 0, "points": 100}, {"within": 1, "points": 50}],
    }
    assert q["config"]["overlays"] == [
        {"kind": "line", "x1": 0, "y1": 1, "x2": 1, "y2": 3, "label": "y = 2x + 1"}
    ]
    assert q["points_value"] == 100 and q["time_limit_seconds"] == 45

    host, phone = start_game(
        api,
        game,
        lambda: pages(api.token),
        lambda t: pages(t, phone=True),
        web,
        guest_token,
    )
    phone.get_by_text("Tap the grid").wait_for()
    submit = phone.get_by_role("button", name="Submit")
    assert submit.is_disabled()

    # Typed coordinates: the readout follows the panel, snapped to the grid.
    phone.get_by_role("button", name="Type coordinates").click()
    phone.get_by_label("x coordinate").fill("-3.4")
    phone.get_by_label("y coordinate").fill("7")
    phone.get_by_label("y coordinate").press("Enter")
    phone.get_by_text(f"({MINUS}3, 7)").wait_for()
    assert phone.get_by_label("x coordinate").input_value() == f"{MINUS}3"

    # Tapping the target moves the point; the readout shows it before submitting.
    tap_grid(phone, "canvas", *TARGET)
    phone.get_by_text("(2, 5)").wait_for()
    assert phone.get_by_label("x coordinate").input_value() == "2"
    submit.click()
    phone.get_by_text("Answer submitted").wait_for()

    host.get_by_role("button", name="Show Results").click()
    phone.get_by_text("Correct!").wait_for(timeout=8000)
    assert "You: (2, 5) · Target: (2, 5) · Exact · 100 pts" in phone.inner_text("body")
    scatter = host.get_by_test_id("plot-scatter")
    scatter.wait_for()
    assert scatter.get_attribute("aria-label").endswith(", 1 answer")
    assert "Target: (2, 5)" in host.inner_text("body")
    assert not pages.errors, pages.errors


def test_rotation_keeps_timer_and_point(api, web, game, pages):
    """Turning the phone must not restart the timer or drop the point (found by the manual
    checklist: the portrait and landscape layouts used to remount the timer at full time)."""
    r = api.post(
        f"/games/{game['game']}/questions",
        json={
            "type": "plot_point",
            "grading_type": "ACCURACY",
            "prompt": "Plot (2, 5)",
            "config": {"xMin": -10, "xMax": 10, "xStep": 1, "yMin": -10, "yMax": 10, "yStep": 1},
            "answer_data": {
                "target": {"x": 2, "y": 5},
                "bands": [{"within": 0, "points": 100}],
            },
            "time_limit_seconds": 120,
            "points_value": 100,
        },
    )
    assert r.status_code == 201, r.text
    _, phone = start_game(
        api,
        game,
        lambda: pages(api.token),
        lambda t: pages(t, phone=True),
        web,
        guest_token,
    )
    tap_grid(phone, "canvas", *TARGET)
    phone.get_by_text("(2, 5)").wait_for()

    def seconds_left() -> int:
        return int(phone.locator("span.font-mono").inner_text().rstrip("s"))

    phone.wait_for_timeout(4000)
    before = seconds_left()
    assert before <= 117

    for width, height in ((844, 390), (390, 844)):  # landscape, then portrait again
        phone.set_viewport_size({"width": width, "height": height})
        phone.wait_for_timeout(500)
        assert seconds_left() <= before, "rotation restarted the timer"
        phone.get_by_text("(2, 5)").wait_for()
    assert not pages.errors, pages.errors
