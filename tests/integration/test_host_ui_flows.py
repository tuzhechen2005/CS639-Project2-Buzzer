"""
T4 host/admin UI flows (docs/plans/t4-ui-restructuring.md §E, §F, test plan §H, step 8).

test_host_management.py covers the backend permission and integrity rules. This file covers
the endpoint behaviour the restructured host and admin screens rely on: the course picker,
readable error bodies, building a game question by question, JSON import/export, Duplicate,
CSV roster upload and single-entry edits, admin course moves and inactive grants, and the
Past Sessions downloads. Runs against the live Docker stack and reuses the `world` fixture
(two courses, a HOST of each, an admin-created game in course A), which cleans up the users
and games it tracks.
"""

from __future__ import annotations

import json

import pytest

from .test_host_management import (  # noqa: F401  (system_course, world are fixtures)
    MC_QUESTION,
    World,
    _tag,
    err,
    play_one_answer,
    system_course,
    world,
)

TF_QUESTION = {
    "type": "true_false",
    "grading_type": "ACCURACY",
    "prompt": "The sky is green.",
    "config": {},
    "answer_data": {"answer_points": {"true": 0.0, "false": 1.0}},
    "time_limit_seconds": 20,
    "points_value": 1.0,
}

FITB_QUESTION = {
    "type": "fill_in_the_blank",
    "grading_type": "ACCURACY",
    "prompt": "Chemical symbol for gold?",
    "config": {},
    "answer_data": {"acceptedAnswers": ["Au"], "answerPoints": [1.0], "editDistance": 0},
    "time_limit_seconds": 20,
    "points_value": 1.0,
}


def _prompts(w: World, game_id: int, token: str) -> list[str]:
    return [q["prompt"] for q in w.ok("GET", f"/games/{game_id}/questions", token)]


# ---------------------------------------------------------------------------
# Course picker and error bodies (host HomePage / CourseLayout, every api.ts)
# ---------------------------------------------------------------------------


def test_course_picker_lists_only_hosted_courses(world: World):
    w = world
    mine = {c["id"] for c in w.ok("GET", "/game/my-courses", w.host_a)}
    assert w.course_a in mine and w.course_b not in mine
    everything = {c["id"] for c in w.ok("GET", "/game/my-courses")}  # admin
    assert {w.course_a, w.course_b} <= everything


def test_error_bodies_carry_a_readable_message(world: World):
    """The frontends show body.message (then a string detail, then detail[].msg)."""
    w = world
    for r in (
        w.req("GET", f"/courses/{w.course_a}/games", w.host_b),  # 403
        w.req("GET", "/games/999999999"),  # 404
        w.req("POST", f"/admin/users/{w.host_b_id}/game-access", json={"game_id": w.game_a}),  # 409
    ):
        body = r.json()
        assert r.status_code in (403, 404, 409), r.text
        assert isinstance(body.get("error"), str) and body["error"]
        assert isinstance(body.get("message"), str) and body["message"].strip()
    assert err(w.req("POST", f"/admin/users/{w.host_b_id}/game-access", json={"game_id": w.game_a})) == "NOT_COURSE_HOST"

    r = w.req("POST", f"/courses/{w.course_a}/roster/import?mode=wipe", w.host_a, json={"rows": []})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and all(isinstance(d.get("msg"), str) for d in detail)


# ---------------------------------------------------------------------------
# Game management by a host (GamesTab, QuestionEditorPage)
# ---------------------------------------------------------------------------


def test_host_builds_edits_reorders_and_deletes_questions(world: World):
    w = world
    g = w.ok(
        "POST",
        f"/courses/{w.course_a}/games",
        w.host_a,
        json={"title": "Host quiz", "description": "d", "max_players": 40},
        status=201,
    )
    w.track_game(g["id"])
    gid = g["id"]
    assert g["course_id"] == w.course_a and g["locked"] is False
    assert gid in [x["id"] for x in w.ok("GET", f"/courses/{w.course_a}/games", w.host_a)]

    # Add three questions; order follows creation.
    created = [
        w.ok("POST", f"/games/{gid}/questions", w.host_a, json=q, status=201)
        for q in (MC_QUESTION, TF_QUESTION, FITB_QUESTION)
    ]
    ids = [q["id"] for q in created]
    listed = w.ok("GET", f"/games/{gid}/questions", w.host_a)
    assert [q["id"] for q in listed] == ids
    assert [q["order_index"] for q in listed] == [0, 1, 2]

    # Edit prompt and scoring; prompts are sanitized (only b, i, br, u survive).
    w.ok(
        "PUT",
        f"/games/{gid}/questions/{ids[0]}",
        w.host_a,
        json={
            "prompt": "Pick <b>B</b><script>alert(1)</script>",
            "answer_data": {"answer_points": [0.0, 1.0]},
        },
    )
    edited = w.ok("GET", f"/games/{gid}/questions", w.host_a)[0]
    assert "<b>B</b>" in edited["prompt"] and "<script>" not in edited["prompt"]
    assert edited["answer_data"]["answer_points"] == [0.0, 1.0]

    # Reorder (reverse) and check the new order sticks.
    w.ok("POST", f"/games/{gid}/questions/reorder", w.host_a, json={"order": ids[::-1]}, status=204)
    assert [q["id"] for q in w.ok("GET", f"/games/{gid}/questions", w.host_a)] == ids[::-1]

    # Delete one; the other two remain in order.
    w.ok("DELETE", f"/games/{gid}/questions/{ids[1]}", w.host_a, status=204)
    assert [q["id"] for q in w.ok("GET", f"/games/{gid}/questions", w.host_a)] == [ids[2], ids[0]]

    # Game details header.
    upd = w.ok(
        "PUT", f"/games/{gid}", w.host_a, json={"title": "Renamed", "description": "", "max_players": 25}
    )
    assert (upd["title"], upd["description"], upd["max_players"]) == ("Renamed", "", 25)

    # Another course's host can do none of this.
    assert w.req("POST", f"/games/{gid}/questions", w.host_b, json=MC_QUESTION).status_code == 403
    assert w.req("PUT", f"/games/{gid}", w.host_b, json={"title": "x"}).status_code == 403


def test_export_then_import_round_trips_into_the_course(world: World):
    w = world
    w.ok("POST", f"/games/{w.game_a}/questions", w.host_a, json=TF_QUESTION, status=201)
    r = w.req("GET", f"/games/{w.game_a}/export", w.host_a)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    bundle = r.json()
    assert bundle["format"] == "buzzer/game" and bundle["version"] == 1
    assert "course_id" not in bundle and "course_id" not in bundle["game"]

    imported = w.ok(
        "POST",
        f"/courses/{w.course_a}/games/import",
        w.host_a,
        files={"file": ("quiz.json", json.dumps(bundle).encode(), "application/json")},
        status=201,
    )
    w.track_game(imported["id"])
    assert imported["course_id"] == w.course_a and imported["locked"] is False
    assert imported["title"] == bundle["game"]["title"]
    src = w.ok("GET", f"/games/{w.game_a}/questions", w.host_a)
    dst = w.ok("GET", f"/games/{imported['id']}/questions", w.host_a)
    keys = ("type", "grading_type", "prompt", "config", "answer_data", "points_value")
    assert [{k: q[k] for k in keys} for q in dst] == [{k: q[k] for k in keys} for q in src]

    # The importing host is granted the game; another course's host can't reach it.
    assert w.req("GET", f"/games/{imported['id']}", w.host_b).status_code == 403

    # Bad files are 400 INVALID_IMPORT with a message the UI can show.
    for raw in (b"not json", json.dumps({**bundle, "version": 99}).encode()):
        r = w.req(
            "POST",
            f"/courses/{w.course_a}/games/import",
            w.host_a,
            files={"file": ("bad.json", raw, "application/json")},
        )
        assert r.status_code == 400 and err(r) == "INVALID_IMPORT" and r.json()["message"]


def test_duplicate_copies_questions_in_order_and_grants_only_the_duplicator(world: World):
    w = world
    for q in (TF_QUESTION, FITB_QUESTION):
        w.ok("POST", f"/games/{w.game_a}/questions", w.host_a, json=q, status=201)
    ids = [q["id"] for q in w.ok("GET", f"/games/{w.game_a}/questions", w.host_a)]
    w.ok("POST", f"/games/{w.game_a}/questions/reorder", w.host_a, json={"order": ids[::-1]}, status=204)
    original_prompts = _prompts(w, w.game_a, w.host_a)

    co_host, co_id = w.user(("HOST", w.course_a))
    w.ok("POST", f"/admin/users/{co_id}/game-access", json={"game_id": w.game_a}, status=204)

    copy = w.ok("POST", f"/games/{w.game_a}/duplicate", w.host_a, status=201)
    w.track_game(copy["id"])
    original = w.ok("GET", f"/games/{w.game_a}", w.host_a)
    assert copy["title"] == f"{original['title']} (copy)"
    assert copy["course_id"] == w.course_a and copy["locked"] is False
    assert _prompts(w, copy["id"], w.host_a) == original_prompts

    # Grants aren't copied: the co-host sees the original but not the copy.
    co_list = [g["id"] for g in w.ok("GET", f"/courses/{w.course_a}/games", co_host)]
    assert w.game_a in co_list and copy["id"] not in co_list
    assert w.req("GET", f"/games/{copy['id']}", co_host).status_code == 403


# ---------------------------------------------------------------------------
# Roster (RosterTab)
# ---------------------------------------------------------------------------


def _canvas_csv(netids: list[str]) -> bytes:
    lines = [
        "Student,ID,SIS User ID,SIS Login ID,Section",
        "    Points Possible,,,,",
    ] + [f'"Student, N{i}",{i},S{i},{n}@example.edu,LEC' for i, n in enumerate(netids)]
    return ("\n".join(lines) + "\n").encode()


def test_roster_csv_upload_preview_add_and_single_entry_toggle(world: World):
    w = world
    t = _tag()
    netids = [f"ra{t}", f"rb{t}", f"rc{t}"]
    path = f"/courses/{w.course_a}/roster"

    def upload(ids: list[str], query: str = "") -> dict:
        return w.ok(
            "POST",
            f"{path}{query}",
            w.host_a,
            files={"file": ("roster.csv", _canvas_csv(ids), "text/csv")},
        )

    # Dry run saves nothing.
    preview = upload(netids, "?dry_run=true")
    assert (preview["imported"], preview["deactivated"]) == (3, 0)
    assert not [e for e in w.ok("GET", path, w.host_a) if e["netid"] in netids]

    # Real add-only upload.
    res = upload(netids)
    assert (res["imported"], res["updated"], res["deactivated"]) == (3, 0, 0)
    entries = {e["netid"]: e for e in w.ok("GET", path, w.host_a) if e["netid"] in netids}
    assert set(entries) == set(netids) and all(e["is_active"] for e in entries.values())

    # Replace with one student deactivates the other two (preview first, then for real).
    assert upload(netids[:1], "?mode=replace&dry_run=true")["deactivated"] == 2
    assert upload(netids[:1], "?mode=replace")["deactivated"] == 2
    active = {e["netid"] for e in w.ok("GET", path, w.host_a) if e["is_active"]}
    assert netids[0] in active and not (set(netids[1:]) & active)

    # Toggle a single entry from the table.
    entry_id = entries[netids[1]]["id"]
    on = w.ok("PATCH", f"{path}/{entry_id}", w.host_a, json={"is_active": True})
    assert on["is_active"] is True and on["netid"] == netids[1]
    off = w.ok("PATCH", f"{path}/{entry_id}", w.host_a, json={"is_active": False})
    assert off["is_active"] is False

    # Another course's host can't upload here.
    r = w.req("POST", path, w.host_b, files={"file": ("r.csv", _canvas_csv(netids), "text/csv")})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Admin CoursesPage and UserDetailPage
# ---------------------------------------------------------------------------


def test_admin_moves_game_to_another_course(world: World, system_course: int):
    w = world
    admin_view = {g["id"]: g for g in w.ok("GET", "/admin/games")}
    assert admin_view[w.game_a]["course_id"] == w.course_a and admin_view[w.game_a]["locked"] is False

    # Moving into the system course is refused.
    r = w.req("PUT", f"/admin/games/{w.game_a}", json={"course_id": system_course})
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"

    moved = w.ok("PUT", f"/admin/games/{w.game_a}", json={"course_id": w.course_b})
    assert moved["course_id"] == w.course_b

    # Course B's hosts gain it; course A's host loses access (their grant is now inactive).
    assert w.game_a in [g["id"] for g in w.ok("GET", f"/courses/{w.course_b}/games", w.host_b)]
    assert w.game_a not in [g["id"] for g in w.ok("GET", f"/courses/{w.course_a}/games", w.host_a)]
    assert w.req("GET", f"/games/{w.game_a}", w.host_a).status_code == 403
    assert w.game_a in w.ok("GET", f"/admin/users/{w.host_a_id}")["game_access"]


def test_admin_cannot_move_a_live_game(world: World):
    w = world
    room = w.room(w.game_a, w.course_a)
    try:
        r = w.req("PUT", f"/admin/games/{w.game_a}", json={"course_id": w.course_b})
        assert r.status_code == 409 and err(r) == "GAME_LIVE"
        assert w.ok("GET", f"/admin/games/{w.game_a}")["course_id"] == w.course_a
    finally:
        w.ok("DELETE", f"/game/sessions/{room['session_id']}", status=204)


def test_system_course_roster_uploads_are_refused(world: World, system_course: int):
    w = world
    sid = system_course
    r = w.req(
        "POST",
        f"/courses/{sid}/roster",
        files={"file": ("roster.csv", _canvas_csv([f"sys{_tag()}"]), "text/csv")},
    )
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"
    r = w.req(
        "POST",
        f"/courses/{sid}/roster/import",
        json={"rows": [{"netid": f"sys{_tag()}", "full_name": "S", "email": "s@example.com"}]},
    )
    assert r.status_code == 409 and err(r) == "SYSTEM_COURSE"
    assert w.ok("GET", f"/admin/courses/{sid}/access") == []

def test_revoking_host_leaves_an_inactive_grant_until_restored(world: World):
    w = world
    w.ok("GET", f"/games/{w.game_a}", w.host_a)
    w.ok("DELETE", f"/admin/users/{w.host_a_id}/course-access/{w.course_a}", status=204)

    assert w.req("GET", f"/games/{w.game_a}", w.host_a).status_code == 403
    assert w.course_a not in {c["id"] for c in w.ok("GET", "/game/my-courses", w.host_a)}
    detail = w.ok("GET", f"/admin/users/{w.host_a_id}")
    assert w.game_a in detail["game_access"]  # shown as "inactive" in the admin UI
    assert all(ca["course_id"] != w.course_a for ca in detail["course_access"])

    w.grant_course(w.host_a_id, w.course_a, "HOST")
    assert w.ok("GET", f"/games/{w.game_a}", w.host_a)["id"] == w.game_a


# ---------------------------------------------------------------------------
# Past Sessions tab
# ---------------------------------------------------------------------------


async def test_past_sessions_tab_lists_and_downloads_a_finished_session(world: World):
    w = world
    room, _, _ = await play_one_answer(w, w.game_a, w.course_a, finish=True)
    sid = room["session_id"]

    items = [s for s in w.ok("GET", f"/courses/{w.course_a}/sessions", w.host_a) if s["session_id"] == sid]
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "COMPLETED" and item["player_count"] == 1
    assert item["game_id"] == w.game_a and item["course_id"] == w.course_a
    assert item["room_code"] == room["room_code"] and item["game_title"]

    report = w.req("GET", f"/sessions/{sid}/report", w.host_a)
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/html")

    raw = w.req("GET", f"/sessions/{sid}/export?format=raw", w.host_a)
    assert raw.status_code == 200 and raw.headers["content-type"].startswith("text/csv")
    header, *rows = [line for line in raw.text.splitlines() if line]
    assert header.split(",") == ["Player", "Q1", "Total"] and len(rows) == 1

    canvas = w.req(
        "GET",
        f"/sessions/{sid}/export?format=canvas&title=Quiz%201%20(42)&sis_domain=wisc.edu&roster_only=false",
        w.host_a,
    )
    assert canvas.status_code == 200
    first = canvas.text.splitlines()[0]
    assert first.startswith("Student,ID,SIS User ID,SIS Login ID,Section") and "Quiz 1 (42)" in first

    # A played game is locked, but export still works (Export JSON stays available).
    assert w.ok("GET", f"/games/{w.game_a}", w.host_a)["locked"] is True
    assert w.req("GET", f"/games/{w.game_a}/export", w.host_a).status_code == 200


def test_course_sessions_list_is_course_scoped(world: World):
    w = world
    r = w.req("GET", f"/courses/{w.course_a}/sessions", w.host_b)
    assert r.status_code == 403
    assert isinstance(w.ok("GET", f"/courses/{w.course_b}/sessions", w.host_b), list)


@pytest.mark.parametrize(
    "path",
    [
        "/courses/{a}/roster",
        "/courses/{a}/games",
        "/courses/{a}/sessions",
        "/games/{g}",
        "/games/{g}/questions",
        "/games/{g}/export",
        "/sessions/{s}/report",
        "/sessions/{s}/export",
    ],
)
def test_guest_token_cannot_use_host_screens(world: World, path: str):
    w = world
    room = w.room(w.game_a, w.course_a)
    guest = w.guest(room["room_code"])
    r = w.req("GET", path.format(a=w.course_a, g=w.game_a, s=room["session_id"]), guest)
    assert r.status_code == 403
    w.ok("DELETE", f"/game/sessions/{room['session_id']}", status=204)
