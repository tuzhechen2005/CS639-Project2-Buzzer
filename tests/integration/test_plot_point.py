"""
plot_point (docs/plans/t7-plot-the-point.md, Tests/Integration): authoring by course HOSTs with
validation on create, update and import; access control; banded scoring over real sockets with
the "col,row" distribution, the reveal and answer secrecy; invalid answers; COMPLETENESS;
export/import; the report; the locked-game rule; and T8's "image on a canvas question".

Uses the `world` fixture (two courses, a HOST of each). Every game is created through the
world, whose cleanup deletes it with the admin game delete: that removes the MySQL rows and
ends any live room in Redis, so a failing test leaves nothing behind.
"""

from __future__ import annotations

import json

import httpx

from . import test_host_management
from .engine.socket_client import TestSocketClient
from .test_host_management import World, err, mysql
from .test_images import png, read, uploaded

world = test_host_management.world  # the shared pytest fixture

PLANE = {"xMin": -10, "xMax": 10, "xStep": 1, "yMin": -10, "yMax": 10, "yStep": 1}
BANDS = [{"within": 0, "points": 100}, {"within": 1, "points": 50}]
# Target (3, -2) is grid point col 13, row 8.
PLOT = {
    "type": "plot_point",
    "grading_type": "ACCURACY",
    "prompt": "Plot the point (3, -2)",
    "config": {
        **PLANE,
        "xLabel": "x",
        "yLabel": "y",
        "overlays": [{"kind": "line", "x1": 0, "y1": 1, "x2": 1, "y2": 3, "label": "y = 2x + 1"}],
    },
    "answer_data": {"target": {"x": 3, "y": -2}, "bands": BANDS},
    "time_limit_seconds": 45,
    "points_value": 100,
}
ANSWER_ERROR = "plot_point answer must be a grid point inside the plane"
SECRET_KEYS = {"answer_data", "target", "bands"}


def _keys(obj) -> set[str]:
    """Every dict key anywhere in a payload (by name, not by value)."""
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


def _plot_game(w: World, question: dict) -> tuple[int, dict]:
    """A fresh game in course A (granted to host_a) with one question created by host_a."""
    gid, _ = w.admin_game(w.course_a, questions=0)
    q = w.ok("POST", f"/games/{gid}/questions", w.host_a, json=question, status=201)
    return gid, q


async def _play(w: World, gid: int, answers: list[dict], *, invalid_first: list | None = None):
    """Play the game's only question: one guest per answer. Returns a dict with the room,
    each player's events before and after the close, and the host's results and game over."""
    room = w.room(gid, w.course_a)
    code = room["room_code"]
    host = TestSocketClient(w.base, w.admin, "host")
    players = [TestSocketClient(w.base, w.guest(code), f"p{i}") for i in range(len(answers))]
    before: list[list[dict]] = [[] for _ in players]  # player events before the close
    try:
        await host.connect()
        await host.emit("join_room", {"room_code": code, "role": "HOST"})
        await host.wait_for("sync_state")
        for i, p in enumerate(players):
            await p.connect()
            await p.emit("join_room", {"room_code": code, "role": "PLAYER"})
            before[i].append(await p.wait_for("sync_state"))
        await host.emit("host_advance", {})
        payloads = []
        for i, p in enumerate(players):
            payloads.append(await p.wait_for("new_question"))
            before[i].append(payloads[-1])
        qid = payloads[0]["questionId"]
        errors = []
        for bad in invalid_first or []:
            await players[0].emit("submit_answer", {"question_id": qid, "answer_data": bad, "answer_time_ms": 100})
            errors.append(await players[0].wait_for("error", timeout=5))
        received = []
        for i, (p, answer) in enumerate(zip(players, answers)):
            await p.emit("submit_answer", {"question_id": qid, "answer_data": answer, "answer_time_ms": 500})
            received.append(await p.wait_for("answer_received"))
            before[i].append(received[-1])
        await host.emit("host_advance", {})
        results = await host.wait_for("question_results", timeout=10)
        player_results = [await p.wait_for("question_results", timeout=10) for p in players]
        await host.emit("host_advance", {})
        over = await host.wait_for("game_over", timeout=10)
    finally:
        for p in players:
            await p.disconnect()
        await host.disconnect()
    return {
        "room": room,
        "payload": payloads[0],
        "before": before,
        "errors": errors,
        "received": received,
        "results": results,
        "player_results": player_results,
        "over": over,
    }


# ---------------------------------------------------------------------------
# Authoring, validation and access
# ---------------------------------------------------------------------------


def test_host_authors_plot_point_with_validation_on_create_and_update(world: World):
    w = world
    gid, q = _plot_game(w, PLOT)
    path = f"/games/{gid}/questions"
    stored = next(x for x in w.ok("GET", path, w.host_a) if x["id"] == q["id"])
    assert stored["type"] == "plot_point"
    assert stored["config"] == PLOT["config"] and stored["answer_data"] == PLOT["answer_data"]

    # Invalid definitions are refused on create.
    for bad in (
        {**PLOT, "config": {**PLOT["config"], "xStep": 3}},  # not a nice step
        {**PLOT, "answer_data": {**PLOT["answer_data"], "target": {"x": 3.5, "y": -2}}},  # off grid
        {**PLOT, "points_value": 99},  # not the first band's points
    ):
        r = w.req("POST", path, w.host_a, json=bad)
        assert r.status_code == 422, r.text

    # On update the merged question is validated, even when only answer_data changes,
    # and a rejected update leaves the question exactly as it was.
    for change in (
        {"answer_data": {**PLOT["answer_data"], "target": {"x": 11, "y": 0}}},  # outside
        {"config": {**PLANE, "xMin": -10, "xMax": 11}},  # 21 cells
    ):
        r = w.req("PUT", f"{path}/{q['id']}", w.host_a, json=change)
        assert (r.status_code, err(r)) == (422, "VALIDATION_ERROR"), r.text
    unchanged = next(x for x in w.ok("GET", path, w.host_a) if x["id"] == q["id"])
    assert unchanged["config"] == stored["config"] and unchanged["answer_data"] == stored["answer_data"]

    # Changing only the type of another question to plot_point fails: its config has no plane.
    mc_gid, (mc_qid,) = w.admin_game(w.course_a)
    r = w.req("PUT", f"/games/{mc_gid}/questions/{mc_qid}", w.admin, json={"type": "plot_point"})
    assert (r.status_code, err(r)) == (422, "VALIDATION_ERROR"), r.text

    # A valid update succeeds; then the question is deleted.
    new_bands = [{"within": 0, "points": 100}, {"within": 2, "points": 40}]
    updated = w.ok("PUT", f"{path}/{q['id']}", w.host_a, json={"answer_data": {**PLOT["answer_data"], "bands": new_bands}})
    assert updated["answer_data"]["bands"] == new_bands
    w.ok("DELETE", f"{path}/{q['id']}", w.host_a, status=204)
    assert all(x["id"] != q["id"] for x in w.ok("GET", path, w.host_a))


def test_only_the_granted_course_host_may_author_plot_point(world: World):
    w = world
    gid, q = _plot_game(w, PLOT)
    path = f"/games/{gid}/questions"
    no_grant, _ = w.user(("HOST", w.course_a))  # HOST made after the game: no grant
    room = w.room(gid, w.course_a)
    guest = w.guest(room["room_code"])
    try:
        for token in (w.host_b, no_grant, guest):
            assert w.req("POST", path, token, json=PLOT).status_code == 403
            assert w.req("PUT", f"{path}/{q['id']}", token, json={"prompt": "x"}).status_code == 403
        assert httpx.post(f"{w.base}/api{path}", json=PLOT, timeout=10).status_code == 401
    finally:
        w.ok("DELETE", f"/game/sessions/{room['session_id']}", status=204)


def test_plot_point_export_import_round_trip_and_invalid_import(world: World):
    w = world
    gid, _ = _plot_game(w, PLOT)
    bundle = w.req("GET", f"/games/{gid}/export", w.host_a)
    assert bundle.status_code == 200
    data = bundle.json()
    assert data["questions"][0]["type"] == "plot_point"
    imported = w.ok(
        "POST", f"/courses/{w.course_a}/games/import", w.host_a,
        files={"file": ("g.json", bundle.content, "application/json")}, status=201,
    )
    w.track_game(imported["id"])
    again = w.ok("GET", f"/games/{imported['id']}/questions", w.host_a)
    assert again[0]["config"] == PLOT["config"] and again[0]["answer_data"] == PLOT["answer_data"]

    # A file with an invalid plot_point question is refused and creates no game.
    data["questions"][0]["answer_data"]["target"] = {"x": 0.5, "y": 0}
    before = len(w.ok("GET", "/admin/games"))
    r = w.req(
        "POST", f"/courses/{w.course_a}/games/import", w.host_a,
        files={"file": ("g.json", json.dumps(data).encode(), "application/json")},
    )
    assert (r.status_code, err(r)) == (400, "INVALID_IMPORT"), r.text
    assert len(w.ok("GET", "/admin/games")) == before


# ---------------------------------------------------------------------------
# Playing
# ---------------------------------------------------------------------------


async def test_banded_scoring_distribution_reveal_and_secrecy_over_sockets(world: World):
    w = world
    gid, _ = _plot_game(w, PLOT)
    game = await _play(
        w, gid,
        # exact (+ an extra key that must not be stored), 1 cell off, 3 cells off
        [{"col": 13, "row": 8, "extra": "dropped"}, {"col": 14, "row": 8}, {"col": 16, "row": 8}],
        invalid_first=[{"col": 21, "row": 0}, {"col": 1.0, "row": 0}, {"col": "1", "row": 0}],
    )
    assert [r["pointsAwarded"] for r in game["received"]] == [100, 50, 0]
    assert [r["isCorrect"] for r in game["received"]] == [True, False, False]

    # Invalid answers were refused with the type's message and recorded nothing.
    assert [e["message"] for e in game["errors"]] == [ANSWER_ERROR] * 3
    sid = game["room"]["session_id"]
    assert mysql(f"SELECT COUNT(*) FROM session_scores WHERE session_id = '{sid}'") == "3"
    # The stored answer is exactly {col, row} (normalize_answer dropped the extra key).
    stored = mysql(f"SELECT answer_data FROM session_scores WHERE session_id = '{sid}' AND points_awarded = 100")
    assert json.loads(stored) == {"col": 13, "row": 8}

    # Phones get the plane, never the answer key: no secret key anywhere before the close.
    assert game["payload"]["type"] == "plot_point" and game["payload"]["config"] == PLOT["config"]
    for events in game["before"]:
        for event in events:
            assert not (_keys(event) & SECRET_KEYS), event
    # After the close a player gets the reveal and their own points, not the distribution.
    for pr in game["player_results"]:
        assert "answerDistribution" not in pr
        assert pr["answerReveal"]["type"] == "plot_point"

    # The host sees the "col,row" buckets and the reveal with exactly type, target, bands.
    results = game["results"]
    assert results["answerDistribution"] == {"13,8": 1, "14,8": 1, "16,8": 1}
    assert set(results["answerReveal"]) == {"type", "target", "bands"}
    assert results["answerReveal"]["target"] == {"x": 3, "y": -2}
    # The game-over summary recomputes the same distribution from the stored answers.
    summary = game["over"]["questionSummary"][0]
    assert summary["answerDistribution"] == results["answerDistribution"]
    assert summary["config"] == PLOT["config"]


async def test_completeness_gives_full_points_and_keeps_the_scatter(world: World):
    w = world
    poll = {**PLOT, "grading_type": "COMPLETENESS", "answer_data": {}, "points_value": 10,
            "prompt": "Rate this movie: x = plot, y = acting"}
    gid, _ = _plot_game(w, poll)
    game = await _play(w, gid, [{"col": 0, "row": 0}, {"col": 20, "row": 5}])
    assert [r["pointsAwarded"] for r in game["received"]] == [10, 10]
    assert game["results"]["answerReveal"] == {"type": "completeness"}
    assert game["results"]["answerDistribution"] == {"0,0": 1, "20,5": 1}


async def test_report_and_locked_game_after_play(world: World):
    w = world
    gid, q = _plot_game(w, PLOT)
    game = await _play(w, gid, [{"col": 13, "row": 8}, {"col": 0, "row": 0}])
    r = w.req("GET", f"/sessions/{game['room']['session_id']}/report", w.host_a)
    assert r.status_code == 200, r.text
    page = r.text
    assert "Plot the Point" in page and "badge-pp" in page
    assert "Target: (3, −2)" in page
    for label in ("Exact", "Within 1 cell", "Missed"):
        assert f'<span class="bar-label">{label}</span>' in page

    # Played, so the question can no longer change.
    r = w.req("PUT", f"/games/{gid}/questions/{q['id']}", w.host_a, json={"prompt": "changed"})
    assert (r.status_code, err(r)) == (409, "GAME_LOCKED"), r.text


# ---------------------------------------------------------------------------
# T8: an image on a canvas-type question
# ---------------------------------------------------------------------------


async def test_t8_image_as_the_plane_background(world: World):
    w = world
    gid, _ = w.admin_game(w.course_a, questions=0)
    image = uploaded(w, gid, png((200, 200)))
    question = {**PLOT, "config": {**PLOT["config"], "image_id": image["id"]}}
    w.ok("POST", f"/games/{gid}/questions", w.host_a, json=question, status=201)

    # An image of another game is refused (T8 reference rule, for this type too).
    other_gid, _ = w.admin_game(w.course_a, questions=0)
    foreign = uploaded(w, other_gid, png((50, 50)))
    bad = {**PLOT, "config": {**PLOT["config"], "image_id": foreign["id"]}}
    r = w.req("POST", f"/games/{gid}/questions", w.host_a, json=bad)
    assert r.status_code == 422 and err(r) == "INVALID_IMAGE_REFERENCE", r.text

    game = await _play(w, gid, [{"col": 13, "row": 8}])
    assert game["payload"]["config"]["image_id"] == image["id"]
    assert game["received"][0]["pointsAwarded"] == 100
    served = read(w, image["id"])
    assert served.status_code == 200 and served.headers["content-type"] == image["content_type"]
