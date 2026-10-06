"""Question prompts show their formatting (<b>, <i>, <u>, <br>) and the characters the server
stores as entities (<, >, &) on the host screens and the phone's game-over list, instead of the
raw tags and codes."""

from __future__ import annotations

from .conftest import guest_token
from .helpers import start_game

PROMPT = "Is x < 5 & y > 2 the <b>right</b> <i>answer</i>?"
SHOWN = "Is x < 5 & y > 2 the right answer?"


def test_prompt_formatting_on_host_and_phone(api, web, game, pages):
    r = api.post(
        f"/games/{game['game']}/questions",
        json={
            "type": "true_false",
            "grading_type": "ACCURACY",
            "prompt": PROMPT,
            "config": {},
            "answer_data": {"answer_points": {"true": 1, "false": 0}},
            "time_limit_seconds": 60,
            "points_value": 1,
        },
    )
    assert r.status_code == 201, r.text
    # The server stores the sanitized form: tags kept, other characters as entities.
    assert "&lt;" in r.json()["prompt"] and "<b>right</b>" in r.json()["prompt"]

    def check(page, selector: str) -> None:
        el = page.locator(selector, has_text="right").first
        el.wait_for()
        assert el.inner_text().replace("\n", " ").strip() == SHOWN
        assert el.locator("b", has_text="right").count() == 1
        assert el.locator("i", has_text="answer").count() == 1
        assert "&lt;" not in el.inner_text() and "<b>" not in el.inner_text()

    editor = pages(api.token)
    editor.goto(f"{web}/host/courses/{game['course']}/games/{game['game']}/questions")
    check(editor, "p")

    host, phone = start_game(
        api, game, lambda: pages(api.token), lambda t: pages(t, phone=True), web, guest_token
    )
    check(host, "h2")
    phone.get_by_role("button", name="True").click()
    host.get_by_role("button", name="Show Results").click()
    check(host, "p")
    host.get_by_role("button", name="Show Final Results").click()
    host.wait_for_url("**/gameover")
    check(host, "p")
    phone.wait_for_url("**/gameover")
    check(phone, "p")
    assert not pages.errors, pages.errors
