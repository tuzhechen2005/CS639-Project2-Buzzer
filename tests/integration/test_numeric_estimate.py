"""
numeric_estimate (docs/plans/t7-numeric-estimate.md, MR B): authoring and validation (create
and update), banded scoring over real sockets, the distribution and reveal sent to the host,
answer validation, COMPLETENESS, export/import, the report and the locked-game rule.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import subprocess
import uuid

import httpx

from .engine.socket_client import TestSocketClient

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent

BANDS = [{"within": 5, "points": 100}, {"within": 15, "points": 50}, {"within": 30, "points": 25}]
NUMERIC = {
    "type": "numeric_estimate",
    "grading_type": "ACCURACY",
    "prompt": "How many steps does the Eiffel Tower have?",
    "config": {"unit": "steps"},
    "answer_data": {"target": 1665, "mode": "relative", "bands": BANDS},
    "time_limit_seconds": 30,
    "points_value": 100,
}


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _api(base_url: str) -> str:
    return f"{base_url}/api"


def _err(r: httpx.Response) -> str:
    try:
        return r.json().get("error", "")
    except ValueError:
        return ""


def _mysql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "mysql", "sh", "-c",
         'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" buzzer -e "$0"', sql],
        cwd=_REPO_ROOT, check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def _post_question(base_url, token, game_id, body, status=201):
    r = httpx.post(f"{_api(base_url)}/admin/games/{game_id}/questions", json=body, headers=_h(token), timeout=10.0)
    assert r.status_code == status, f"{status} expected, got {r.status_code}: {r.text}"
    return r.json()


def _guest(base_url: str, code: str) -> str:
    tag = uuid.uuid4().hex[:8]
    r = httpx.post(
        f"{_api(base_url)}/auth/guest",
        json={"display_name": f"G{tag}", "email": f"g.{tag}@example.com", "room_code": code},
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------


def test_numeric_create_update_delete_and_validation(game_setup, base_url, admin_token):
    game_id = game_setup["game_id"]
    created = _post_question(base_url, admin_token, game_id, NUMERIC)
    qid = created["id"]
    assert created["config"] == {"unit": "steps"} and created["answer_data"]["target"] == 1665

    bad = {
        "target 0 in relative mode": {**NUMERIC, "answer_data": {"target": 0, "mode": "relative", "bands": BANDS}},
        "unsorted within": {**NUMERIC, "answer_data": {"target": 5, "mode": "absolute",
                            "bands": [{"within": 9, "points": 100}, {"within": 3, "points": 50}]}},
        "points not decreasing": {**NUMERIC, "answer_data": {"target": 5, "mode": "absolute",
                                  "bands": [{"within": 1, "points": 100}, {"within": 3, "points": 100}]}},
        "no bands": {**NUMERIC, "answer_data": {"target": 5, "mode": "absolute", "bands": []}},
        "six bands": {**NUMERIC, "answer_data": {"target": 5, "mode": "absolute",
                      "bands": [{"within": i + 1, "points": 100 - i} for i in range(6)]}},
        "bool target": {**NUMERIC, "answer_data": {"target": True, "mode": "absolute", "bands": BANDS}},
        "unknown mode": {**NUMERIC, "answer_data": {"target": 5, "mode": "log", "bands": BANDS}},
        "points_value differs": {**NUMERIC, "points_value": 7},
        "long unit": {**NUMERIC, "config": {"unit": "x" * 21}},
    }
    for name, body in bad.items():
        r = httpx.post(f"{_api(base_url)}/admin/games/{game_id}/questions", json=body, headers=_h(admin_token), timeout=10.0)
        assert r.status_code == 422, f"{name}: {r.status_code} {r.text}"

    def get_q():
        r = httpx.get(f"{_api(base_url)}/admin/games/{game_id}/questions", headers=_h(admin_token), timeout=10.0)
        return next(q for q in r.json() if q["id"] == qid)

    def put(body):
        return httpx.put(f"{_api(base_url)}/admin/games/{game_id}/questions/{qid}", json=body,
                         headers=_h(admin_token), timeout=10.0)

    # Update enforces the same structure as create, on the merged result.
    before = get_q()
    r = put({"answer_data": {"target": 0, "mode": "relative", "bands": BANDS}})
    assert r.status_code == 422 and _err(r) == "VALIDATION_ERROR", r.text
    assert "relative mode needs a non-zero target" in r.json()["message"]
    r = put({"type": "multiple_choice"})  # leaves a numeric config under a new type
    assert r.status_code == 422, r.text
    r = put({"points_value": 3})
    assert r.status_code == 422, r.text
    assert get_q() == before, "a rejected update leaves the stored question unchanged"

    assert put({"time_limit_seconds": 45}).status_code == 200
    assert put({"prompt": "Steps on the Eiffel Tower?"}).status_code == 200
    assert put({"answer_data": {"target": 1665, "mode": "relative",
                                "bands": [{"within": 10, "points": 100}, {"within": 20, "points": 40}]}}).status_code == 200

    # A legacy-style change on another type still works.
    mc = _post_question(base_url, admin_token, game_id, {
        "type": "multiple_choice", "grading_type": "ACCURACY", "prompt": "Pick A",
        "config": {"options": ["A", "B"]}, "answer_data": {"answer_points": [1, 0]}, "points_value": 1})
    r = httpx.put(f"{_api(base_url)}/admin/games/{game_id}/questions/{mc['id']}", json={"prompt": "Pick B"},
                  headers=_h(admin_token), timeout=10.0)
    assert r.status_code == 200
    r = httpx.put(f"{_api(base_url)}/admin/games/{game_id}/questions/{mc['id']}", json={"config": {"options": ["A"]}},
                  headers=_h(admin_token), timeout=10.0)
    assert r.status_code == 422, "update now validates every type"

    r = httpx.delete(f"{_api(base_url)}/admin/games/{game_id}/questions/{qid}", headers=_h(admin_token), timeout=10.0)
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Playing
# ---------------------------------------------------------------------------


async def _play(base_url, admin_token, game_setup, question, answers, *, invalid_first=None):
    """One question, one guest per entry of `answers` (a list of answer_data dicts).
    Returns (room, new_question payload, answer_received list, host question_results,
    host game_over)."""
    headers = _h(admin_token)
    game_id, course_id = game_setup["game_id"], game_setup["course_id"]
    _post_question(base_url, admin_token, game_id, question)
    room = httpx.post(f"{_api(base_url)}/game/rooms", json={"game_id": game_id, "course_id": course_id},
                      headers=headers, timeout=10.0).json()
    code = room["room_code"]
    host = TestSocketClient(base_url, admin_token, "host")
    players = [TestSocketClient(base_url, _guest(base_url, code), f"p{i}") for i in range(len(answers))]
    try:
        await host.connect()
        await host.emit("join_room", {"room_code": code, "role": "HOST"})
        await host.wait_for("sync_state")
        for p in players:
            await p.connect()
            await p.emit("join_room", {"room_code": code, "role": "PLAYER"})
            await p.wait_for("sync_state")
        await host.emit("host_advance", {})
        payloads = [await p.wait_for("new_question") for p in players]
        if invalid_first:
            for bad in invalid_first:
                await players[0].emit("submit_answer", {"question_id": payloads[0]["questionId"],
                                                        "answer_data": bad, "answer_time_ms": 100})
                err = await players[0].wait_for("error", timeout=5)
                assert "numeric" in err["message"]
        received = []
        for p, payload, answer in zip(players, payloads, answers):
            await p.emit("submit_answer", {"question_id": payload["questionId"], "answer_data": answer, "answer_time_ms": 500})
            received.append(await p.wait_for("answer_received"))
        # duplicate submission is acknowledged and not scored twice
        await players[0].emit("submit_answer", {"question_id": payloads[0]["questionId"],
                                                "answer_data": answers[0], "answer_time_ms": 600})
        dup = await players[0].wait_for("answer_received")
        assert dup.get("alreadyAnswered") is True
        await host.emit("host_advance", {})
        results = await host.wait_for("question_results", timeout=10)
        await host.emit("host_advance", {})
        over = await host.wait_for("game_over", timeout=10)
    finally:
        for p in players:
            await p.disconnect()
        await host.disconnect()
    return room, payloads[0], received, results, over


async def test_numeric_banded_scoring_distribution_and_reveal(game_setup, base_url, admin_token):
    room, payload, received, results, over = await _play(
        base_url, admin_token, game_setup, NUMERIC,
        [{"value": 1700}, {"value": 1900}, {"value": 2300}],
        invalid_first=[{"value": "1700"}, {"value": True}, {"value": 1e16}, {"value": None}, {}],
    )
    assert [r["pointsAwarded"] for r in received] == [100, 50, 0]
    assert [r["isCorrect"] for r in received] == [True, False, False]

    # What a player sees: the unit, never the answer key.
    assert payload["type"] == "numeric_estimate" and payload["config"] == {"unit": "steps"}
    assert "answer_data" not in json.dumps(payload) and "target" not in json.dumps(payload)

    # What the host sees after the question closes.
    assert results["answerDistribution"] == {"0": 1, "1": 1, "miss": 1}
    assert set(results["answerReveal"]) == {"type", "target", "mode", "bands"}
    assert results["answerReveal"]["target"] == 1665 and results["answerReveal"]["bands"] == BANDS

    # The game-over summary recomputes the same distribution from the stored answers.
    summary = over["questionSummary"][0]
    assert summary["answerDistribution"] == results["answerDistribution"]
    assert summary["answerReveal"]["type"] == "numeric_estimate"
    assert summary["config"] == {"unit": "steps"}

    # Rejected submissions recorded nothing: exactly the three valid answers exist.
    assert _mysql(f"SELECT COUNT(*) FROM session_scores WHERE session_id = '{room['session_id']}'") == "3"


async def test_numeric_absolute_mode_and_negative_values(game_setup, base_url, admin_token):
    year = {**NUMERIC, "prompt": "Year of the French Revolution?", "config": {},
            "answer_data": {"target": 1789, "mode": "absolute",
                            "bands": [{"within": 1, "points": 10}, {"within": 5, "points": 4}]},
            "points_value": 10}
    _, _, received, results, _ = await _play(
        base_url, admin_token, game_setup, year, [{"value": 1789}, {"value": 1793}, {"value": -50}])
    assert [r["pointsAwarded"] for r in received] == [10, 4, 0]
    assert results["answerDistribution"] == {"0": 1, "1": 1, "miss": 1}


async def test_numeric_completeness_gives_full_points_to_any_number(game_setup, base_url, admin_token):
    soft = {**NUMERIC, "grading_type": "COMPLETENESS", "answer_data": {}, "points_value": 5}
    _, _, received, results, _ = await _play(
        base_url, admin_token, game_setup, soft, [{"value": 3}, {"value": -999999}])
    assert [r["pointsAwarded"] for r in received] == [5, 5]
    assert results["answerReveal"] == {"type": "completeness"}
    assert results["answerDistribution"] == {}


async def test_played_numeric_game_is_locked(game_setup, base_url, admin_token):
    room, _, _, _, _ = await _play(base_url, admin_token, game_setup, NUMERIC, [{"value": 1665}])
    game_id = game_setup["game_id"]
    qs = httpx.get(f"{_api(base_url)}/admin/games/{game_id}/questions", headers=_h(admin_token), timeout=10.0).json()
    r = httpx.put(f"{_api(base_url)}/admin/games/{game_id}/questions/{qs[0]['id']}", json={"prompt": "changed"},
                  headers=_h(admin_token), timeout=10.0)
    assert r.status_code == 409 and _err(r) == "GAME_LOCKED"


# ---------------------------------------------------------------------------
# Export / import and the report
# ---------------------------------------------------------------------------


def test_numeric_export_import_roundtrip(game_setup, base_url, admin_token):
    game_id, course_id = game_setup["game_id"], game_setup["course_id"]
    _post_question(base_url, admin_token, game_id, NUMERIC)
    exported = httpx.get(f"{_api(base_url)}/admin/games/{game_id}/export", headers=_h(admin_token), timeout=10.0)
    assert exported.status_code == 200
    bundle = exported.json()
    assert bundle["version"] == 1 and bundle["questions"][0]["type"] == "numeric_estimate"
    r = httpx.post(f"{_api(base_url)}/admin/games/import?course_id={course_id}",
                   files={"file": ("g.json", exported.content)}, headers=_h(admin_token), timeout=10.0)
    assert r.status_code == 201, r.text
    new_id = r.json()["game_id"]
    try:
        qs = httpx.get(f"{_api(base_url)}/admin/games/{new_id}/questions", headers=_h(admin_token), timeout=10.0).json()
        assert qs[0]["answer_data"] == NUMERIC["answer_data"] and qs[0]["config"] == {"unit": "steps"}
        # an invalid numeric question in a file is rejected with 4xx and no game is created
        bundle["questions"][0]["answer_data"] = {"target": 0, "mode": "relative", "bands": BANDS}
        before = httpx.get(f"{_api(base_url)}/admin/games", headers=_h(admin_token), timeout=10.0).json()
        r = httpx.post(f"{_api(base_url)}/admin/games/import?course_id={course_id}",
                       files={"file": ("g.json", json.dumps(bundle).encode())}, headers=_h(admin_token), timeout=10.0)
        assert r.status_code == 400 and _err(r) == "INVALID_IMPORT", r.text
        after = httpx.get(f"{_api(base_url)}/admin/games", headers=_h(admin_token), timeout=10.0).json()
        assert len(after) == len(before)
    finally:
        httpx.delete(f"{_api(base_url)}/admin/games/{new_id}", headers=_h(admin_token), timeout=10.0)


async def test_numeric_report_has_badge_and_missed_bar(game_setup, base_url, admin_token):
    room, _, _, _, _ = await _play(
        base_url, admin_token, game_setup, NUMERIC, [{"value": 1700}, {"value": 2300}])
    r = httpx.get(f"{_api(base_url)}/admin/sessions/{room['session_id']}/report",
                  headers=_h(admin_token), timeout=10.0)
    assert r.status_code == 200, r.text
    page = r.text
    assert "Numeric Estimate" in page
    assert '<span class="bar-label">Within 5 %</span>' in page
    assert '<span class="bar-label">Within 30 %</span>' in page
    assert '<span class="bar-label">Missed</span>' in page


async def test_fractional_points_keep_max_possible_score(game_setup, base_url, admin_token):
    """maxPossibleScore was cast to int, so a 7.5-point question reported 7."""
    bands = [{"within": 5, "points": 7.5}, {"within": 15, "points": 2.5}]
    question = {**NUMERIC, "points_value": 7.5, "answer_data": {**NUMERIC["answer_data"], "bands": bands}}
    _, _, received, _, over = await _play(base_url, admin_token, game_setup, question, [{"value": 1665}])
    assert received[0]["pointsAwarded"] == 7.5
    assert over["maxPossibleScore"] == 7.5
