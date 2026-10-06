"""
T8 images (docs/plans/t8-image-support.md §I, integration part): upload, read, list,
replace and delete; permissions and check order; quotas; question references;
duplicate, export and import; the write protocol under forced lock overlap; the
migration's LONGBLOB. Runs against the backend on :8000 like the other integration
tests (nginx's limits are tested separately in test_images_nginx.py).

Every test builds its own courses, users and games through the `world` fixture of
test_host_management.py and removes the games and users it created.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import random
import struct
import time
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import httpx
import pymysql
from PIL import Image

from .engine.socket_client import TestSocketClient
from . import test_host_management
from .test_host_management import (
    MC_QUESTION,
    World,
    err,
    mysql,
    play_one_answer,
    redis_del_room,
)

world = test_host_management.world  # the shared pytest fixture

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
MIB = 1024 * 1024


# ---------------------------------------------------------------------------
# Image factories
# ---------------------------------------------------------------------------


def enc(img: Image.Image, fmt: str = "PNG", **kw) -> bytes:
    out = BytesIO()
    img.save(out, fmt, **kw)
    return out.getvalue()


_counter = iter(range(1, 10**6))


def png(size: tuple[int, int] = (40, 30), fmt: str = "PNG") -> bytes:
    """A small image with a colour no other call returns, so its bytes are unique."""
    n = next(_counter) + random.randrange(1 << 20)
    return enc(Image.new("RGB", size, (n & 255, (n >> 8) & 255, (n >> 16) & 255)), fmt)


def noise_png(side: int, seed: int) -> bytes:
    rnd = random.Random(seed)
    raw = bytes(rnd.getrandbits(8) for _ in range(side * side * 3))
    return enc(Image.frombytes("RGB", (side, side), raw))


def pixel_bomb() -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", 5000, 5000, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")


# ---------------------------------------------------------------------------
# REST helpers
# ---------------------------------------------------------------------------


def upload(w: World, game_id: int, data: bytes, token: str | None = None) -> httpx.Response:
    return w.req("POST", f"/games/{game_id}/images", token, files={"file": ("x.bin", data, "application/octet-stream")})


def replace(w: World, game_id: int, image_id: str, data: bytes, token: str | None = None) -> httpx.Response:
    return w.req(
        "PUT", f"/games/{game_id}/images/{image_id}", token, files={"file": ("x.bin", data, "application/octet-stream")}
    )


def uploaded(w: World, game_id: int, data: bytes | None = None, status: int = 201) -> dict:
    r = upload(w, game_id, data if data is not None else png())
    assert r.status_code == status, r.text
    return r.json()


def read(w: World, image_id: str, **headers) -> httpx.Response:
    """The public read endpoint, without a token."""
    return httpx.get(f"{w.base}/api/images/{image_id}", headers=headers, timeout=15.0)


def listing(w: World, game_id: int, token: str | None = None) -> list[dict]:
    return w.ok("GET", f"/games/{game_id}/images", token)


def new_game(w: World, questions: int = 1) -> tuple[int, list[int]]:
    return w.admin_game(w.course_a, questions=questions)


def mc(config: dict) -> dict:
    return {**MC_QUESTION, "config": {"options": ["A", "B"], **config}}


TF_QUESTION = {
    "type": "true_false",
    "grading_type": "ACCURACY",
    "prompt": "True?",
    "config": {},
    "answer_data": {"answer_points": {"true": 1.0, "false": 0.0}},
    "time_limit_seconds": 30,
    "points_value": 1.0,
}
FITB_QUESTION = {
    "type": "fill_in_the_blank",
    "grading_type": "ACCURACY",
    "prompt": "Name it",
    "config": {},
    "answer_data": {"acceptedAnswers": ["cat"], "answerPoints": [1.0], "editDistance": 0},
    "time_limit_seconds": 30,
    "points_value": 1.0,
}


def image_rows(game_id: int) -> int:
    return int(mysql(f"SELECT COUNT(*) FROM images WHERE game_id = {game_id}"))


def all_image_rows() -> int:
    return int(mysql("SELECT COUNT(*) FROM images"))


# ---------------------------------------------------------------------------
# Upload, read, list
# ---------------------------------------------------------------------------


def test_upload_read_and_list(world: World):
    w = world
    gid, (qid,) = new_game(w)
    for fmt, ctype in (("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
        data = png(fmt=fmt)
        meta = uploaded(w, gid, data)
        assert meta["content_type"] == ctype and meta["game_id"] == gid
        assert set(meta) == {
            "id", "game_id", "content_type", "size_bytes", "width", "height", "sha256", "created_at", "updated_at"
        }
        r = read(w, meta["id"])
        assert r.status_code == 200 and r.content == data
        assert r.headers["content-type"] == ctype
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["etag"] == f'"{meta["sha256"]}"'
        assert r.headers["cache-control"] == "public, max-age=60"
        assert r.headers["content-disposition"] == "inline"
        for inm in (f'"{meta["sha256"]}"', f'"nope", W/"{meta["sha256"]}"', "*"):
            r = read(w, meta["id"], **{"If-None-Match": inm})
            assert r.status_code == 304 and r.content == b"", inm
        assert read(w, meta["id"], **{"If-None-Match": '"nope"'}).status_code == 200

    assert read(w, str(uuid.uuid4())).status_code == 404
    for bad in ("not-an-id", str(uuid.uuid4()).upper(), "1"):
        assert read(w, bad).status_code == 404

    prompt_img, option_img = uploaded(w, gid), uploaded(w, gid)
    w.ok(
        "PUT",
        f"/games/{gid}/questions/{qid}",
        w.host_a,
        json={"config": {"options": ["A", "B"], "image_id": prompt_img["id"], "option_image_ids": [None, option_img["id"]]}},
    )
    items = {i["id"]: i for i in listing(w, gid, w.host_a)}
    assert len(items) == 5
    assert all("data" not in i for i in items.values())
    assert items[prompt_img["id"]]["used_by"] == [qid]
    assert items[option_img["id"]]["used_by"] == [qid]
    assert sum(1 for i in items.values() if i["used_by"] == []) == 3


def test_upload_deduplicates_identical_bytes(world: World):
    w = world
    gid, _ = new_game(w)
    data = png()
    first = uploaded(w, gid, data, status=201)
    second = uploaded(w, gid, data, status=200)
    assert first["id"] == second["id"]
    assert len(listing(w, gid)) == 1


def test_rejections_have_the_exact_status_and_code(world: World):
    w = world
    gid, _ = new_game(w)
    cases = [
        (b"just text", 415, "UNSUPPORTED_IMAGE_TYPE"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', 415, "UNSUPPORTED_IMAGE_TYPE"),
        (enc(Image.new("RGB", (5, 5)), "GIF"), 415, "UNSUPPORTED_IMAGE_TYPE"),
        (noise_png(64, 1)[:3000], 400, "INVALID_IMAGE"),
        (b"\0" * (2 * MIB + 1), 413, "IMAGE_TOO_LARGE"),
        (pixel_bomb(), 413, "IMAGE_TOO_LARGE"),
    ]
    for data, status, code in cases:
        r = upload(w, gid, data)
        assert (r.status_code, err(r)) == (status, code), r.text
        assert r.json()["message"]
    r = w.req("POST", f"/games/{gid}/images", data={"other": "x"})
    assert r.status_code == 422
    assert image_rows(gid) == 0


async def test_order_of_checks(world: World):
    w = world
    gid, _ = new_game(w)
    other_gid, _ = new_game(w)
    other = uploaded(w, other_gid)
    # 403 before the file is looked at.
    assert upload(w, gid, b"not an image", w.host_b).status_code == 403
    # An image of another game is a 404 through this game's path.
    assert replace(w, gid, other["id"], png()).status_code == 404
    assert w.req("DELETE", f"/games/{gid}/images/{other['id']}").status_code == 404
    # On a locked game the file errors still come first; a valid file gets 409.
    mine = uploaded(w, gid)
    await play_one_answer(w, gid, w.course_a, finish=True)
    assert (upload(w, gid, b"text").status_code, upload(w, gid, pixel_bomb()).status_code) == (415, 413)
    assert upload(w, gid, noise_png(64, 1)[:3000]).status_code == 400
    r = upload(w, gid, png())
    assert (r.status_code, err(r)) == (409, "GAME_LOCKED")
    # Even an upload of bytes the game already has is refused, not answered with 200.
    r = upload(w, gid, read(w, mine["id"]).content)
    assert (r.status_code, err(r)) == (409, "GAME_LOCKED")


# ---------------------------------------------------------------------------
# Permissions, locked and live games
# ---------------------------------------------------------------------------


async def test_permissions_locked_and_live(world: World):
    w = world
    gid, _ = new_game(w)
    image = uploaded(w, gid)
    no_grant, _ = w.user(("HOST", w.course_a))  # HOST made after the game: no grant
    room = w.room(gid, w.course_a)
    guest = w.guest(room["room_code"])
    paths = [
        ("GET", f"/games/{gid}/images", None),
        ("POST", f"/games/{gid}/images", png()),
        ("PUT", f"/games/{gid}/images/{image['id']}", png()),
        ("DELETE", f"/games/{gid}/images/{image['id']}", None),
    ]
    for method, path, data in paths:
        files = {"file": ("x", data)} if data else None
        for token, status in ((w.host_b, 403), (no_grant, 403), (guest, 403)):
            assert w.req(method, path, token, files=files).status_code == status, (method, path)
        r = httpx.request(method, f"{w.base}/api{path}", files=files, timeout=10)
        assert r.status_code == 401, (method, path)

    # Live game: every write is 409 GAME_LIVE, also for an admin; reads still work.
    for token in (w.host_a, w.admin):
        for method, path, data in paths[1:]:
            files = {"file": ("x", data)} if data else None
            r = w.req(method, path, token, files=files)
            assert (r.status_code, err(r)) == (409, "GAME_LIVE"), (method, path, r.text)
    redis_del_room(room["room_code"])

    # Granted HOST and admin succeed.
    a = uploaded(w, gid)
    w.ok("DELETE", f"/games/{gid}/images/{a['id']}", w.host_a, status=204)
    r = upload(w, gid, png(), w.host_a)
    assert r.status_code == 201, r.text

    # Locked game: writes refused, list and read still work.
    await play_one_answer(w, gid, w.course_a, finish=True)
    for token in (w.host_a, w.admin):
        for method, path, data in paths[1:]:
            files = {"file": ("x", data)} if data else None
            r = w.req(method, path, token, files=files)
            assert (r.status_code, err(r)) == (409, "GAME_LOCKED"), (method, path, r.text)
    assert len(listing(w, gid, w.host_a)) == 2
    assert read(w, image["id"]).status_code == 200


# ---------------------------------------------------------------------------
# Quotas
# ---------------------------------------------------------------------------


def test_count_quota(world: World):
    w = world
    gid, _ = new_game(w)
    first = png()
    uploaded(w, gid, first)
    for _ in range(49):
        uploaded(w, gid)
    r = upload(w, gid, png())
    assert (r.status_code, err(r)) == (409, "IMAGE_LIMIT")
    # Bytes the game already holds are returned without a quota check.
    assert upload(w, gid, first).status_code == 200
    assert image_rows(gid) == 50


def test_byte_quota_and_replace_does_not_count_twice(world: World):
    w = world
    gid, _ = new_game(w)
    big = [noise_png(830, seed) for seed in range(14)]
    assert all(2 * MIB - 40_000 < len(b) <= 2 * MIB for b in big)
    ids = [uploaded(w, gid, b)["id"] for b in big[:12]]
    r = upload(w, gid, big[12])
    assert (r.status_code, err(r)) == (409, "IMAGE_LIMIT"), r.text
    # Replacing one of the twelve with another image of the same size fits.
    r = replace(w, gid, ids[0], big[13])
    assert r.status_code == 200, r.text
    assert image_rows(gid) == 12


# ---------------------------------------------------------------------------
# References in question configs
# ---------------------------------------------------------------------------


async def test_question_references(world: World):
    w = world
    gid, (qid,) = new_game(w)
    other_gid, _ = new_game(w)
    foreign = uploaded(w, other_gid)
    mine, opt = uploaded(w, gid), uploaded(w, gid)

    def create(body: dict) -> httpx.Response:
        return w.req("POST", f"/games/{gid}/questions", w.host_a, json=body)

    for body in (
        mc({"image_id": foreign["id"]}),
        mc({"option_image_ids": [mine["id"]]}),
        {**TF_QUESTION, "config": {"option_image_ids": [None, None]}},
        mc({"image_id": "img1"}),
        mc({"option_image_ids": [mine["id"], str(uuid.uuid4())]}),
    ):
        r = create(body)
        assert (r.status_code, err(r)) == (422, "INVALID_IMAGE_REFERENCE"), (body, r.text)

    before = w.ok("GET", f"/games/{gid}/questions")[0]
    r = w.req("PUT", f"/games/{gid}/questions/{qid}", w.host_a, json={"config": {"options": ["A", "B"], "image_id": foreign["id"]}})
    assert (r.status_code, err(r)) == (422, "INVALID_IMAGE_REFERENCE")
    # Changing only the type also re-checks the merged config.
    w.ok("PUT", f"/games/{gid}/questions/{qid}", w.host_a, json={"config": {"options": ["A", "B"], "option_image_ids": [opt["id"], None]}})
    # (fill_in_the_blank + COMPLETENESS passes the type's own structure check, if T7's
    # update validation is present, so only the image rule can refuse it.)
    r = w.req(
        "PUT",
        f"/games/{gid}/questions/{qid}",
        w.host_a,
        json={"type": "fill_in_the_blank", "grading_type": "COMPLETENESS"},
    )
    assert (r.status_code, err(r)) == (422, "INVALID_IMAGE_REFERENCE")
    after = w.ok("GET", f"/games/{gid}/questions")[0]
    assert after["type"] == before["type"] == "multiple_choice"
    w.ok("PUT", f"/games/{gid}/questions/{qid}", w.host_a, json={"config": before["config"]})

    # Valid references on every kind of question; admin alias too.
    good_mc = mc({"image_id": mine["id"], "option_image_ids": [opt["id"], None]})
    good_fitb = {**FITB_QUESTION, "config": {"image_id": mine["id"]}}
    w.ok("POST", f"/games/{gid}/questions", w.host_a, json=good_mc, status=201)
    w.ok("POST", f"/admin/games/{gid}/questions", json=good_fitb, status=201)
    configs = [q["config"] for q in w.ok("GET", f"/games/{gid}/questions")]
    assert configs[1] == good_mc["config"] and configs[2] == good_fitb["config"]
    w.ok("DELETE", f"/games/{gid}/questions/{qid}", w.host_a, status=204)

    # The ids (never bytes) reach a player over the socket.
    room = w.room(gid, w.course_a)
    code = room["room_code"]
    host = TestSocketClient(w.base, w.admin, "host")
    player = TestSocketClient(w.base, w.guest(code), "player")
    try:
        await host.connect()
        await host.emit("join_room", {"room_code": code, "role": "HOST"})
        await host.wait_for("sync_state")
        await player.connect()
        await player.emit("join_room", {"room_code": code, "role": "PLAYER"})
        await player.wait_for("sync_state")
        await host.emit("host_advance", {})
        q = await player.wait_for("new_question")
        assert q["config"] == good_mc["config"]
        assert len(json.dumps(q)) < 2000
    finally:
        await host.disconnect()
        await player.disconnect()
        redis_del_room(code)


# ---------------------------------------------------------------------------
# Replace and delete
# ---------------------------------------------------------------------------


def test_replace_and_delete(world: World):
    w = world
    gid, (qid,) = new_game(w)
    used = uploaded(w, gid, png((40, 30)))
    free = uploaded(w, gid, png((40, 30)))
    w.ok("PUT", f"/games/{gid}/questions/{qid}", json={"config": {"options": ["A", "B"], "image_id": used["id"]}})
    etag = read(w, used["id"]).headers["etag"]

    # Same shape, new content: same id, new sha and ETag, the reference still resolves.
    new_bytes = png((80, 60))
    r = replace(w, gid, used["id"], new_bytes, w.host_a)
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["id"] == used["id"] and meta["sha256"] != used["sha256"]
    assert meta["created_at"] == used["created_at"]
    got = read(w, used["id"])
    assert got.content == new_bytes and got.headers["etag"] != etag
    # Same bytes: a no-op 200.
    assert replace(w, gid, used["id"], new_bytes).json()["sha256"] == meta["sha256"]
    # Another image's bytes: 409.
    r = replace(w, gid, used["id"], read(w, free["id"]).content)
    assert (r.status_code, err(r)) == (409, "IMAGE_DUPLICATE")
    # A referenced image must keep its shape; an unreferenced one need not.
    r = replace(w, gid, used["id"], png((40, 40)))
    assert (r.status_code, err(r)) == (409, "IMAGE_ASPECT_CHANGED")
    assert replace(w, gid, free["id"], png((40, 40))).status_code == 200

    r = w.req("DELETE", f"/games/{gid}/images/{used['id']}", w.host_a)
    assert (r.status_code, err(r)) == (409, "IMAGE_IN_USE")
    assert "Q1" in r.json()["message"]
    w.ok("DELETE", f"/games/{gid}/images/{free['id']}", w.host_a, status=204)
    assert read(w, free["id"]).status_code == 404  # no shared cache
    assert [i["id"] for i in listing(w, gid)] == [used["id"]]


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------


def test_duplicate_copies_images(world: World):
    w = world
    gid, (qid,) = new_game(w)
    a, b = uploaded(w, gid), uploaded(w, gid)
    source_config = {"options": ["A", "B"], "image_id": a["id"], "option_image_ids": [b["id"], None]}
    w.ok("PUT", f"/games/{gid}/questions/{qid}", json={"config": source_config})
    dangling_q = w.ok("POST", f"/games/{gid}/questions", json=MC_QUESTION, status=201)["id"]
    mysql(f"UPDATE questions SET config = JSON_SET(config, '$.image_id', '{uuid.uuid4()}') WHERE id = {dangling_q}")

    copy = w.ok("POST", f"/games/{gid}/duplicate", w.host_a, status=201)
    w.track_game(copy["id"])
    copy_images = listing(w, copy["id"], w.host_a)
    assert len(copy_images) == 2
    assert {i["id"] for i in copy_images}.isdisjoint({a["id"], b["id"]})
    assert sorted(i["sha256"] for i in copy_images) == sorted([a["sha256"], b["sha256"]])
    by_sha = {i["sha256"]: i["id"] for i in copy_images}
    q1, q2 = w.ok("GET", f"/games/{copy['id']}/questions")
    assert q1["config"] == {"options": ["A", "B"], "image_id": by_sha[a["sha256"]], "option_image_ids": [by_sha[b["sha256"]], None]}
    assert q2["config"]["image_id"] is None
    assert read(w, by_sha[a["sha256"]]).content == read(w, a["id"]).content
    assert w.ok("GET", f"/games/{gid}/questions")[0]["config"] == source_config

    # The copy's images are its own.
    w.ok("PUT", f"/games/{copy['id']}/questions/{q1['id']}", json={"config": {"options": ["A", "B"]}})
    w.ok("DELETE", f"/games/{copy['id']}/images/{by_sha[a['sha256']]}", status=204)
    assert read(w, a["id"]).status_code == 200
    assert len(listing(w, gid)) == 2


# ---------------------------------------------------------------------------
# Export and import
# ---------------------------------------------------------------------------


def export(w: World, game_id: int, admin: bool = False) -> dict:
    path = f"/admin/games/{game_id}/export" if admin else f"/games/{game_id}/export"
    r = w.req("GET", path)
    assert r.status_code == 200, r.text
    return r.json()


def import_raw(w: World, raw: bytes, admin: bool = False) -> httpx.Response:
    files = {"file": ("game.json", raw, "application/json")}
    if admin:
        return w.req("POST", f"/admin/games/import?course_id={w.course_a}", files=files)
    return w.req("POST", f"/courses/{w.course_a}/games/import", w.host_a, files=files)


def import_ok(w: World, bundle: dict, admin: bool = False) -> int:
    r = import_raw(w, json.dumps(bundle).encode(), admin)
    assert r.status_code == 201, r.text
    game_id = r.json()["game_id"] if admin else r.json()["id"]
    w.track_game(game_id)
    return game_id


def bundle(version: int, questions: list[dict], images=None) -> dict:
    out = {"format": "buzzer/game", "version": version, "game": {"title": f"Import {uuid.uuid4().hex[:6]}"}, "questions": questions}
    if images is not None:
        out["images"] = images
    return out


def b64_item(key: str, data: bytes, content_type: str = "image/png") -> dict:
    return {"key": key, "content_type": content_type, "data_base64": base64.b64encode(data).decode()}


def test_export_without_images_stays_version_1(world: World):
    w = world
    gid, (qid,) = new_game(w)
    w.ok("PUT", f"/games/{gid}/questions/{qid}", json={"config": {"options": ["A", "B"], "image_id": None}})
    out = export(w, gid)
    assert out["version"] == 1 and "images" not in out
    import_ok(w, out)
    # References to deleted images only: still version 1, with null.
    image = uploaded(w, gid)
    w.ok("PUT", f"/games/{gid}/questions/{qid}", json={"config": {"options": ["A", "B"], "image_id": image["id"]}})
    mysql(f"DELETE FROM images WHERE id = '{image['id']}'")
    out = export(w, gid)
    assert out["version"] == 1 and "images" not in out
    assert out["questions"][0]["config"]["image_id"] is None
    import_ok(w, out)


def test_export_import_round_trip_with_images(world: World):
    w = world
    gid, (qid,) = new_game(w)
    a, b, unused = uploaded(w, gid), uploaded(w, gid, png(fmt="JPEG")), uploaded(w, gid)
    config = {"options": ["img1", "B"], "image_id": b["id"], "option_image_ids": [a["id"], b["id"]]}
    w.ok("PUT", f"/games/{gid}/questions/{qid}", json={"config": config})
    for admin in (False, True):
        out = export(w, gid, admin=admin)
        assert out["version"] == 2
        assert [i["key"] for i in out["images"]] == ["img1", "img2"]  # order of first use, unused not exported
        assert out["questions"][0]["config"] == {"options": ["img1", "B"], "image_id": "img1", "option_image_ids": ["img2", "img1"]}
        new_gid = import_ok(w, out, admin=admin)
        imported = {i["sha256"]: i for i in listing(w, new_gid)}
        assert set(imported) == {a["sha256"], b["sha256"]}
        new_config = w.ok("GET", f"/games/{new_gid}/questions")[0]["config"]
        assert new_config["image_id"] == imported[b["sha256"]]["id"]
        assert new_config["option_image_ids"] == [imported[a["sha256"]]["id"], imported[b["sha256"]]["id"]]
        assert read(w, new_config["image_id"]).content == read(w, b["id"]).content
    assert unused["id"]


def test_import_edge_cases_that_succeed(world: World):
    w = world
    same = png()
    q = mc({"image_id": "k1", "option_image_ids": ["k2", None]})
    gid = import_ok(w, bundle(2, [q], [b64_item("k1", same), b64_item("k2", same)]))
    images = listing(w, gid)
    assert len(images) == 1  # identical bytes share one row
    config = w.ok("GET", f"/games/{gid}/questions")[0]["config"]
    assert config["image_id"] == config["option_image_ids"][0] == images[0]["id"]

    import_ok(w, bundle(2, [MC_QUESTION]))  # version 2 without an images key
    gid = import_ok(w, bundle(2, [MC_QUESTION], [b64_item("lonely", png())]))
    assert [i["used_by"] for i in listing(w, gid)] == [[]]  # unused library image
    gid = import_ok(w, bundle(2, [mc({"image_id": "j"})], [b64_item("j", png(fmt="JPEG"), "image/png")]))
    assert listing(w, gid)[0]["content_type"] == "image/jpeg"  # the detected format wins
    gid = import_ok(w, bundle(1, [MC_QUESTION], [b64_item("ignored", png())]))  # v1 ignores images
    assert listing(w, gid) == []

    for path in sorted((_REPO_ROOT / "sample_games").glob("*.json")):
        r = import_raw(w, path.read_bytes())
        assert r.status_code == 201, (path.name, r.text)
        w.track_game(r.json()["id"])


def test_import_failures_leave_nothing_behind(world: World):
    w = world
    good = b64_item("k", png())
    q = mc({"image_id": "k"})
    many = [b64_item(f"k{i}", png((2, 2))) for i in range(51)]
    huge = [b64_item(f"n{s}", noise_png(830, s)) for s in range(13)]
    cases = [
        ("bad base64", bundle(2, [q], [{**good, "data_base64": "@@@"}]), 400),
        ("unknown key", bundle(2, [mc({"image_id": "nope"})], [good]), 400),
        ("string ref in v1", bundle(1, [q]), 400),
        ("images not a list", bundle(2, [q], {"k": good}), 400),
        ("item not an object", bundle(2, [q], ["k"]), 400),
        ("non-string key", bundle(2, [q], [{**good, "key": 5}]), 400),
        ("duplicate key", bundle(2, [q], [good, good]), 400),
        ("empty key", bundle(2, [q], [{**good, "key": ""}]), 400),
        ("over 50 items", bundle(2, [MC_QUESTION], many), 400),
        ("bad content_type", bundle(2, [q], [{**good, "content_type": "image/gif"}]), 400),
        ("missing content_type", bundle(2, [q], [{k: v for k, v in good.items() if k != "content_type"}]), 400),
        ("non-string data", bundle(2, [q], [{**good, "data_base64": 5}]), 400),
        ("oversized image", bundle(2, [q], [b64_item("k", b"\0" * (2 * MIB + 1))]), 400),
        ("undecodable image", bundle(2, [q], [b64_item("k", b"not an image")]), 400),
        ("version 3", bundle(3, [MC_QUESTION]), 400),
        ("version true", bundle(True, [MC_QUESTION]), 400),
        ("version 2.0", bundle(2.0, [MC_QUESTION]), 400),
        ("images null", bundle(2, [q], None) | {"images": None}, 400),
        ("questions not a list", bundle(1, None), 400),
        ("questions a string", {**bundle(1, []), "questions": "x"}, 400),
        ("question not an object", bundle(2, [["x"]], [good]), 400),
        ("total over the byte quota", bundle(2, [MC_QUESTION], huge), 400),
        ("malformed option_image_ids", bundle(2, [mc({"option_image_ids": ["k"]})], [good]), 400),
    ]
    games_before = mysql(f"SELECT COUNT(*) FROM games WHERE course_id = {w.course_a}")
    images_before = all_image_rows()
    for name, body, status in cases:
        r = import_raw(w, json.dumps(body).encode())
        assert (r.status_code, err(r)) == (status, "INVALID_IMPORT"), (name, r.text)
    r = import_raw(w, b"x" * (40 * MIB + 1))
    assert (r.status_code, err(r)) == (413, "BUNDLE_TOO_LARGE")
    r = import_raw(w, b"x" * (40 * MIB + 1), admin=True)
    assert (r.status_code, err(r)) == (413, "BUNDLE_TOO_LARGE")
    assert mysql(f"SELECT COUNT(*) FROM games WHERE course_id = {w.course_a}") == games_before
    assert all_image_rows() == images_before


def test_dirty_configs_list_export_and_reimport(world: World):
    w = world
    gid, (q1,) = new_game(w)
    q2 = w.ok("POST", f"/games/{gid}/questions", json=MC_QUESTION, status=201)["id"]
    q3 = w.ok("POST", f"/games/{gid}/questions", json=MC_QUESTION, status=201)["id"]
    other_gid, _ = new_game(w)
    foreign = uploaded(w, other_gid)
    mysql(f"UPDATE questions SET config = JSON_SET(config, '$.image_id', 5) WHERE id = {q1}")
    mysql(f"UPDATE questions SET config = JSON_SET(config, '$.image_id', 'IMG-NOT-CANONICAL') WHERE id = {q2}")
    mysql(f"UPDATE questions SET config = JSON_SET(config, '$.image_id', '{foreign['id']}', '$.option_image_ids', 'abc') WHERE id = {q3}")
    assert listing(w, gid) == []
    for admin in (False, True):
        out = export(w, gid, admin=admin)
        assert out["version"] == 1
        assert [q["config"].get("image_id") for q in out["questions"]] == [None, None, None]
        assert "option_image_ids" not in out["questions"][2]["config"]
        import_ok(w, out, admin=admin)


# ---------------------------------------------------------------------------
# Game delete removes images
# ---------------------------------------------------------------------------


async def test_game_delete_removes_images(world: World):
    w = world
    gid, _ = new_game(w)
    uploaded(w, gid)
    host_game = w.ok("POST", f"/courses/{w.course_a}/games", w.host_a, json={"title": "host game"}, status=201)["id"]
    uploaded(w, host_game)
    w.ok("DELETE", f"/games/{host_game}", w.host_a, status=204)
    assert image_rows(host_game) == 0
    await play_one_answer(w, gid, w.course_a, finish=True)
    w.ok("DELETE", f"/admin/games/{gid}", status=204)
    assert image_rows(gid) == 0


# ---------------------------------------------------------------------------
# Write protocol under forced overlap
# ---------------------------------------------------------------------------


def _env(name: str) -> str:
    if name in os.environ:
        return os.environ[name]
    for line in (_REPO_ROOT / ".env").read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip()
    raise KeyError(name)


class GameRowLock:
    """Hold SELECT ... FOR UPDATE on a games row from a separate MySQL connection."""

    def __init__(self, game_id: int):
        self.game_id = game_id
        self.conn = pymysql.connect(
            host="127.0.0.1", port=3306, user="root", password=_env("MYSQL_ROOT_PASSWORD"), database="buzzer"
        )

    def __enter__(self):
        self.conn.begin()
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM games WHERE id = %s FOR UPDATE", (self.game_id,))
        return self

    def __exit__(self, *exc):
        self.conn.commit()
        self.conn.close()


def overlap(game_id: int, *calls):
    """Run the calls from threads while the game row is locked, so they all wait on
    it at the same time; release after a second and return their responses."""
    with ThreadPoolExecutor(len(calls)) as pool:
        with GameRowLock(game_id):
            futures = [pool.submit(c) for c in calls]
            time.sleep(1.0)
            assert not any(f.done() for f in futures), "a request did not wait for the lock"
        return [f.result(timeout=60) for f in futures]


def test_concurrent_identical_uploads(world: World):
    w = world
    gid, _ = new_game(w)
    data = png()
    r1, r2 = overlap(gid, lambda: upload(w, gid, data), lambda: upload(w, gid, data, w.host_a))
    assert sorted([r1.status_code, r2.status_code]) == [200, 201]
    assert r1.json()["id"] == r2.json()["id"]
    assert image_rows(gid) == 1


def test_image_delete_racing_a_question_save(world: World):
    w = world
    gid, (qid,) = new_game(w)
    for _ in range(3):
        image = uploaded(w, gid)
        save, delete = overlap(
            gid,
            lambda: w.req("PUT", f"/games/{gid}/questions/{qid}", w.host_a, json={"config": {"options": ["A", "B"], "image_id": image["id"]}}),
            lambda: w.req("DELETE", f"/games/{gid}/images/{image['id']}"),
        )
        outcome = (save.status_code, delete.status_code, err(save), err(delete))
        assert outcome in {(200, 409, "", "IMAGE_IN_USE"), (422, 204, "INVALID_IMAGE_REFERENCE", "")}, outcome
        config = w.ok("GET", f"/games/{gid}/questions")[0]["config"]
        present = {i["id"] for i in listing(w, gid)}
        assert config.get("image_id") in present | {None}
        w.ok("PUT", f"/games/{gid}/questions/{qid}", json={"config": {"options": ["A", "B"]}})


def test_game_delete_racing_an_upload_with_a_stale_lobby(world: World):
    w = world
    for stale in (True, False):
        game = w.ok("POST", f"/courses/{w.course_a}/games", w.host_a, json={"title": "race"}, status=201)["id"]
        w.track_game(game)
        if stale:
            room = w.room(game, w.course_a, w.host_a)
            redis_del_room(room["room_code"])
        upload_r, delete_r = overlap(
            game,
            lambda: upload(w, game, png(), w.host_a),
            lambda: w.req("DELETE", f"/games/{game}", w.host_a),
        )
        assert upload_r.status_code in (201, 404, 503), upload_r.text
        assert delete_r.status_code in (204, 503), delete_r.text
        if 503 in (upload_r.status_code, delete_r.status_code):
            assert "TRY_AGAIN" in (err(upload_r), err(delete_r))
        if delete_r.status_code == 204:
            assert image_rows(game) == 0
            assert mysql(f"SELECT COUNT(*) FROM games WHERE id = {game}") == "0"


def test_file_errors_are_decided_before_the_lock(world: World):
    w = world
    gid, _ = new_game(w)
    with ThreadPoolExecutor(2) as pool:
        with GameRowLock(gid):
            bad = pool.submit(upload, w, gid, b"not an image")
            good = pool.submit(upload, w, gid, png())
            assert bad.result(timeout=5).status_code == 415
            time.sleep(0.5)
            assert not good.done()
        assert good.result(timeout=30).status_code == 201
    # Immediately visible after the response (explicit commit).
    assert len(listing(w, gid)) == 1


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_data_column_is_longblob_and_holds_a_megabyte(world: World):
    w = world
    assert mysql(
        "SELECT DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = 'buzzer' AND TABLE_NAME = 'images' AND COLUMN_NAME = 'data'"
    ) == "longblob"
    gid, _ = new_game(w)
    data = noise_png(620, 7)
    assert len(data) > MIB
    meta = uploaded(w, gid, data)
    assert read(w, meta["id"]).content == data
