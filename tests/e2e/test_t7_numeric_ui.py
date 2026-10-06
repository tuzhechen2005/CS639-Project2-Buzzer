"""T7 numeric_estimate in the browser: authored with the host editor's form (MR C) and
answered on a phone with the number field, with the banded result shown back."""

from __future__ import annotations

from .conftest import guest_token
from .helpers import start_game


def test_numeric_question_from_editor_form_to_phone_result(api, web, game, pages):
    gid = game["game"]
    page = pages(api.token)
    page.goto(f"{web}/host/courses/{game['course']}/games/{gid}/questions")
    page.get_by_role("button", name="Add Question").click()
    page.locator("select").first.select_option("numeric_estimate")
    page.get_by_placeholder("Question text…").fill(
        "How many keys does a standard piano have?"
    )
    page.get_by_placeholder("e.g. 1665").fill("88")
    page.get_by_placeholder("steps, years, m…").fill("keys")
    page.get_by_role("button", name="Save Question").click()
    page.get_by_text("Target:").wait_for()
    (q,) = api.get(f"/games/{gid}/questions").json()
    assert q["type"] == "numeric_estimate" and q["config"] == {"unit": "keys"}
    assert q["answer_data"] == {
        "target": 88,
        "mode": "relative",
        "bands": [
            {"within": 5, "points": 100},
            {"within": 15, "points": 50},
            {"within": 30, "points": 25},
        ],
    }
    assert q["points_value"] == 100 and q["time_limit_seconds"] == 45

    host, phone = start_game(
        api,
        game,
        lambda: pages(api.token),
        lambda t: pages(t, phone=True),
        web,
        guest_token,
    )
    box = phone.get_by_label("Your estimate")
    submit = phone.locator("form button[type=submit]")
    box.fill("abc")
    phone.get_by_text("Enter a number").wait_for()
    assert submit.is_disabled()
    box.fill("95")  # 8 % off: the second band
    phone.get_by_text("= 95 keys").wait_for()
    submit.click()
    phone.get_by_text("Answer locked in!").wait_for()

    host.get_by_role("button", name="Show Results").click()
    try:
        phone.get_by_text("Close!").wait_for(timeout=8000)
    except Exception:
        phone.screenshot(
            path="/private/tmp/claude-501/-Users-tuzhechen-Documents-buzzer-45/01ab05bb-826f-46a8-b318-5fac4375efbf/scratchpad/dbg_phone.png"
        )
        host.screenshot(
            path="/private/tmp/claude-501/-Users-tuzhechen-Documents-buzzer-45/01ab05bb-826f-46a8-b318-5fac4375efbf/scratchpad/dbg_host.png"
        )
        print("PHONE URL", phone.url, "TEXT", phone.inner_text("body")[:300])
        print("HOST URL", host.url, "TEXT", host.inner_text("body")[:300])
        raise
    assert "50" in phone.inner_text("body")
    assert not pages.errors
