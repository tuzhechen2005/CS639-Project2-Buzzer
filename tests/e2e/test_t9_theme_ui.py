"""T9 light/dark theme in the three apps (docs/plans/t9-theming.md): a first visit follows the OS,
the toggle flips the theme and the choice survives a reload, one choice is shared by the apps on
:8080 (picked up on the next load, never live), the toggle is on every screen except the player's
question screen, and nothing throws."""

from __future__ import annotations

import re

import pytest

from .conftest import guest_token
from .helpers import start_game

# A signed-out page in each app, so these tests need no account.
APPS = {"host": "/host/login", "player": "/player/join", "admin": "/admin/login"}
KEY = "buzzer-theme"


@pytest.fixture()
def themed(browser):
    """Factory for browser contexts with a given OS colour scheme, plus a list of page errors."""
    contexts, errors = [], []

    def make(scheme: str, *, phone: bool = False, token: str | None = None):
        ctx = browser.new_context(
            color_scheme=scheme,
            viewport={"width": 390, "height": 844}
            if phone
            else {"width": 1440, "height": 900},
            is_mobile=phone,
        )
        contexts.append(ctx)
        if token:
            # try: the init script also runs on the first about:blank, where storage is blocked
            ctx.add_init_script(
                f"try {{ localStorage.setItem('token', '{token}') }} catch {{}}"
            )
        ctx.on("page", lambda p: p.on("pageerror", lambda e: errors.append(str(e))))
        return ctx

    make.errors = errors  # type: ignore[attr-defined]
    yield make
    for ctx in contexts:
        ctx.close()


def toggle(page):
    return page.get_by_role("button", name="Dark theme", exact=True)


def theme(page) -> str:
    return page.evaluate("document.documentElement.dataset.theme")


def channels(colour: str) -> list[str]:
    return re.findall(r"\d+", colour)


def check_applied(page, expected: str) -> None:
    """data-theme, color-scheme, the toggle's state and the meta tag all agree with `expected`."""
    assert theme(page) == expected
    assert page.evaluate("document.documentElement.style.colorScheme") == expected
    button = toggle(page)
    button.wait_for()
    assert button.get_attribute("aria-pressed") == (
        "true" if expected == "dark" else "false"
    )
    meta = page.evaluate("document.querySelector('meta[name=\"theme-color\"]').content")
    body = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert meta and channels(meta) == channels(body), (meta, body)


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_first_visit_follows_the_os(themed, web, app, scheme):
    page = themed(scheme, phone=app == "player").new_page()
    page.goto(web + APPS[app])
    check_applied(page, scheme)
    assert page.evaluate(f"localStorage.getItem('{KEY}')") is None
    assert not themed.errors, themed.errors


@pytest.mark.parametrize("app", APPS)
def test_toggle_flips_the_theme_and_survives_a_reload(themed, web, app):
    page = themed("dark", phone=app == "player").new_page()
    page.goto(web + APPS[app])
    check_applied(page, "dark")
    dark_page = page.evaluate("getComputedStyle(document.body).backgroundColor")

    toggle(page).click()
    check_applied(page, "light")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") != dark_page
    assert page.evaluate(f"localStorage.getItem('{KEY}')") == "light"

    page.reload()
    check_applied(page, "light")  # the saved choice beats the dark OS

    toggle(page).click()
    check_applied(page, "dark")
    page.reload()
    check_applied(page, "dark")
    assert not themed.errors, themed.errors


def test_a_choice_in_admin_reaches_the_host_on_its_next_load(themed, web):
    ctx = themed("light")  # one context = one origin's localStorage, as on :8080
    host = ctx.new_page()
    host.goto(web + APPS["host"])
    check_applied(host, "light")

    admin = ctx.new_page()
    admin.goto(web + APPS["admin"])
    toggle(admin).click()
    check_applied(admin, "dark")

    # No live sync: an open projector tab keeps its theme until it loads again.
    host.wait_for_timeout(300)
    assert theme(host) == "light"
    host.reload()
    check_applied(host, "dark")

    player = ctx.new_page()
    player.goto(web + APPS["player"])
    check_applied(player, "dark")
    assert not themed.errors, themed.errors


def test_the_toggle_is_on_every_signed_in_screen(themed, web, api, game):
    ctx = themed("light", token=api.token)
    page = ctx.new_page()
    for path in (
        "/host/home",
        f"/host/courses/{game['course']}/games",
        f"/host/courses/{game['course']}/games/{game['game']}/questions",
        "/admin/users",
        "/admin/courses",
    ):
        page.goto(web + path)
        check_applied(page, "light")
        assert toggle(page).count() == 1, path
    assert not themed.errors, themed.errors


def test_the_player_toggle_hides_on_the_question_screen(api, web, game, pages):
    r = api.post(
        f"/games/{game['game']}/questions",
        json={
            "type": "true_false",
            "grading_type": "ACCURACY",
            "prompt": "Is the sky blue?",
            "config": {},
            "answer_data": {"answer_points": {"true": 1, "false": 0}},
            "time_limit_seconds": 60,
            "points_value": 1,
        },
    )
    assert r.status_code == 201, r.text
    host, phone = start_game(
        api,
        game,
        lambda: pages(api.token),
        lambda t: pages(t, phone=True),
        web,
        guest_token,
    )
    # Host: the toggle lives in the QR panel on every game screen.
    assert toggle(host).count() == 1

    # Phone: none while answering, back as soon as the answer is in.
    phone.get_by_role("button", name="True").wait_for()
    assert toggle(phone).count() == 0
    phone.get_by_role("button", name="True").click()
    phone.wait_for_url("**/feedback")
    toggle(phone).wait_for()

    # Flipping it on the phone recolours the page without leaving the game.
    toggle(phone).click()
    assert theme(phone) == "dark"
    host.get_by_role("button", name="Show Results").click()
    phone.wait_for_url("**/results")
    assert theme(phone) == "dark" and toggle(phone).count() == 1
    assert toggle(host).count() == 1
    assert not pages.errors, pages.errors
