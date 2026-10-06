"""
Coverage the T7 and T8 suites left out (rubric R5/R7: "authorable by admins and hosts",
error and access-control cases):

- numeric_estimate through the course HOST routes (/api/games/{id}/questions), not only
  the /api/admin aliases: create, update validation, duplicate, export/import, and the
  403/401 cases for other hosts, hosts without a grant, guests and anonymous callers;
- image references reaching the game-over summaries that the host and player screens
  render images from (the image suite only checks the new_question payload);
- the T8 write protocol's permission re-check inside the game lock: a grant revoked while
  a request waits for the lock must turn that request into a 403.

Uses the `world` fixture of test_host_management.py and cleans up through it.
"""

from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from PIL import Image

from .engine.socket_client import TestSocketClient
from . import test_host_management
from .test_host_management import World, err, mysql, redis_del_room
from .test_images import GameRowLock

world = test_host_management.world  # the shared pytest fixture

BANDS = [{"within": 5, "points": 100}, {"within": 15, "points": 50}]
NUMERIC = {
    "type": "numeric_estimate",
    "grading_type": "ACCURACY",
    "prompt": "How many keys does a piano have?",
    "config": {"unit": "keys"},
    "answer_data": {"target": 88, "mode": "relative", "bands": BANDS},
    "time_limit_seconds": 30,
    "points_value": 100,
}


def test_hosts_author_numeric_questions_through_the_course_routes(world: World):
    w = world
    gid = w.game_a
    path = f"/games/{gid}/questions"

    # The granted course HOST creates, reads and edits it like any other type.
    q = w.ok("POST", path, w.host_a, json=NUMERIC, status=201)
    stored = next(x for x in w.ok("GET", path, w.host_a) if x["id"] == q["id"])
    assert stored["answer_data"] == NUMERIC["answer_data"] and stored["config"] == {
        "unit": "keys"
    }
    r = w.req(
        "PUT",
        f"{path}/{q['id']}",
        w.host_a,
        json={"answer_data": {**NUMERIC["answer_data"], "target": 0}},
    )
    assert (r.status_code, err(r)) == (422, "VALIDATION_ERROR"), r.text
    r = w.req("PUT", f"{path}/{q['id']}", w.host_a, json={"points_value": 5})
    assert (r.status_code, err(r)) == (422, "VALIDATION_ERROR"), (
        "points_value must equal the best band"
    )
    w.ok(
        "PUT",
        f"{path}/{q['id']}",
        w.host_a,
        json={"answer_data": {**NUMERIC["answer_data"], "mode": "absolute"}},
    )

    # Nobody else may author it.
    no_grant, _ = w.user(("HOST", w.course_a))  # HOST made after the game: no grant
    room = w.room(gid, w.course_a)
    guest = w.guest(room["room_code"])
    redis_del_room(room["room_code"])
    for token, status in ((w.host_b, 403), (no_grant, 403), (guest, 403)):
        r = w.req("POST", path, token, json=NUMERIC)
        assert r.status_code == status, r.text
        r = w.req("PUT", f"{path}/{q['id']}", token, json={"prompt": "x"})
        assert r.status_code == status, r.text
    r = httpx.post(f"{w.base}/api{path}", json=NUMERIC, timeout=10)
    assert r.status_code == 401

    # Duplicate and export/import by the host keep the answer key exactly.
    copy = w.ok("POST", f"/games/{gid}/duplicate", w.host_a, status=201)
    w.track_game(copy["id"])
    copied = [
        x
        for x in w.ok("GET", f"/games/{copy['id']}/questions", w.host_a)
        if x["type"] == "numeric_estimate"
    ]
    assert [x["answer_data"]["mode"] for x in copied] == ["absolute"]
    bundle = w.req("GET", f"/games/{gid}/export", w.host_a).content
    imported = w.ok(
        "POST",
        f"/courses/{w.course_a}/games/import",
        w.host_a,
        files={"file": ("g.json", bundle, "application/json")},
        status=201,
    )
    w.track_game(imported["id"])
    again = [
        x
        for x in w.ok("GET", f"/games/{imported['id']}/questions", w.host_a)
        if x["type"] == "numeric_estimate"
    ]
    assert again[0]["answer_data"] == copied[0]["answer_data"]
    assert again[0]["points_value"] == 100

    w.ok("DELETE", f"{path}/{q['id']}", w.host_a, status=204)


def _png(colour: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), colour).save(out, "PNG")
    return out.getvalue()


async def test_game_over_summaries_carry_image_references(world: World):
    w = world
    gid, _ = w.admin_game(w.course_a, questions=0)
    ids = [
        w.ok(
            "POST",
            f"/games/{gid}/images",
            files={"file": ("i.png", _png(c))},
            status=201,
        )["id"]
        for c in ((200, 0, 0), (0, 0, 200))
    ]
    config = {
        "options": ["Red", "Blue"],
        "image_id": ids[0],
        "option_image_ids": [None, ids[1]],
    }
    w.ok(
        "POST",
        f"/games/{gid}/questions",
        json={
            "type": "multiple_choice",
            "grading_type": "ACCURACY",
            "prompt": "Which colour?",
            "config": config,
            "answer_data": {"answer_points": [1.0, 0.0]},
            "time_limit_seconds": 30,
            "points_value": 1.0,
        },
        status=201,
    )
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
        await player.emit(
            "submit_answer",
            {
                "question_id": q["questionId"],
                "answer_data": {"selectedIndex": 1},
                "answer_time_ms": 400,
            },
        )
        await player.wait_for("answer_received")
        await host.emit("host_advance", {})
        await host.wait_for("question_results")
        await host.emit("host_advance", {})
        host_over = await host.wait_for("game_over")
        player_over = await player.wait_for("game_over")
    finally:
        await host.disconnect()
        await player.disconnect()
    assert host_over["questionSummary"][0]["config"] == config
    assert player_over["questionSummary"][0]["config"] == config
    # The ids are enough to show the pictures: they resolve without a login.
    for image_id in ids:
        assert (
            httpx.get(f"{w.base}/api/images/{image_id}", timeout=10).status_code == 200
        )


def test_permission_is_rechecked_inside_the_game_lock(world: World):
    """The read phase already passed (the host had the grant); the grant is revoked while
    the request waits for the games row lock. Without the re-check inside the lock the
    write would go through with a permission that no longer exists."""
    w = world
    gid = w.game_a
    before = len(w.ok("GET", f"/games/{gid}/questions"))
    with ThreadPoolExecutor(1) as pool:
        with GameRowLock(gid):
            pending = pool.submit(
                w.req, "POST", f"/games/{gid}/questions", w.host_a, json=NUMERIC
            )
            time.sleep(1.0)
            assert not pending.done(), "the request did not wait for the lock"
            w.ok("DELETE", f"/admin/users/{w.host_a_id}/game-access/{gid}", status=204)
            # The admin endpoint answers before get_db commits, so wait until the revoke
            # is really committed before letting the waiting request in.
            deadline = time.time() + 10
            while (
                mysql(
                    f"SELECT COUNT(*) FROM user_game_access WHERE user_id = '{w.host_a_id}' AND game_id = {gid}"
                )
                != "0"
            ):
                assert time.time() < deadline, "the revoke never committed"
                time.sleep(0.05)
        r = pending.result(timeout=30)
    assert r.status_code == 403, r.text
    assert len(w.ok("GET", f"/games/{gid}/questions")) == before
