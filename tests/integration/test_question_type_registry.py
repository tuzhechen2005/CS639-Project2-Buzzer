"""
Question-type registry (docs/plans/t7-numeric-estimate.md, MR A): the downloadable HTML
report now covers multi_select questions (badge and per-option bar chart), and an unknown
question type is still rejected on create and update.
"""

from __future__ import annotations

import subprocess
import pathlib
import uuid

import httpx

from .engine.socket_client import TestSocketClient

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent

MS_QUESTION = {
    "type": "multi_select",
    "grading_type": "ACCURACY",
    "prompt": "Pick the vowels",
    "config": {"options": ["A", "B", "E"]},
    "answer_data": {"answer_points": [1, -1, 1]},
    "time_limit_seconds": 30,
    "points_value": 2,
}


def _redis_del_room(code: str) -> None:
    subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "DEL", f"room:{code}"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )


async def test_report_covers_multi_select(game_setup, base_url, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    game_id, course_id = game_setup["game_id"], game_setup["course_id"]
    r = httpx.post(
        f"{base_url}/api/admin/games/{game_id}/questions", json=MS_QUESTION, headers=headers, timeout=10.0
    )
    assert r.status_code == 201, r.text

    room = httpx.post(
        f"{base_url}/api/game/rooms",
        json={"game_id": game_id, "course_id": course_id},
        headers=headers,
        timeout=10.0,
    ).json()
    code = room["room_code"]
    tag = uuid.uuid4().hex[:8]
    guest = httpx.post(
        f"{base_url}/api/auth/guest",
        json={"display_name": f"G{tag}", "email": f"g.{tag}@example.com", "room_code": code},
        timeout=10.0,
    ).json()["access_token"]

    host = TestSocketClient(base_url, admin_token, "host")
    player = TestSocketClient(base_url, guest, "player")
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
            {"question_id": q["questionId"], "answer_data": {"selectedIndices": [0, 2]}, "answer_time_ms": 500},
        )
        done = await player.wait_for("answer_received")
        assert done["pointsAwarded"] == 2 and done["isCorrect"] is True
    finally:
        await player.disconnect()
        await host.disconnect()
    _redis_del_room(code)  # as if the room had expired: the session becomes downloadable

    r = httpx.get(
        f"{base_url}/api/admin/sessions/{room['session_id']}/report", headers=headers, timeout=10.0
    )
    assert r.status_code == 200, r.text
    page = r.text
    assert "Multi Select" in page and "badge-ms" in page
    # (the CSS also contains these class names, so look for the rendered rows)
    assert '<div class="bar-chart"><div class="bar-row">' in page, "per-option bar chart"
    assert page.count('bar-correct-mark">✓') == 2, "the two options that earn points are marked"
    assert '<span class="bar-label">A A</span>' in page


def test_unknown_question_type_is_still_rejected(game_setup, base_url, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    game_id = game_setup["game_id"]
    body = {**MS_QUESTION, "type": "numeric_estimate_not_yet"}
    r = httpx.post(f"{base_url}/api/admin/games/{game_id}/questions", json=body, headers=headers, timeout=10.0)
    assert r.status_code == 422
    created = httpx.post(
        f"{base_url}/api/admin/games/{game_id}/questions", json=MS_QUESTION, headers=headers, timeout=10.0
    ).json()
    r = httpx.put(
        f"{base_url}/api/admin/games/{game_id}/questions/{created['id']}",
        json={"type": "nope"},
        headers=headers,
        timeout=10.0,
    )
    assert r.status_code == 422
