"""
Browser end-to-end tests (T5) for the T7 and T8 user interfaces: the host editor, the
host game screens and the player phone screens, driven in a real Chrome by Playwright.

They need the full stack behind nginx (:8080) with freshly built frontends
(`npm run build`), the `playwright` package and Google Chrome (Playwright drives the
installed Chrome through `channel="chrome"`, so `playwright install` is not needed).
Anything missing → the tests are skipped, so CI is unaffected. Run:

    cd tests/e2e && python -m pytest -q

Each test creates its own course and game through the API and deletes the game after.
"""

from __future__ import annotations

import pathlib
import uuid

import httpx
import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent


def pytest_addoption(parser):
    parser.addoption(
        "--web-url",
        default="http://localhost:8080",
        help="nginx URL serving the built apps",
    )
    parser.addoption(
        "--api-url",
        default="http://localhost:8000/api",
        help="backend API URL for test setup",
    )
    parser.addoption("--headed", action="store_true", help="show the browser")


def _env() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    return {
        k.strip(): v.strip()
        for k, _, v in (line.partition("=") for line in path.read_text().splitlines())
        if k.strip() and not k.strip().startswith("#")
    }


@pytest.fixture(scope="session")
def web(request) -> str:
    url = request.config.getoption("--web-url").rstrip("/")
    try:
        ok = httpx.get(f"{url}/api/health", timeout=3).status_code == 200
    except httpx.HTTPError:
        ok = False
    if not ok:
        pytest.skip(f"nginx not reachable at {url}")
    for app in ("host", "player"):
        if not (ROOT / "frontend" / app / "dist" / "index.html").exists():
            pytest.skip(f"frontend/{app}/dist is not built (run npm run build)")
    return url


@pytest.fixture(scope="session")
def api(request) -> httpx.Client:
    env = _env()
    base = request.config.getoption("--api-url").rstrip("/")
    r = httpx.post(
        f"{base}/auth/login",
        json={
            "username": env.get("ADMIN_USERNAME", "admin"),
            "password": env.get("ADMIN_PASSWORD", "changeme123"),
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    client = httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        timeout=30,
    )
    client.token = r.json()["access_token"]  # type: ignore[attr-defined]
    yield client
    client.close()


@pytest.fixture(scope="session")
def browser(request, web):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(
                channel="chrome", headless=not request.config.getoption("--headed")
            )
        except Exception as exc:  # Chrome not installed
            pytest.skip(f"Google Chrome not available to Playwright: {exc}")
        yield b
        b.close()


@pytest.fixture()
def game(api):
    """A fresh course and empty game; deleted after the test."""
    tag = uuid.uuid4().hex[:6]
    course = api.post(
        "/admin/courses", json={"name": f"E2E {tag}", "semester": "Test"}
    ).json()["id"]
    game_id = api.post(
        "/admin/games", json={"course_id": course, "title": f"E2E game {tag}"}
    ).json()["id"]
    yield {"course": course, "game": game_id}
    api.delete(f"/admin/games/{game_id}")


@pytest.fixture()
def pages(browser, api):
    """Factory for pages logged in with a token, plus a list of uncaught page errors."""
    contexts, errors = [], []

    def make(token: str, *, phone: bool = False, block=(), delay=()):
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844}
            if phone
            else {"width": 1400, "height": 950},
            is_mobile=phone,
        )
        contexts.append(ctx)
        ctx.add_init_script(f"localStorage.setItem('token', '{token}')")
        for image_id in block:
            ctx.route(f"**/api/images/{image_id}*", lambda route: route.abort())
        for image_id in delay:  # never answered during the test: stays "loading"
            ctx.route(f"**/api/images/{image_id}*", lambda route: None)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        return page

    make.errors = errors  # type: ignore[attr-defined]
    yield make
    for ctx in contexts:
        ctx.close()


def guest_token(api, room_code: str) -> str:
    tag = uuid.uuid4().hex[:6]
    r = httpx.post(
        f"{str(api.base_url).rstrip('/')}/auth/guest",
        json={
            "display_name": f"Phone {tag}",
            "email": f"p.{tag}@example.com",
            "room_code": room_code,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
