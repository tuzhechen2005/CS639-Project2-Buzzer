"""T8 in the browser: the host editor's image library and pickers, and images on the
host and phone game screens, including the loading placeholder and the failure fallback."""

from __future__ import annotations

from .conftest import guest_token
from .helpers import loaded, picture, polygon, start_game, upload


def test_editor_image_library_and_pickers(api, web, game, pages, tmp_path):
    gid = game["game"]
    a = tmp_path / "a.png"
    a.write_bytes(picture("ALPHA", (30, 90, 170)))
    b = tmp_path / "b.png"
    b.write_bytes(picture("BETA", (160, 60, 40)))
    same_shape = tmp_path / "a2.png"
    same_shape.write_bytes(picture("ALPHA 2", (20, 130, 90), (800, 600)))
    square = tmp_path / "sq.png"
    square.write_bytes(picture("SQUARE", (120, 40, 140), (300, 300)))
    big = tmp_path / "big.png"
    big.write_bytes(
        b"\x89PNG" + b"\0" * (2 * 1024 * 1024 + 10)
    )  # refused before sending

    page = pages(api.token)
    page.goto(f"{web}/host/courses/{game['course']}/games/{gid}/questions")
    page.get_by_text("Image library").wait_for()
    upload_input = page.locator("input[type=file]").first
    upload_input.set_input_files(str(a))
    page.get_by_text("Unused").first.wait_for()
    upload_input.set_input_files(str(b))
    page.wait_for_function(
        "() => document.body.innerText.split('Unused').length - 1 === 2"
    )
    upload_input.set_input_files(str(big))
    page.get_by_text("images can be at most 2 MB").wait_for()
    assert len(api.get(f"/games/{gid}/images").json()) == 2

    images = {i["sha256"]: i["id"] for i in api.get(f"/games/{gid}/images").json()}
    first, second = (api.get(f"/games/{gid}/images").json()[k]["id"] for k in (0, 1))

    page.get_by_role("button", name="Add Question").click()
    page.get_by_placeholder("Question text…").fill("Which colour is this?")
    page.get_by_placeholder("Option 1").fill("Blue")
    page.get_by_placeholder("Option 2").fill("Red")
    page.get_by_title("Prompt image: choose").click()
    page.locator(f"div.absolute.z-20 button:has(img[src*='{first}'])").click()
    page.get_by_title("Image for option 2: choose").click()
    page.locator(f"div.absolute.z-20 button:has(img[src*='{second}'])").click()
    page.get_by_role("button", name="Save Question").click()
    page.get_by_text("Used by Q1").first.wait_for()
    config = api.get(f"/games/{gid}/questions").json()[0]["config"]
    assert config == {
        "options": ["Blue", "Red"],
        "option_image_ids": [None, second],
        "image_id": first,
    }

    # Refusals from the server are shown, not swallowed.
    card = page.locator(
        "div.rounded-lg.border", has=page.locator(f"img[src*='{first}']")
    ).first
    card.get_by_title("Delete image").click()
    page.get_by_text("is used by Q1").wait_for()
    replace_input = card.locator("input[type=file]")
    replace_input.set_input_files(str(square))
    page.get_by_text("different shape").wait_for()
    replace_input.set_input_files(str(same_shape))
    page.wait_for_function(
        "id => [...document.images].some(i => i.src.includes(id) && i.naturalWidth === 800)",
        arg=first,
    )
    after = {i["id"]: i for i in api.get(f"/games/{gid}/images").json()}
    assert after[first]["width"] == 800 and after[first]["sha256"] not in images

    # Clearing the prompt image frees it; then it can be deleted.
    page.get_by_role("button", name="Edit", exact=True).click()
    page.get_by_title("Prompt image: remove").click()
    page.get_by_role("button", name="Save Question").click()
    page.get_by_text("Unused").wait_for()
    assert "image_id" not in api.get(f"/games/{gid}/questions").json()[0]["config"]
    card.get_by_title("Delete image").click()
    page.wait_for_function("() => !document.body.innerText.includes('Unused')")
    assert [i["id"] for i in api.get(f"/games/{gid}/images").json()] == [second]
    assert not pages.errors


def test_images_on_the_game_screens(api, web, game, pages):
    gid = game["game"]
    prompt = upload(api, gid, picture("PROMPT", (40, 90, 160), (800, 450)))
    tri, hexa = upload(api, gid, polygon(3)), upload(api, gid, polygon(6))
    slow, broken = upload(api, gid, polygon(5)), upload(api, gid, polygon(8))
    for body in (
        {
            "prompt": "Which has more sides?",
            "config": {
                "options": ["Three", "Six", "Text only"],
                "image_id": prompt,
                "option_image_ids": [tri, hexa, None],
            },
            "points": [0.0, 1.0, 0.0],
        },
        {
            "prompt": "Slow and broken",
            "config": {
                "options": ["Slow one", "Broken one"],
                "option_image_ids": [slow, broken],
            },
            "points": [1.0, 0.0],
        },
    ):
        r = api.post(
            f"/games/{gid}/questions",
            json={
                "type": "multiple_choice",
                "grading_type": "ACCURACY",
                "prompt": body["prompt"],
                "config": body["config"],
                "answer_data": {"answer_points": body["points"]},
                "time_limit_seconds": 60,
                "points_value": 1.0,
            },
        )
        assert r.status_code == 201, r.text

    host, phone = start_game(
        api,
        game,
        lambda: pages(api.token),
        lambda token: pages(token, phone=True, block=[broken], delay=[slow]),
        web,
        guest_token,
    )
    # Question 1: prompt image on the host, option pictures inside the phone's buttons.
    host.wait_for_function(
        "() => [...document.images].some(i => i.alt === 'Image for the question' && i.naturalWidth > 0)"
    )
    phone.wait_for_function(
        "() => [...document.images].filter(i => i.naturalWidth > 0).length === 2"
    )
    assert loaded(phone, "Three") and loaded(phone, "Six")
    assert phone.get_by_role("button", name="Text only").count() == 1
    assert not phone.evaluate(
        "[...document.images].some(i => i.alt === 'Image for the question')"
    ), "phones never show the prompt image"
    phone.get_by_role("button", name="Six").click()

    host.get_by_role("button", name="Show Results").click()
    host.wait_for_url("**/results")
    host.wait_for_function(
        "() => [...document.images].filter(i => i.naturalWidth > 0).length === 3"
    )  # prompt + 2 thumbnails
    host.get_by_role("button", name="Next Question").click()

    # Question 2: a slow image shows a placeholder, a failed one leaves the text button.
    phone.get_by_role("button", name="Slow one").wait_for()
    phone.get_by_role("button", name="Broken one").wait_for()
    phone.wait_for_function("() => !document.querySelector('img[alt=\"Broken one\"]')")
    assert phone.locator("button:has-text('Slow one') .animate-pulse").count() == 1
    phone.get_by_role("button", name="Broken one").click()  # still answerable

    host.get_by_role("button", name="Show Results").click()
    host.wait_for_url("**/results")
    host.get_by_role("button", name="Show Final Results").click()
    phone.wait_for_url("**/gameover")
    phone.wait_for_function(
        "() => [...document.images].some(i => i.alt === 'Image for the question' && i.naturalWidth > 0)"
    )
    assert not pages.errors
