"""T7 admin interface: an admin creates and edits numeric_estimate and plot_point questions in
the admin app (Courses -> a game's "Questions" link), with the same editor the host app uses.
Checked through the API afterwards, so the saved questions are what the server holds."""

from __future__ import annotations

import time

from .test_t7_plot_point_ui import TARGET, tap_grid


def poll(read, expected, seconds: float = 5.0):
    """The editor saves, then reloads; wait until the server shows the new value."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = read()
        if value == expected:
            return value
        time.sleep(0.2)
    assert read() == expected


def questions(api, gid: int) -> list[dict]:
    return api.get(f"/admin/games/{gid}/questions").json()


def test_admin_authors_and_edits_both_new_types(api, web, game, pages):
    gid = game["game"]
    title = api.get(f"/games/{gid}").json()["title"]
    page = pages(api.token)

    # The dev database keeps every course earlier test runs created (there is no course delete
    # route), and the Courses page lists them all. Show only this test's course, so the run does
    # not depend on how much has piled up; the link and the editor are still the real ones.
    def only_this_test(route):
        body = route.fetch().json()
        keep = [x for x in body if x.get("course_id", x["id"]) == game["course"]]
        route.fulfill(json=keep)

    page.route("**/api/admin/courses", only_this_test)
    page.route("**/api/admin/games", only_this_test)

    # Courses page -> the game's Questions link (no direct URL: this is the admin path).
    page.goto(f"{web}/admin/courses")
    row = page.get_by_text(title).locator(
        "xpath=ancestor::div[contains(@class,'justify-between')][1]"
    )
    row.get_by_role("link", name="Questions").click()
    page.wait_for_url(f"**/admin/courses/{game['course']}/games/{gid}/questions")

    # numeric_estimate: create, then edit the target.
    page.get_by_role("button", name="Add Question").click()
    page.locator("select").first.select_option("numeric_estimate")
    page.get_by_placeholder("Question text…").fill("How many keys does a piano have?")
    page.get_by_placeholder("e.g. 1665").fill("88")
    page.get_by_placeholder("steps, years, m…").fill("keys")
    page.get_by_role("button", name="Save Question").click()
    page.get_by_text("Target:").wait_for()
    (q,) = questions(api, gid)
    assert q["type"] == "numeric_estimate" and q["answer_data"]["target"] == 88
    assert q["config"] == {"unit": "keys"}

    page.get_by_role("button", name="Edit", exact=True).click()
    page.get_by_placeholder("e.g. 1665").fill("90")
    page.get_by_role("button", name="Save Question").click()
    poll(lambda: questions(api, gid)[0]["answer_data"]["target"], 90)

    # plot_point: create by clicking the preview, then edit the prompt.
    page.get_by_role("button", name="Add Question").click()
    page.locator("select").first.select_option("plot_point")
    page.get_by_placeholder("Question text…").fill("Where do the two lines meet?")
    save = page.get_by_role("button", name="Save Question")
    assert save.is_disabled()  # no target yet
    tap_grid(page, "[data-testid=plot-scatter]", *TARGET)
    page.get_by_test_id("plot-target").get_by_text("(2, 5)").wait_for()
    assert save.is_enabled()
    save.click()
    page.get_by_text("Target (2, 5) · 20×20 grid").wait_for()
    qs = questions(api, gid)
    assert [x["type"] for x in qs] == ["numeric_estimate", "plot_point"]
    assert qs[1]["answer_data"]["target"] == {"x": 2, "y": 5}

    page.get_by_role("button", name="Edit", exact=True).nth(1).click()
    page.get_by_placeholder("Question text…").fill("Tap the intersection")
    page.get_by_role("button", name="Save Question").click()
    poll(lambda: questions(api, gid)[1]["prompt"], "Tap the intersection")

    assert pages.errors == []
