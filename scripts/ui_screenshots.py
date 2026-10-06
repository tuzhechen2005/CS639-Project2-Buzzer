#!/usr/bin/env python3
"""
Screenshots of the key screens of the host, player and admin apps, for the T9 before/after
evidence in docs/ui/.

The data is seeded through the API (a course with a host, a roster, a game with every question
type including the T7 numeric_estimate and plot_point types and T8 images), then the screens
are visited and one game is played with a host and two phones. Running it again with the same
arguments gives the same screens, so before and after shots are directly comparable:

    npm run build                       # nginx serves frontend/*/dist
    pip install playwright httpx Pillow # Google Chrome is driven directly, no browser download
    python scripts/ui_screenshots.py --out docs/ui/before
    python scripts/ui_screenshots.py --out docs/ui/after-light --color-scheme light
    python scripts/ui_screenshots.py --out docs/ui/after-dark  --color-scheme dark

`--color-scheme` emulates the OS preference (prefers-color-scheme), which is how a first visit
chooses its theme. File names are the same in every folder.

Needs the stack running behind nginx (:8080) and the backend on :8000, with ADMIN_USERNAME and
ADMIN_PASSWORD in .env. The seeded games and users are deleted afterwards (`--keep` keeps them);
the demo course is reused between runs.
"""

from __future__ import annotations

import argparse
import io
import math
import pathlib
import sys
import uuid

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
COURSE_NAME = "Intro to Data Science"
HOST_USERNAME = "prof_rivera"
HOST_PASSWORD = "demo-password-1"
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}


# ---------------------------------------------------------------------------
# Pictures drawn for the demo game
# ---------------------------------------------------------------------------


def _png(image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def make_images() -> dict[str, bytes]:
    from PIL import Image, ImageDraw

    dots = Image.new("RGB", (800, 500), (250, 247, 240))
    draw = ImageDraw.Draw(dots)
    colours = [
        (231, 76, 60),
        (52, 152, 219),
        (46, 204, 113),
        (241, 196, 15),
        (155, 89, 182),
    ]
    placed: list[tuple[int, int]] = []
    state = 7
    while len(placed) < 60:
        state = (state * 1103515245 + 12345) % (2**31)
        x = 20 + state % 760
        state = (state * 1103515245 + 12345) % (2**31)
        y = 20 + state % 460
        if all((x - a) ** 2 + (y - b) ** 2 > 28**2 for a, b in placed):
            placed.append((x, y))
            draw.ellipse(
                [x - 10, y - 10, x + 10, y + 10], fill=colours[len(placed) % 5]
            )

    def polygon(sides: int, colour: tuple[int, int, int]) -> bytes:
        image = Image.new("RGB", (300, 300), (245, 245, 245))
        points = [
            (
                150 + 115 * math.cos(2 * math.pi * k / sides - math.pi / 2),
                155 + 115 * math.sin(2 * math.pi * k / sides - math.pi / 2),
            )
            for k in range(sides)
        ]
        ImageDraw.Draw(image).polygon(
            points, fill=colour, outline=(40, 40, 40), width=4
        )
        return _png(image)

    plane = Image.new("RGB", (400, 400), (235, 245, 255))
    draw = ImageDraw.Draw(plane)
    for i in range(0, 400, 40):
        draw.line([(i, 0), (i, 400)], fill=(205, 220, 238))
        draw.line([(0, i), (400, i)], fill=(205, 220, 238))
    draw.ellipse([150, 150, 250, 250], outline=(120, 160, 220), width=4)
    return {
        "dots": _png(dots),
        "triangle": polygon(3, (241, 196, 15)),
        "square": polygon(4, (231, 76, 60)),
        "hexagon": polygon(6, (46, 204, 113)),
        "octagon": polygon(8, (52, 152, 219)),
        "plane": _png(plane),
    }


# ---------------------------------------------------------------------------
# Seeding through the API
# ---------------------------------------------------------------------------


def read_env() -> dict[str, str]:
    path = ROOT / ".env"
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                env[key.strip()] = value.strip()
    return env


class Api:
    def __init__(self, base: str, token: str | None = None):
        self.client = httpx.Client(base_url=base, timeout=30)
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def call(self, method: str, path: str, ok: tuple[int, ...] = (200, 201, 204), **kw):
        r = self.client.request(method, path, headers=self.headers, **kw)
        if r.status_code not in ok:
            raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return (
            r.json()
            if r.content and "json" in r.headers.get("content-type", "")
            else None
        )

    def login(self, username: str, password: str) -> str:
        data = self.call(
            "POST", "/auth/login", json={"username": username, "password": password}
        )
        return data["access_token"]


def question(kind, grading, prompt, config, answer, points, seconds):
    return {
        "type": kind,
        "grading_type": grading,
        "prompt": prompt,
        "config": config,
        "answer_data": answer,
        "time_limit_seconds": seconds,
        "points_value": points,
    }


def game_questions(img: dict[str, str]) -> dict[str, list[dict]]:
    mc = question(
        "multiple_choice",
        "ACCURACY",
        "Which of these shapes has the most sides?",
        {
            "options": ["Triangle", "Square", "Hexagon", "Octagon"],
            "option_image_ids": [
                img["triangle"],
                img["square"],
                img["hexagon"],
                img["octagon"],
            ],
        },
        {"answer_points": [0, 0, 0, 1]},
        1,
        30,
    )
    numeric = question(
        "numeric_estimate",
        "ACCURACY",
        "Roughly how many dots are in this picture?",
        {"unit": "dots", "image_id": img["dots"]},
        {
            "target": 60,
            "mode": "relative",
            "bands": [{"within": 10, "points": 100}, {"within": 25, "points": 50}],
        },
        100,
        45,
    )
    plot = question(
        "plot_point",
        "ACCURACY",
        "Tap the vertex of the parabola.",
        {
            "xMin": -5,
            "xMax": 5,
            "xStep": 1,
            "yMin": -5,
            "yMax": 5,
            "yStep": 1,
            "xLabel": "x",
            "yLabel": "y",
            "image_id": img["plane"],
            "overlays": [
                {
                    "kind": "line",
                    "x1": 0,
                    "y1": 1,
                    "x2": 1,
                    "y2": 3,
                    "label": "y = 2x + 1",
                },
                {
                    "kind": "polynomial",
                    "coefficients": [-3, -2, 1],
                    "label": "y = x² − 2x − 3",
                },
            ],
        },
        {
            "target": {"x": 1, "y": -4},
            "bands": [{"within": 0, "points": 100}, {"within": 1, "points": 50}],
        },
        100,
        45,
    )
    tf = question(
        "true_false",
        "ACCURACY",
        "A mean is always one of the values in the data set.",
        {},
        {"answer_points": {"true": 0, "false": 1}},
        1,
        20,
    )
    ms = question(
        "multi_select",
        "ACCURACY",
        "Which of these are measures of spread? Select all that apply.",
        {"options": ["Range", "Median", "Standard deviation", "Mode"]},
        {"answer_points": [0.5, -0.5, 0.5, -0.5]},
        1,
        30,
    )
    fitb = question(
        "fill_in_the_blank",
        "COMPLETENESS",
        "In one word: what is the most confusing topic so far?",
        {},
        {},
        1,
        30,
    )
    return {"editor": [mc, numeric, plot, tf, ms, fitb], "live": [mc, numeric, plot]}


class Seed:
    def __init__(self, api: Api):
        self.api = api
        self.game_ids: list[int] = []
        self.user_ids: list[str] = []

    def course(self) -> int:
        for c in self.api.call("GET", "/admin/courses"):
            if c["name"] == COURSE_NAME:
                return c["id"]
        created = self.api.call(
            "POST",
            "/admin/courses",
            json={"name": COURSE_NAME, "semester": "Fall 2026"},
        )
        return created["id"]

    def host_user(self, course_id: int) -> None:
        users = self.api.call("GET", "/admin/users")
        existing = next((u for u in users if u.get("username") == HOST_USERNAME), None)
        if existing is None:
            existing = self.api.call(
                "POST",
                "/admin/users",
                json={
                    "username": HOST_USERNAME,
                    "display_name": "Prof. Rivera",
                    "password": HOST_PASSWORD,
                    "email": "rivera@example.edu",
                },
            )
        self.user_ids.append(existing["id"])
        self.api.call(
            "POST",
            f"/admin/users/{existing['id']}/course-access",
            json={"course_id": course_id, "role": "HOST"},
            ok=(200, 201, 204, 409),
        )

    def extra_users(self, course_id: int) -> None:
        names = [
            ("ana_lopez", "Ana Lopez"),
            ("ben_okafor", "Ben Okafor"),
            ("chen_wei", "Chen Wei"),
        ]
        have = {u.get("username") for u in self.api.call("GET", "/admin/users")}
        for username, display in names:
            if username in have:
                continue
            user = self.api.call(
                "POST",
                "/admin/users",
                json={
                    "username": username,
                    "display_name": display,
                    "password": "demo-password-2",
                    "email": f"{username}@example.edu",
                },
            )
            self.user_ids.append(user["id"])
            self.api.call(
                "POST",
                f"/admin/users/{user['id']}/course-access",
                json={"course_id": course_id, "role": "PLAYER"},
                ok=(200, 201, 204, 409),
            )

    def roster(self, course_id: int) -> None:
        students = [
            ("alopez", "Ana Lopez"),
            ("bokafor", "Ben Okafor"),
            ("cwei", "Chen Wei"),
            ("dsmith", "Dana Smith"),
            ("ekim", "Eun Kim"),
            ("fnguyen", "Fiona Nguyen"),
            ("gpatel", "Gita Patel"),
            ("hjones", "Hugo Jones"),
        ]
        rows = [
            {"netid": n, "full_name": f, "email": f"{n}@example.edu"}
            for n, f in students
        ]
        self.api.call(
            "POST", f"/courses/{course_id}/roster/import", json={"rows": rows}
        )

    def game(
        self,
        course_id: int,
        title: str,
        questions: list[dict],
        images: dict[str, bytes],
    ):
        game = self.api.call(
            "POST",
            "/admin/games",
            json={
                "course_id": course_id,
                "title": title,
                "description": "Reading graphs and estimating numbers.",
            },
        )
        self.game_ids.append(game["id"])
        ids: dict[str, str] = {}
        for name, data in images.items():
            ids[name] = self.api.call(
                "POST",
                f"/games/{game['id']}/images",
                files={"file": (f"{name}.png", data)},
            )["id"]
        for body in questions:
            self.api.call(
                "POST", f"/admin/games/{game['id']}/questions", json=resolve(body, ids)
            )
        return game["id"]

    def cleanup(self) -> None:
        for game_id in self.game_ids:
            self.api.call("DELETE", f"/admin/games/{game_id}", ok=(200, 204, 404))
        for user_id in self.user_ids:
            self.api.call("DELETE", f"/admin/users/{user_id}", ok=(200, 204, 404))


def resolve(body: dict, ids: dict[str, str]) -> dict:
    """Replace image names by the ids the library assigned."""
    config = dict(body["config"])
    if "image_id" in config:
        config["image_id"] = ids[config["image_id"]]
    if "option_image_ids" in config:
        config["option_image_ids"] = [ids[n] for n in config["option_image_ids"]]
    return {**body, "config": config}


# ---------------------------------------------------------------------------
# The screens
# ---------------------------------------------------------------------------


def shoot(
    page, out: pathlib.Path, name: str, *, full: bool = False, wait: int = 900
) -> None:
    page.wait_for_timeout(wait)
    page.screenshot(path=str(out / f"{name}.png"), full_page=full)
    print("  ", name)


def tap_plane(page, col: int, row: int, n_rows: int) -> None:
    canvas = page.locator("canvas").first
    left = float(canvas.get_attribute("data-plot-left"))
    top = float(canvas.get_attribute("data-plot-top"))
    cell = float(canvas.get_attribute("data-cell-px"))
    box = canvas.bounding_box()
    page.mouse.click(
        box["x"] + left + col * cell, box["y"] + top + (n_rows - row) * cell
    )


def run(args: argparse.Namespace) -> None:
    from playwright.sync_api import sync_playwright

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = read_env()
    api = Api(args.api_url)
    admin_token = api.login(
        env.get("ADMIN_USERNAME", "admin"), env.get("ADMIN_PASSWORD", "changeme123")
    )
    api = Api(args.api_url, admin_token)
    seed = Seed(api)
    course_id = seed.course()
    seed.host_user(course_id)
    seed.extra_users(course_id)
    seed.roster(course_id)
    images = make_images()
    qs = game_questions({k: k for k in images})
    editor_id = seed.game(course_id, "Graphs and Guesses", qs["editor"], images)
    live_id = seed.game(course_id, "Class Warm-up", qs["live"], images)
    host_token = Api(args.api_url).login(HOST_USERNAME, HOST_PASSWORD)
    host_api = Api(args.api_url, host_token)
    web = args.web_url.rstrip("/")

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome", headless=not args.headed)
            except Exception as exc:
                raise SystemExit(
                    f"Google Chrome is needed (driven by Playwright): {exc}"
                )

            def context(size, token=None, phone=False):
                ctx = browser.new_context(
                    viewport=size,
                    is_mobile=phone,
                    has_touch=phone,
                    color_scheme=args.color_scheme,
                )
                if token:
                    ctx.add_init_script(f"localStorage.setItem('token', '{token}')")
                return ctx

            errors: list[str] = []

            def page_of(ctx):
                page = ctx.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                return page

            # --- Logins and the admin/host management screens --------------------------
            print("host app")
            anon = page_of(context(DESKTOP))
            anon.goto(f"{web}/host/login")
            shoot(anon, out, "h01-login")
            host = page_of(context(DESKTOP, host_token))
            host.goto(f"{web}/host/home")
            shoot(host, out, "h02-home")
            host.goto(f"{web}/host/courses/{course_id}/games")
            shoot(host, out, "h03-games")
            host.goto(f"{web}/host/courses/{course_id}/games/{editor_id}/questions")
            host.get_by_text("Image library").wait_for()
            shoot(host, out, "h04-editor-questions", full=True, wait=1500)
            host.get_by_role("button", name="Add Question").click()
            for kind, label in (
                ("multiple_choice", "h05-editor-form-multiple-choice"),
                ("numeric_estimate", "h06-editor-form-numeric"),
                ("plot_point", "h07-editor-form-plot-point"),
            ):
                host.locator("select").first.select_option(kind)
                host.get_by_placeholder("Question text…").fill(
                    "Example prompt for the form"
                )
                shoot(host, out, label, full=True, wait=500)
            host.goto(f"{web}/host/courses/{course_id}/roster")
            shoot(host, out, "h08-roster", full=True)

            print("admin app")
            anon_admin = page_of(context(DESKTOP))
            anon_admin.goto(f"{web}/admin/login")
            shoot(anon_admin, out, "a01-login")
            admin = page_of(context(DESKTOP, admin_token))
            admin.goto(f"{web}/admin/users")
            shoot(admin, out, "a02-users", full=True)
            admin.get_by_text("Prof. Rivera").first.click()
            shoot(admin, out, "a03-user-detail", full=True)
            admin.goto(f"{web}/admin/courses")
            shoot(admin, out, "a04-courses", full=True)

            print("player app (before joining)")
            room = host_api.call(
                "POST", "/game/rooms", json={"course_id": course_id, "game_id": live_id}
            )["room_code"]
            phone_anon = page_of(context(PHONE, phone=True))
            phone_anon.goto(f"{web}/player/join")
            shoot(phone_anon, out, "p01-join")
            phone_anon.goto(f"{web}/player/name/{room}")
            shoot(phone_anon, out, "p02-name")

            # --- One game: host screen and two phones ------------------------------------
            print("live game")
            guests = []
            for name in ("Ana", "Ben"):
                tag = uuid.uuid4().hex[:6]
                guests.append(
                    Api(args.api_url).call(
                        "POST",
                        "/auth/guest",
                        json={
                            "display_name": name,
                            "email": f"{name.lower()}.{tag}@example.com",
                            "room_code": room,
                        },
                    )["access_token"]
                )
            screen = page_of(context(DESKTOP, host_token))
            phone = page_of(context(PHONE, guests[0], phone=True))
            other = page_of(context(PHONE, guests[1], phone=True))
            screen.goto(f"{web}/host/game/{room}/lobby")
            phone.goto(f"{web}/player/game/{room}/lobby")
            other.goto(f"{web}/player/game/{room}/lobby")
            shoot(screen, out, "h09-lobby", wait=1800)
            shoot(phone, out, "p03-lobby", wait=100)
            screen.get_by_role("button", name="Start Game").click()
            for page in (screen, phone, other):
                page.wait_for_url("**/question")

            # Q1: multiple choice with picture options
            shoot(screen, out, "h10-question-multiple-choice", wait=1500)
            shoot(phone, out, "p04-question-multiple-choice", full=True, wait=100)
            phone.get_by_role("button", name="Octagon").click()
            shoot(phone, out, "p05-feedback", wait=500)
            other.get_by_role("button", name="Hexagon").click()
            other.wait_for_timeout(300)
            screen.get_by_role("button", name="Show Results").click()
            screen.wait_for_url("**/results")
            shoot(screen, out, "h11-results-multiple-choice", full=True, wait=1500)
            shoot(phone, out, "p06-results", wait=500)
            screen.get_by_role("button", name="Next Question").click()
            for page in (screen, phone, other):
                page.wait_for_url("**/question")

            # Q2: numeric estimate with a picture prompt
            shoot(screen, out, "h12-question-numeric", wait=1500)
            shoot(phone, out, "p07-question-numeric", wait=300)
            phone.get_by_label("Your estimate").fill("58")
            phone.locator("form button[type=submit]").click()
            other.get_by_label("Your estimate").fill("90")
            other.locator("form button[type=submit]").click()
            phone.wait_for_timeout(300)
            screen.get_by_role("button", name="Show Results").click()
            screen.wait_for_url("**/results")
            shoot(screen, out, "h13-results-numeric", full=True, wait=1500)
            shoot(phone, out, "p08-results-numeric", wait=500)
            screen.get_by_role("button", name="Next Question").click()
            for page in (screen, phone, other):
                page.wait_for_url("**/question")

            # Q3: plot the point on a canvas with a picture behind it
            shoot(screen, out, "h14-question-plot-point", wait=1800)
            shoot(phone, out, "p09-question-plot-point", wait=1000)
            tap_plane(phone, 7, 1, 10)  # (2, -4): one cell from the vertex (1, -4)
            shoot(phone, out, "p10-question-plot-point-placed", wait=400)
            phone.get_by_role("button", name="Submit").click()
            tap_plane(other, 6, 1, 10)  # (1, -4): exact
            other.get_by_role("button", name="Submit").click()
            phone.wait_for_timeout(400)
            screen.get_by_role("button", name="Show Results").click()
            screen.wait_for_url("**/results")
            shoot(screen, out, "h15-results-plot-point", full=True, wait=1800)
            shoot(phone, out, "p11-results-plot-point", wait=500)
            screen.get_by_role("button", name="Show Final Results").click()
            screen.wait_for_url("**/gameover")
            phone.wait_for_url("**/gameover")
            shoot(screen, out, "h16-game-over", full=True, wait=1800)
            shoot(phone, out, "p12-game-over", full=True, wait=800)

            # --- Screens that show the finished session ---------------------------------
            host.goto(f"{web}/host/courses/{course_id}/sessions")
            shoot(host, out, "h17-sessions", full=True)
            admin.goto(f"{web}/admin/guests")
            shoot(admin, out, "a05-guests", full=True)
            admin.goto(f"{web}/admin/sessions")
            shoot(admin, out, "a06-sessions", full=True)
            browser.close()
            print("page errors:", errors or "none")
    finally:
        if not args.keep:
            seed.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out", required=True, help="folder for the PNG files, e.g. docs/ui/before"
    )
    parser.add_argument("--color-scheme", choices=["dark", "light"], default="dark")
    parser.add_argument("--web-url", default="http://localhost:8080")
    parser.add_argument("--api-url", default="http://localhost:8000/api")
    parser.add_argument(
        "--keep", action="store_true", help="keep the seeded games and users"
    )
    parser.add_argument("--headed", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
