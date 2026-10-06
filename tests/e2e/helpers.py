"""Shared steps for the browser tests: images, questions and driving a game."""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw


def picture(text: str, colour: tuple[int, int, int], size=(400, 300)) -> bytes:
    im = Image.new("RGB", size, colour)
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, size[0] - 6, size[1] - 6], outline="white", width=5)
    d.text((20, size[1] // 2 - 20), text, fill="white", font_size=40)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def polygon(sides: int) -> bytes:
    im = Image.new("RGB", (200, 200), (240, 240, 240))
    pts = [
        (
            100 + 80 * math.cos(2 * math.pi * k / sides),
            100 + 80 * math.sin(2 * math.pi * k / sides),
        )
        for k in range(sides)
    ]
    ImageDraw.Draw(im).polygon(pts, fill=(52, 152, 219))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def upload(api, game_id: int, data: bytes) -> str:
    r = api.post(f"/games/{game_id}/images", files={"file": ("x.png", data)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def start_game(
    api, game: dict, host_page_factory, phone_page_factory, web: str, guest_token
):
    """Open a room, put the host screen and one phone in it and start the game.
    Returns (host page, phone page)."""
    room = api.post(
        "/game/rooms", json={"course_id": game["course"], "game_id": game["game"]}
    ).json()["room_code"]
    host = host_page_factory()
    phone = phone_page_factory(guest_token(api, room))
    host.goto(f"{web}/host/game/{room}/lobby")
    phone.goto(f"{web}/player/game/{room}/lobby")
    host.get_by_role("button", name="Start Game").wait_for()
    host.wait_for_function("() => !document.querySelector('button.px-12')?.disabled")
    host.get_by_role("button", name="Start Game").click()
    host.wait_for_url("**/question")
    phone.wait_for_url("**/question")
    return host, phone


def loaded(page, alt: str) -> bool:
    """Whether an <img> with this alt text has finished loading real pixels."""
    return page.evaluate(
        "alt => [...document.images].some(i => i.alt === alt && i.complete && i.naturalWidth > 0)",
        alt,
    )
