"""
nginx limits for T8 (docs/plans/t8-image-support.md §G, §I): the two narrow locations
that raise client_max_body_size, the default 1 MB everywhere else, and the per-address
request limit. These need the proxy, so they use --nginx-url (default :8080) and skip
when it is not reachable. Each check would fail under nginx's default 1 MB limit.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import test_host_management
from .test_host_management import World
from .test_images import MIB, noise_png

world = test_host_management.world  # the shared pytest fixture

_TIMEOUT = 120.0


def _h(w: World) -> dict:
    return {"Authorization": f"Bearer {w.admin}"}


def _post_file(url: str, w: World, size_or_data, path: str) -> httpx.Response:
    data = size_or_data if isinstance(size_or_data, bytes) else b"x" * size_or_data
    return httpx.post(f"{url}{path}", headers=_h(w), files={"file": ("f", data)}, timeout=_TIMEOUT)


def _from_nginx(r: httpx.Response) -> bool:
    return r.headers.get("server", "").startswith("nginx")


def test_body_limits(world: World, nginx_url: str):
    w = world
    gid, _ = w.admin_game(w.course_a)
    image = noise_png(830, 3)
    assert 2 * MIB - 40_000 < len(image) <= 2 * MIB

    # The image location raised the limit: a 2 MiB image goes through.
    r = _post_file(nginx_url, w, image, f"/api/games/{gid}/images")
    assert r.status_code == 201, r.text
    # ...but only to 3 MB.
    r = _post_file(nginx_url, w, 8 * MIB, f"/api/games/{gid}/images")
    assert r.status_code == 413 and _from_nginx(r) and "json" not in r.headers.get("content-type", "")

    # Import location: 5 MB reaches the backend (not JSON → 400), 45 MB does not.
    r = _post_file(nginx_url, w, 5 * MIB, f"/api/courses/{w.course_a}/games/import")
    assert r.status_code == 400 and r.json()["error"] == "INVALID_IMPORT", r.text
    r = _post_file(nginx_url, w, 5 * MIB, f"/api/admin/games/import?course_id={w.course_a}")
    assert r.status_code == 400 and r.json()["error"] == "INVALID_IMPORT", r.text
    r = _post_file(nginx_url, w, 45 * MIB, f"/api/courses/{w.course_a}/games/import")
    assert r.status_code == 413 and _from_nginx(r)

    # Everything else keeps the 1 MB default.
    r = httpx.post(f"{nginx_url}/api/auth/guest", content=b"x" * (2 * MIB), timeout=_TIMEOUT)
    assert r.status_code == 413 and _from_nginx(r)
    for path in (f"/api/games/{gid}/imagesXYZ", f"/api/games/{gid}/images/", f"/api/games/{gid}/images/a/b"):
        r = _post_file(nginx_url, w, 2 * MIB, path)
        assert r.status_code == 413 and _from_nginx(r), path


def test_request_rate_limit(world: World, nginx_url: str):
    w = world
    gid, _ = w.admin_game(w.course_a)
    time.sleep(3)  # let earlier requests drain from the bucket

    def one(_):
        return httpx.get(f"{nginx_url}/api/games/{gid}/images", headers=_h(w), timeout=_TIMEOUT).status_code

    with ThreadPoolExecutor(10) as pool:
        statuses = list(pool.map(one, range(30)))
    assert 429 in statuses, statuses
    assert 200 in statuses, statuses
    time.sleep(3)
    assert one(0) == 200
