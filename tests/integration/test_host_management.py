"""
T4 host-management rules (docs/plans/t4-ui-restructuring.md §B–§D, test plan §H):
course-scoped games, permission and integrity rules, roster modes, downloads and the
router-orchestrated deletes. Runs against the live Docker stack.

Every test builds its own courses, users and games through the `world` fixture and
removes the users and games it created (courses have no delete endpoint and are left
as inert records, as in the rest of the suite). Redis room keys are removed through
`docker compose exec redis` to simulate rooms that expired or were lost.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import subprocess
import uuid
from dataclasses import dataclass, field

import httpx
import pytest

from .engine.socket_client import TestSocketClient

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent

MC_QUESTION = {
    "type": "multiple_choice",
    "grading_type": "ACCURACY",
    "prompt": "Pick A",
    "config": {"options": ["A", "B"]},
    "answer_data": {"answer_points": [1.0, 0.0]},
    "time_limit_seconds": 30,
    "points_value": 1.0,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def redis_del_room(code: str) -> None:
    """Simulate an expired/lost room by deleting its Redis key."""
    subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "DEL", f"room:{code}"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )


def redis_set_room(code: str, data: dict) -> None:
    """Make a room key belong to a made-up session, as after a room code is reused."""
    subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "SET", f"room:{code}", json.dumps(data)],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )


def redis_get_room(code: str) -> dict | None:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "GET", f"room:{code}"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return json.loads(out) if out else None


def mysql(sql: str) -> str:
    """Run SQL as root inside the mysql container (credentials come from its own env)."""
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "mysql", "sh", "-c",
         'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" buzzer -e "$0"', sql],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def redis_room_exists(code: str) -> bool:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "EXISTS", f"room:{code}"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() == "1"


@dataclass
class World:
    """Two courses, a HOST of each, and an admin-created game in course A."""

    base: str
    admin: str
    course_a: int = 0
    course_b: int = 0
    host_a: str = ""  # token
    host_a_id: str = ""
    host_b: str = ""
    host_b_id: str = ""
    game_a: int = 0
    question_a: int = 0
    _users: list[str] = field(default_factory=list)
    _games: list[int] = field(default_factory=list)

    # -- REST shortcuts ----------------------------------------------------
    def req(self, method: str, path: str, token: str | None = None, **kw) -> httpx.Response:
        return httpx.request(
            method, f"{self.base}/api{path}", headers=_h(token or self.admin), timeout=15.0, **kw
        )

    def ok(self, method: str, path: str, token: str | None = None, status: int = 200, **kw):
        r = self.req(method, path, token, **kw)
        assert r.status_code == status, f"{method} {path} → {r.status_code}: {r.text}"
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else r

    # -- builders ----------------------------------------------------------
    def course(self, name: str) -> int:
        return self.ok("POST", "/admin/courses", json={"name": name, "semester": "Test"}, status=201)["id"]

    def user(self, role_course: tuple[str, int] | None = None) -> tuple[str, str]:
        """Create a local USER (optionally with HOST/PLAYER on a course); return (token, id)."""
        name = f"t4u_{_tag()}"
        u = self.ok(
            "POST",
            "/admin/users",
            json={"username": name, "display_name": name, "password": "password123"},
            status=201,
        )
        self._users.append(u["id"])
        if role_course:
            self.grant_course(u["id"], role_course[1], role_course[0])
        r = httpx.post(
            f"{self.base}/api/auth/login",
            json={"username": name, "password": "password123"},
            timeout=10.0,
        )
        assert r.status_code == 200, r.text
        return r.json()["access_token"], u["id"]

    def grant_course(self, user_id: str, course_id: int, role: str = "HOST") -> None:
        self.ok(
            "POST",
            f"/admin/users/{user_id}/course-access",
            json={"course_id": course_id, "role": role},
            status=204,
        )

    def admin_game(
        self, course_id: int, questions: int = 1, time_limit: int = 30
    ) -> tuple[int, list[int]]:
        g = self.ok(
            "POST", "/admin/games", json={"course_id": course_id, "title": f"T4 {_tag()}"}, status=201
        )
        self._games.append(g["id"])
        qids = [
            self.ok("POST", f"/admin/games/{g['id']}/questions", json={**MC_QUESTION, "time_limit_seconds": time_limit}, status=201
            )["id"]
            for _ in range(questions)
        ]
        return g["id"], qids

    def track_game(self, game_id: int) -> None:
        self._games.append(game_id)

    def room(self, game_id: int, course_id: int, token: str | None = None) -> dict:
        return self.ok(
            "POST", "/game/rooms", token, json={"game_id": game_id, "course_id": course_id}, status=201
        )

    def guest(self, room_code: str) -> str:
        t = _tag()
        r = httpx.post(
            f"{self.base}/api/auth/guest",
            json={"display_name": f"G{t}", "email": f"g.{t}@example.com", "room_code": room_code},
            timeout=10.0,
        )
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def cleanup(self) -> None:
        for gid in self._games:
            self.req("DELETE", f"/admin/games/{gid}")
        for uid in self._users:
            self.req("DELETE", f"/admin/users/{uid}")


def err(r: httpx.Response) -> str:
    try:
        return r.json().get("error", "")
    except ValueError:
        return ""


@pytest.fixture()
def world(docker_stack, base_url: str, admin_token: str):
    w = World(base=base_url, admin=admin_token)
    t = _tag()
    w.course_a = w.course(f"T4 Course A {t}")
    w.course_b = w.course(f"T4 Course B {t}")
    w.host_a, w.host_a_id = w.user(("HOST", w.course_a))
    w.host_b, w.host_b_id = w.user(("HOST", w.course_b))
    # Admin-created game: auto-granted to every existing HOST of course A.
    w.game_a, (w.question_a,) = w.admin_game(w.course_a)
    yield w
    w.cleanup()


async def play_one_answer(w: World, game_id: int, course_id: int, *, finish: bool):
    """Open a room as admin, have one guest answer the first question.
    Returns (room dict, host client, player client). With finish=True the game is
    driven to game_over (status COMPLETED) and both clients are disconnected."""
    room = w.room(game_id, course_id)
    code = room["room_code"]
    host = TestSocketClient(w.base, w.admin, "host")
    player = TestSocketClient(w.base, w.guest(code), "player")
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
        {"question_id": q["questionId"], "answer_data": {"selectedIndex": 0}, "answer_time_ms": 500},
    )
    await player.wait_for("answer_received")
    if finish:
        while True:
            await host.emit("host_advance", {})
            done = asyncio.ensure_future(host.wait_for("game_over", timeout=5))
            try:
                await host.wait_for("question_results", timeout=5)
                done.cancel()
            except asyncio.TimeoutError:
                await done
                break
        await host.disconnect()
        await player.disconnect()
    return room, host, player


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def test_other_course_host_is_forbidden(world: World):
    w = world
    for path in (
        f"/courses/{w.course_a}/roster",
        f"/courses/{w.course_a}/games",
        f"/courses/{w.course_a}/sessions",
        f"/games/{w.game_a}",
        f"/games/{w.game_a}/questions",
    ):
        r = w.req("GET", path, w.host_b)
        assert r.status_code == 403, f"{path}: {r.status_code} {r.text}"


def test_admin_created_game_is_granted_to_existing_hosts(world: World):
    w = world
    games = w.ok("GET", f"/courses/{w.course_a}/games", w.host_a)
    assert [g["id"] for g in games] == [w.game_a]
    assert games[0]["course_id"] == w.course_a and games[0]["locked"] is False


def test_host_without_game_grant_cannot_see_or_run(world: World):
    w = world
    late_host, _ = w.user(("HOST", w.course_a))  # no retroactive grant (Decision 3)
    assert w.ok("GET", f"/courses/{w.course_a}/games", late_host) == []
    assert w.req("GET", f"/games/{w.game_a}", late_host).status_code == 403
    r = w.req("POST", "/game/rooms", late_host, json={"game_id": w.game_a, "course_id": w.course_a})
    assert r.status_code == 403


def test_game_grant_requires_course_host_and_is_idempotent(world: World):
    w = world
    r = w.req("POST", f"/admin/users/{w.host_b_id}/game-access", json={"game_id": w.game_a})
    assert r.status_code == 409 and err(r) == "NOT_COURSE_HOST"
    for _ in range(2):  # host_a already holds the auto-grant
        w.ok("POST", f"/admin/users/{w.host_a_id}/game-access", json={"game_id": w.game_a}, status=204)


def test_admin_course_access_list(world: World):
    w = world
    rows = w.ok("GET", f"/admin/courses/{w.course_a}/access")
    assert [(r["user_id"], r["role"]) for r in rows] == [(w.host_a_id, "HOST")]


# ---------------------------------------------------------------------------
# Ownership of child ids
# ---------------------------------------------------------------------------


def test_child_ids_must_belong_to_the_path_parent(world: World):
    w = world
    w.ok(
        "POST",
        f"/admin/courses/{w.course_b}/roster/import",
        json={"rows": [{"netid": f"b{_tag()}", "full_name": "B Student", "email": "b@example.com"}]},
    )
    entry_b = w.ok("GET", f"/admin/courses/{w.course_b}/roster")[0]["id"]
    r = w.req("PATCH", f"/courses/{w.course_a}/roster/{entry_b}", w.host_a, json={"is_active": False})
    assert r.status_code == 404

    game_b, (q_b,) = w.admin_game(w.course_b)
    r = w.req("PUT", f"/games/{w.game_a}/questions/{q_b}", w.host_a, json={"prompt": "x"})
    assert r.status_code == 404
    r = w.req("DELETE", f"/games/{w.game_a}/questions/{q_b}", w.host_a)
    assert r.status_code == 404
    r = w.req("POST", f"/games/{w.game_a}/questions/reorder", w.host_a, json={"order": [q_b]})
    assert r.status_code == 409 and err(r) == "QUESTIONS_CHANGED"


# ---------------------------------------------------------------------------
# Game create / delete by hosts
# ---------------------------------------------------------------------------


def test_host_game_create_takes_course_from_path(world: World):
    w = world
    r = w.req(
        "POST", f"/courses/{w.course_a}/games", w.host_a, json={"title": "x", "course_id": w.course_b}
    )
    assert r.status_code == 422
    g = w.ok("POST", f"/courses/{w.course_a}/games", w.host_a, json={"title": "Host game"}, status=201)
    w.track_game(g["id"])
    assert g["course_id"] == w.course_a and g["locked"] is False

    # A co-host with a grant may delete an unplayed game they did not create.
    co_host, co_id = w.user(("HOST", w.course_a))
    w.ok("POST", f"/admin/users/{co_id}/game-access", json={"game_id": g["id"]}, status=204)
    w.ok("DELETE", f"/games/{g['id']}", co_host, status=204)
    assert w.req("GET", f"/admin/games/{g['id']}").status_code == 404


def test_non_admin_cannot_move_game(world: World):
    w = world
    w.ok("PUT", f"/games/{w.game_a}", w.host_a, json={"course_id": w.course_a, "title": "Same course ok"})
    r = w.req("PUT", f"/games/{w.game_a}", w.host_a, json={"course_id": w.course_b})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------


def test_room_course_must_match_game(world: World):
    w = world
    r = w.req("POST", "/game/rooms", json={"game_id": w.game_a, "course_id": w.course_b})
    assert r.status_code == 400 and err(r) == "COURSE_MISMATCH"
    # Permission is checked before the mismatch: no information for outsiders.
    r = w.req("POST", "/game/rooms", w.host_b, json={"game_id": w.game_a, "course_id": w.course_b})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# System course
# ---------------------------------------------------------------------------


@pytest.fixture
def system_course(world: World):
    """A system course made directly in MySQL: the API can't create one, and a fresh
    database only has one if migration 004 found a game that was never played."""
    name = f"T4 Unassigned {_tag()}"
    mysql(f"INSERT INTO courses (name, semester, is_system) VALUES ('{name}', 'n/a', 1)")
    sid = int(mysql(f"SELECT id FROM courses WHERE name = '{name}'"))
    yield sid
    mysql(f"DELETE FROM games WHERE course_id = {sid}")
    mysql(f"DELETE FROM courses WHERE id = {sid}")


def test_system_course_rules(world: World, system_course: int):
    w = world
    sid = system_course
    assert any(c["id"] == sid and c["is_system"] for c in w.ok("GET", "/admin/courses"))

    r = w.req("GET", f"/courses/{sid}/roster")
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"
    r = w.req("POST", f"/admin/users/{w.host_a_id}/course-access", json={"course_id": sid, "role": "HOST"})
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"

    bundle = b'{"format": "buzzer/game", "version": 1, "game": {"title": "x"}, "questions": []}'
    r = w.req("POST", f"/admin/games/import?course_id={sid}", files={"file": ("g.json", bundle)})
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"
    r = w.req("POST", "/admin/games/import", files={"file": ("g.json", bundle)})
    assert r.status_code == 422

    # A game living in the system course (as after the migration) can't be run or copied.
    mysql(f"INSERT INTO games (title, description, course_id) VALUES ('T4 sys {_tag()}', '', {sid})")
    gid = int(mysql(f"SELECT MAX(id) FROM games WHERE course_id = {sid}"))
    r = w.req("POST", "/game/rooms", json={"game_id": gid, "course_id": sid})
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"
    r = w.req("POST", f"/games/{gid}/duplicate")
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"
    assert all(c["id"] != sid for c in w.ok("GET", "/game/my-courses"))


# ---------------------------------------------------------------------------
# Rosters
# ---------------------------------------------------------------------------


def test_roster_add_only_and_replace_dry_run(world: World):
    w = world
    rows = [{"netid": f"r{i}{_tag()}", "full_name": f"S{i}", "email": f"s{i}@example.com"} for i in range(3)]
    path = f"/courses/{w.course_a}/roster/import"
    res = w.ok("POST", path, w.host_a, json={"rows": rows})
    assert (res["imported"], res["deactivated"]) == (3, 0)

    res = w.ok("POST", path, w.host_a, json={"rows": rows[:1]})  # default add_only
    assert (res["updated"], res["deactivated"]) == (1, 0)

    res = w.ok("POST", f"{path}?mode=replace&dry_run=true", w.host_a, json={"rows": rows[:1]})
    assert res["deactivated"] == 2
    active = [e for e in w.ok("GET", f"/courses/{w.course_a}/roster", w.host_a) if e["is_active"]]
    assert len(active) == 3, "dry run must not save"

    assert w.req("POST", f"{path}?mode=wipe", w.host_a, json={"rows": rows}).status_code == 422


def _active_netids(w: World, course_id: int, token: str | None = None) -> set[str]:
    return {e["netid"] for e in w.ok("GET", f"/courses/{course_id}/roster", token) if e["is_active"]}


def test_roster_replace_and_add_only_really_write(world: World):
    """The preview test above never saves; these check what actually changes in the data."""
    w = world
    t = _tag()
    rows = [{"netid": f"w{i}{t}", "full_name": f"S{i}", "email": f"w{i}{t}@example.com"} for i in range(3)]
    path = f"/courses/{w.course_a}/roster/import"
    netids = {r["netid"] for r in rows}

    res = w.ok("POST", path, w.host_a, json={"rows": rows})
    assert res["imported"] == 3 and _active_netids(w, w.course_a, w.host_a) == netids

    res = w.ok("POST", f"{path}?mode=replace", w.host_a, json={"rows": rows[:1]})
    assert res["deactivated"] == 2
    assert _active_netids(w, w.course_a, w.host_a) == {rows[0]["netid"]}

    # add_only reactivates what it is given and deactivates nobody.
    res = w.ok("POST", f"{path}?mode=add_only", w.host_a, json={"rows": rows[1:]})
    assert res["deactivated"] == 0
    assert _active_netids(w, w.course_a, w.host_a) == netids


def test_admin_roster_alias_keeps_replace_behaviour(world: World):
    w = world
    t = _tag()
    rows = [{"netid": f"a{i}{t}", "full_name": f"S{i}", "email": f"a{i}{t}@example.com"} for i in range(3)]
    w.ok("POST", f"/admin/courses/{w.course_a}/roster/import", json={"rows": rows})
    assert _active_netids(w, w.course_a, w.host_a) == {r["netid"] for r in rows}
    res = w.ok("POST", f"/admin/courses/{w.course_a}/roster/import", json={"rows": rows[:1]})
    assert res["deactivated"] == 2, "the admin alias is replace-only, as before T4"
    assert _active_netids(w, w.course_a, w.host_a) == {rows[0]["netid"]}


def test_roster_csv_upload_parses_a_canvas_export(world: World):
    w = world
    t = _tag()
    csv_text = (
        "Student,ID,SIS Login ID,Section\n"
        "    Points Possible,,,\n"
        f'"Doe, Jane Q",1,JDOE{t}@WISC.EDU,001\n'
        f'"Roe, Rich",2,rroe{t}@wisc.edu,001\n'
    )
    res = w.ok(
        "POST",
        f"/courses/{w.course_a}/roster",
        w.host_a,
        files={"file": ("roster.csv", csv_text.encode())},
    )
    assert res["imported"] == 2 and not res["errors"]
    by_netid = {e["netid"]: e for e in w.ok("GET", f"/courses/{w.course_a}/roster", w.host_a)}
    assert by_netid[f"jdoe{t}"]["full_name"] == "Jane Q", "given name taken from 'Last, First'"
    assert by_netid[f"jdoe{t}"]["email"] == f"jdoe{t}@wisc.edu"


def test_replace_refuses_an_upload_cut_at_the_row_limit(world: World):
    """Replace deactivates everyone missing from the upload; rows past the 1000-row limit
    are not processed, so their students must not be deactivated. Dry runs only: nothing
    is written either way."""
    w = world
    keep = f"keep{_tag()}"
    path = f"/courses/{w.course_a}/roster/import"
    w.ok(
        "POST",
        path,
        w.host_a,
        json={"rows": [{"netid": keep, "full_name": "Keep", "email": f"{keep}@example.com"}]},
    )
    rows = [{"netid": f"n{i}", "full_name": "S", "email": f"n{i}@example.com"} for i in range(1001)]

    r = w.req("POST", f"{path}?mode=replace&dry_run=true", w.host_a, json={"rows": rows})
    assert r.status_code == 422 and err(r) == "ROSTER_TOO_LARGE", r.text
    r = w.req("POST", f"{path}?mode=replace", w.host_a, json={"rows": rows})
    assert r.status_code == 422 and err(r) == "ROSTER_TOO_LARGE", r.text

    csv_text = "Student,SIS Login ID\nPoints Possible,\n" + "".join(
        f"Last{i}, First{i},n{i}@wisc.edu\n" for i in range(1001)
    )
    r = w.req(
        "POST",
        f"/courses/{w.course_a}/roster?mode=replace&dry_run=true",
        w.host_a,
        files={"file": ("roster.csv", csv_text.encode())},
    )
    assert r.status_code == 422 and err(r) == "ROSTER_TOO_LARGE", r.text

    # add_only never deactivates anyone, so it keeps the old behaviour: process the first
    # 1000 rows and report the rest.
    res = w.ok("POST", f"{path}?mode=add_only&dry_run=true", w.host_a, json={"rows": rows})
    assert res["imported"] == 1000 and res["deactivated"] == 0
    assert any("1000-row limit" in e for e in res["errors"])

    still = [e for e in w.ok("GET", f"/courses/{w.course_a}/roster", w.host_a) if e["netid"] == keep]
    assert still and still[0]["is_active"], "the existing student must not be deactivated"


# ---------------------------------------------------------------------------
# Locked games, downloads
# ---------------------------------------------------------------------------


async def test_played_game_is_locked_and_downloadable(world: World):
    w = world
    room, _, _ = await play_one_answer(w, w.game_a, w.course_a, finish=True)
    sid = room["session_id"]

    game = w.ok("GET", f"/games/{w.game_a}", w.host_a)
    assert game["locked"] is True
    for method, path, body in (
        ("POST", f"/games/{w.game_a}/questions", MC_QUESTION),
        ("PUT", f"/games/{w.game_a}/questions/{w.question_a}", {"prompt": "changed"}),
        ("DELETE", f"/games/{w.game_a}/questions/{w.question_a}", None),
        ("POST", f"/games/{w.game_a}/questions/reorder", {"order": [w.question_a]}),
    ):
        r = w.req(method, path, w.host_a, json=body)
        assert r.status_code == 409 and err(r) == "GAME_LOCKED", f"{method} {path}: {r.text}"
    # Title stays editable; a host can't delete a played game.
    w.ok("PUT", f"/games/{w.game_a}", w.host_a, json={"title": "Renamed after play"})
    r = w.req("DELETE", f"/games/{w.game_a}", w.host_a)
    assert r.status_code == 409 and err(r) == "GAME_LOCKED"

    csv_before = w.req("GET", f"/sessions/{sid}/export", w.host_a).content
    copy = w.ok("POST", f"/games/{w.game_a}/duplicate", w.host_a, status=201)
    w.track_game(copy["id"])
    assert copy["locked"] is False and copy["course_id"] == w.course_a
    copy_questions = w.ok("GET", f"/games/{copy['id']}/questions", w.host_a)
    assert len(copy_questions) == 1
    w.ok(
        "PUT",
        f"/games/{copy['id']}/questions/{copy_questions[0]['id']}",
        w.host_a,
        json={"prompt": "editable copy"},
    )
    assert w.req("GET", f"/sessions/{sid}/export", w.host_a).content == csv_before

    # Any HOST of the course may download; other courses may not.
    co_host, _ = w.user(("HOST", w.course_a))
    for q in ("report", "export", "export?format=canvas"):
        r = w.req("GET", f"/sessions/{sid}/{q}", co_host)
        assert r.status_code == 200, f"{q}: {r.text}"
        assert "attachment" in r.headers["content-disposition"]
        assert w.req("GET", f"/sessions/{sid}/{q}", w.host_b).status_code == 403
    assert sid in [s["session_id"] for s in w.ok("GET", f"/courses/{w.course_a}/sessions", co_host)]
    # Legacy endpoints keep working.
    assert w.req("GET", f"/admin/sessions/{sid}/report").status_code == 200
    assert w.req("GET", f"/game/sessions/{sid}/export").status_code == 200


# ---------------------------------------------------------------------------
# Live games and stale sessions
# ---------------------------------------------------------------------------


def test_live_game_blocks_edits_until_room_is_gone(world: World):
    w = world
    room = w.room(w.game_a, w.course_a)
    r = w.req("PUT", f"/games/{w.game_a}/questions/{w.question_a}", w.host_a, json={"prompt": "x"})
    assert r.status_code == 409 and err(r) == "GAME_LIVE"
    r = w.req("DELETE", f"/games/{w.game_a}", w.host_a)
    assert r.status_code == 409 and err(r) == "GAME_LIVE"
    r = w.req("GET", f"/sessions/{room['session_id']}/report", w.host_a)
    assert r.status_code == 409 and err(r) == "SESSION_NOT_FINISHED"

    redis_del_room(room["room_code"])
    w.ok("PUT", f"/games/{w.game_a}/questions/{w.question_a}", w.host_a, json={"prompt": "after expiry"})
    statuses = {s["session_id"]: s["status"] for s in w.ok("GET", "/admin/sessions")}
    assert statuses[room["session_id"]] == "ABANDONED"


async def test_stale_in_progress_session_becomes_downloadable(world: World):
    w = world
    room, host, player = await play_one_answer(w, w.game_a, w.course_a, finish=False)
    await host.disconnect()
    await player.disconnect()
    redis_del_room(room["room_code"])  # e.g. a restart lost the room

    sessions = w.ok("GET", f"/courses/{w.course_a}/sessions", w.host_a)
    match = [s for s in sessions if s["session_id"] == room["session_id"]]
    assert match and match[0]["status"] == "ABANDONED"
    assert w.req("GET", f"/sessions/{room['session_id']}/report", w.host_a).status_code == 200
    assert w.req("GET", f"/sessions/{room['session_id']}/export", w.host_a).status_code == 200


def test_admin_moving_a_game_grants_the_new_courses_hosts(world: World):
    w = world
    game, _ = w.admin_game(w.course_a)
    assert w.req("GET", f"/games/{game}", w.host_b).status_code == 403
    w.ok("PUT", f"/admin/games/{game}", json={"course_id": w.course_b})
    moved = w.ok("GET", f"/games/{game}", w.host_b)
    assert moved["course_id"] == w.course_b, "a HOST of the new course got a grant automatically"
    assert w.req("GET", f"/games/{game}", w.host_a).status_code == 403, "the old course's host lost access"


def test_admin_move_is_refused_for_live_games_unknown_and_system_courses(world: World, system_course: int):
    w = world
    game, _ = w.admin_game(w.course_a)
    r = w.req("PUT", f"/admin/games/{game}", json={"course_id": 99999999})
    assert r.status_code == 404
    r = w.req("PUT", f"/admin/games/{game}", json={"course_id": system_course})
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"

    room = w.room(game, w.course_a)
    r = w.req("PUT", f"/admin/games/{game}", json={"course_id": w.course_b})
    assert r.status_code == 409 and err(r) == "GAME_LIVE"
    assert w.ok("GET", f"/admin/games/{game}")["course_id"] == w.course_a
    redis_del_room(room["room_code"])


def test_only_admins_move_games(world: World):
    w = world
    r = w.req("PUT", f"/games/{w.game_a}", w.host_a, json={"course_id": w.course_b})
    assert r.status_code == 403


def test_question_prompts_are_sanitized_on_every_write_path(world: World):
    w = world
    dirty = "<script>alert(1)</script>Pick <b>A</b> <img src=x onerror=alert(2)>"
    created = w.ok(
        "POST", f"/games/{w.game_a}/questions", w.host_a, json={**MC_QUESTION, "prompt": dirty}, status=201
    )
    updated = w.ok(
        "PUT", f"/games/{w.game_a}/questions/{w.question_a}", w.host_a, json={"prompt": dirty}
    )
    bundle = {
        "format": "buzzer/game",
        "version": 1,
        "game": {"title": f"T4 import {_tag()}"},
        "questions": [{**MC_QUESTION, "prompt": dirty}],
    }
    imported = w.ok(
        "POST",
        f"/courses/{w.course_a}/games/import",
        w.host_a,
        files={"file": ("g.json", json.dumps(bundle).encode())},
        status=201,
    )
    w.track_game(imported["id"])
    imported_q = w.ok("GET", f"/games/{imported['id']}/questions", w.host_a)[0]
    for prompt in (created["prompt"], updated["prompt"], imported_q["prompt"]):
        assert "<script" not in prompt and "onerror" not in prompt and "<img" not in prompt, prompt
        assert "Pick" in prompt


async def test_host_deleting_a_session_ends_its_room(world: World):
    w = world
    room = w.room(w.game_a, w.course_a, w.host_a)
    code = room["room_code"]
    player = TestSocketClient(w.base, w.guest(code), "player")
    await player.connect()
    await player.emit("join_room", {"room_code": code, "role": "PLAYER"})
    await player.wait_for("sync_state")
    try:
        w.ok("DELETE", f"/game/sessions/{room['session_id']}", w.host_a, status=204)
        await player.wait_for("game_abandoned", timeout=5)
    finally:
        await player.disconnect()
    assert not redis_room_exists(code)
    sessions = w.ok("GET", f"/courses/{w.course_a}/sessions", w.host_a)
    assert all(s["session_id"] != room["session_id"] for s in sessions)
    # Another course's host can't delete it.
    other = w.room(w.game_a, w.course_a, w.host_a)
    assert w.req("DELETE", f"/game/sessions/{other['session_id']}", w.host_b).status_code == 403
    redis_del_room(other["room_code"])


async def _one_answer(w: World, host_token: str, code: str, guest_token: str) -> None:
    """Join a room as its host and as the given guest; the guest answers question 1."""
    host = TestSocketClient(w.base, host_token, "host")
    player = TestSocketClient(w.base, guest_token, "player")
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
            {"question_id": q["questionId"], "answer_data": {"selectedIndex": 0}, "answer_time_ms": 500},
        )
        await player.wait_for("answer_received")
    finally:
        await player.disconnect()
        await host.disconnect()


async def test_host_guest_merge_only_touches_its_own_session(world: World):
    """A guest account is reused by email, so one guest can have answers in another
    course's session. The host of session A may re-attribute the guest's answers in A,
    never those in B."""
    w = world
    game_b, _ = w.admin_game(w.course_b)
    room_a = w.room(w.game_a, w.course_a, w.host_a)
    room_b = w.room(game_b, w.course_b, w.host_b)

    email = f"merge.{_tag()}@example.com"
    tokens = [
        httpx.post(
            f"{w.base}/api/auth/guest",
            json={"display_name": "Merge Guest", "email": email, "room_code": room["room_code"]},
            timeout=10.0,
        ).json()["access_token"]
        for room in (room_a, room_b)
    ]
    await _one_answer(w, w.host_a, room_a["room_code"], tokens[0])
    await _one_answer(w, w.host_b, room_b["room_code"], tokens[1])

    guest_id = mysql(f"SELECT id FROM users WHERE email = '{email}'")
    w._users.append(guest_id)
    _, target_id = w.user(("PLAYER", w.course_a))
    netid = f"t4n{_tag()}"
    mysql(f"UPDATE users SET netid = '{netid}' WHERE id = '{target_id}'")

    def owners(session_id: str) -> set[str]:
        return set(mysql(f"SELECT user_id FROM session_scores WHERE session_id = '{session_id}'").split())

    assert owners(room_a["session_id"]) == {guest_id} == owners(room_b["session_id"])

    path = f"/game/sessions/{room_a['session_id']}/merge-guest"
    body = {"guest_user_id": guest_id, "target_netid": netid}
    w.ok("POST", path, w.host_a, json=body, status=204)

    assert owners(room_a["session_id"]) == {target_id}, "answers in the host's own session move"
    assert owners(room_b["session_id"]) == {guest_id}, "answers in another course's session stay"
    assert mysql(f"SELECT COUNT(*) FROM users WHERE id = '{guest_id}'") == "1", "guest still has scores"

    # Nothing left in session A for this guest: nothing to merge.
    r = w.req("POST", path, w.host_a, json=body)
    assert r.status_code == 404, r.text
    # Another course's host can't merge into session A at all.
    assert w.req("POST", path, w.host_b, json=body).status_code == 403


async def test_exports_work_with_non_ascii_titles(world: World):
    """A title in Chinese (alphanumeric, but not latin-1) used to make the download
    endpoints fail with a 500 while building the Content-Disposition header."""
    w = world
    game = w.ok(
        "POST", f"/courses/{w.course_a}/games", w.host_a, json={"title": "数据库基础"}, status=201
    )
    w.track_game(game["id"])
    for path in (f"/games/{game['id']}/export", f"/admin/games/{game['id']}/export"):
        r = w.req("GET", path, w.host_a if path.startswith("/games") else None)
        assert r.status_code == 200, f"{path}: {r.status_code}"
        r.headers["content-disposition"].encode("latin-1")
        assert "数据库基础" in r.content.decode(), "the bundle itself keeps the real title"

    # Canvas CSV with a Chinese assignment title (any readable session will do).
    room, host, player = await play_one_answer(w, w.game_a, w.course_a, finish=False)
    await host.disconnect()
    await player.disconnect()
    redis_del_room(room["room_code"])
    r = w.req(
        "GET",
        f"/sessions/{room['session_id']}/export?format=canvas&title=数据库",
        w.host_a,
    )
    assert r.status_code == 200, r.text
    r.headers["content-disposition"].encode("latin-1")


# ---------------------------------------------------------------------------
# Deletes
# ---------------------------------------------------------------------------


def test_host_delete_removes_empty_abandoned_lobby(world: World):
    w = world
    room = w.room(w.game_a, w.course_a)
    redis_del_room(room["room_code"])
    w.ok("DELETE", f"/games/{w.game_a}", w.host_a, status=204)
    assert room["session_id"] not in {s["session_id"] for s in w.ok("GET", "/admin/sessions")}


def backend_logged(event: str, session_id: str) -> bool:
    """True if the backend logged `event` for this session. A cancelled question timer leaves
    no socket trace (its host-room emit would need a socket still in the room), but a timer
    that expires logs `question_timer_expired` with its session id."""
    out = subprocess.run(
        ["docker", "compose", "logs", "--no-color", "backend"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return any(event in line and session_id in line for line in out.splitlines())


async def _start_timed_question(w: World, time_limit: int):
    """Open a room on a fresh game and start its (short) question. Returns
    (game_id, room, host, player); the caller disconnects both clients."""
    game_id, _ = w.admin_game(w.course_a, time_limit=time_limit)
    room = w.room(game_id, w.course_a)
    code = room["room_code"]
    host = TestSocketClient(w.base, w.admin, "host")
    player = TestSocketClient(w.base, w.guest(code), "player")
    await host.connect()
    await host.emit("join_room", {"room_code": code, "role": "HOST"})
    await host.wait_for("sync_state")
    await player.connect()
    await player.emit("join_room", {"room_code": code, "role": "PLAYER"})
    await player.wait_for("sync_state")
    await host.emit("host_advance", {})
    await player.wait_for("new_question")
    return game_id, room, host, player


async def test_question_timer_expiry_is_visible_in_backend_logs(world: World):
    """Control for the next test: without a delete, the timer expires and is logged, so
    the log probe really can see a timer that fires."""
    w = world
    game_id, room, host, player = await _start_timed_question(w, time_limit=2)
    try:
        await host.wait_for("answer_phase_ended", timeout=6)
        assert backend_logged("question_timer_expired", room["session_id"])
    finally:
        await player.disconnect()
        await host.disconnect()


async def test_admin_delete_ends_live_room(world: World):
    w = world
    game_id, room, host, player = await _start_timed_question(w, time_limit=2)
    code = room["room_code"]
    try:
        w.ok("DELETE", f"/admin/games/{game_id}", status=204)
        await player.wait_for("game_abandoned", timeout=5)
        # The question's timer must not fire after the delete. Its only effects are an
        # emit to the host room (which the host socket has left) and a log line, so the
        # log is what we check, after the 2 s limit has passed.
        await asyncio.sleep(4)
        assert not backend_logged("question_timer_expired", room["session_id"])
    finally:
        await player.disconnect()
        await host.disconnect()
    assert not redis_room_exists(code)
    assert w.req("GET", f"/admin/games/{game_id}").status_code == 404


async def test_admin_delete_leaves_a_room_key_owned_by_another_session(world: World):
    """Guard in end_session_from_rest: the room key is only deleted while it still holds
    this session's id. This cannot happen through the API today (game_sessions.room_code
    is UNIQUE, so a code is never reused), so the other session's room key is made by hand
    and only the key is asserted: no socket can be a bystander of a session that has no
    MySQL row."""
    w = world
    room = w.room(w.game_a, w.course_a)
    code = room["room_code"]
    other = {"session_id": f"other-{_tag()}", "status": "LOBBY", "course_id": w.course_b}
    redis_set_room(code, other)
    w.ok("DELETE", f"/admin/games/{w.game_a}", status=204)
    assert redis_get_room(code) == other
    redis_del_room(code)


# ---------------------------------------------------------------------------
# Players and guests
# ---------------------------------------------------------------------------


async def test_only_course_players_and_guests_can_join(world: World):
    w = world
    room = w.room(w.game_a, w.course_a)
    code = room["room_code"]
    outsider_token, _ = w.user(("PLAYER", w.course_b))
    outsider = TestSocketClient(w.base, outsider_token, "outsider")
    guest = TestSocketClient(w.base, w.guest(code), "guest")
    try:
        await outsider.connect()
        await outsider.emit("join_room", {"room_code": code, "role": "PLAYER"})
        e = await outsider.wait_for("error")
        assert "roster" in e["message"].lower()
        await guest.connect()
        await guest.emit("join_room", {"room_code": code, "role": "PLAYER"})
        await guest.wait_for("sync_state")
        # A guest token is never enough for the management API.
        assert w.req("GET", f"/courses/{w.course_a}/games", guest.token).status_code == 403
    finally:
        await outsider.disconnect()
        await guest.disconnect()
        redis_del_room(code)
