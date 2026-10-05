"""
Unit tests for services/image_service.py (docs/plans/t8-image-support.md §I, unit part):
normalise, the pure rules (aspect, quota, ETag), the config convention, export cleanup
and the 503 handler. No Docker; Pillow is needed.
"""

from __future__ import annotations

import random
import struct
import zlib
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy.exc import OperationalError
from structlog.testing import capture_logs

from app.common.exceptions import BuzzerError, register_exception_handlers
from app.services import image_service as s

UUID_A = "0b0c4f0e-2f6d-4f6e-9a55-3a8f5f2b7c11"
UUID_B = "7f1a0c52-1d9e-4a63-8c37-6d2e9b4a1f08"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def enc(img: Image.Image, fmt: str, **kw) -> bytes:
    out = BytesIO()
    img.save(out, fmt, **kw)
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    img = Image.open(BytesIO(data))
    img.load()
    return img


def noise(size: tuple[int, int], mode: str = "RGB", seed: int = 1) -> Image.Image:
    rnd = random.Random(seed)
    channels = len(mode) if mode != "P" else 1
    raw = bytes(rnd.getrandbits(8) for _ in range(size[0] * size[1] * channels))
    img = Image.frombytes("L" if mode == "P" else mode, size, raw)
    if mode == "P":
        img = img.convert("P")
        img.putpalette([rnd.getrandbits(8) for _ in range(768)])
    return img


RGB = Image.new("RGB", (200, 100), (10, 120, 200))


def mpo_bytes() -> bytes:
    frames = [Image.new("RGB", (50, 40), c) for c in ("red", "blue")]
    out = BytesIO()
    frames[0].save(out, "MPO", save_all=True, append_images=frames[1:])
    return out.getvalue()


def exif_rotated_jpeg() -> bytes:
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise to display
    return enc(RGB, "JPEG", exif=exif)


def png_with_text() -> bytes:
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "secret")
    return enc(RGB, "PNG", pnginfo=info)


def webp_with_exif() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    return enc(RGB, "WEBP", exif=exif)


def big_png() -> bytes:
    return enc(Image.linear_gradient("L").resize((3000, 2000)).convert("RGB"), "PNG")


def palette_png_with_transparency() -> bytes:
    return enc(Image.new("P", (10, 10)), "PNG", transparency=0)


def cmyk_jpeg() -> bytes:
    return enc(Image.new("CMYK", (10, 10), (0, 50, 100, 0)), "JPEG")


REENCODE_FIXTURES = {
    "exif_jpeg": exif_rotated_jpeg,
    "big_png": big_png,
    "palette_png": palette_png_with_transparency,
    "cmyk_jpeg": cmyk_jpeg,
    "png_text": png_with_text,
    "webp_exif": webp_with_exif,
    "mpo": mpo_bytes,
}


def assert_clean_and_idempotent(data: bytes, **kw) -> None:
    once = s.normalise(data, **kw)
    assert s._is_clean(opened(once.data))
    assert s.normalise(once.data, **kw).data == once.data


# ---------------------------------------------------------------------------
# normalise: accepted inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt,content_type",
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_small_clean_image_is_stored_byte_for_byte(fmt, content_type):
    data = enc(RGB, fmt)
    result = s.normalise(data)
    assert result.data == data
    assert (result.content_type, result.width, result.height) == (
        content_type,
        200,
        100,
    )
    assert result.size_bytes == len(data)


def test_large_image_is_shrunk_keeping_aspect():
    result = s.normalise(big_png())
    assert (result.width, result.height) == (1600, 1067)


def test_exif_orientation_is_applied_and_removed():
    result = s.normalise(exif_rotated_jpeg())
    assert (result.width, result.height) == (100, 200)
    assert len(opened(result.data).getexif()) == 0


@pytest.mark.parametrize(
    "data,fmt",
    [
        (png_with_text(), "PNG"),
        (enc(RGB, "PNG", icc_profile=b"\0" * 128), "PNG"),
        (enc(RGB, "JPEG", comment=b"secret"), "JPEG"),
    ],
)
def test_metadata_is_removed(data, fmt):
    img = opened(s.normalise(data).data)
    assert img.format == fmt
    assert set(img.info) <= s._CLEAN_INFO_KEYS


def test_alpha_is_kept_and_palette_transparency_becomes_rgba():
    alpha = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
    assert opened(s.normalise(enc(alpha, "PNG")).data).mode == "RGBA"
    assert opened(s.normalise(palette_png_with_transparency()).data).mode == "RGBA"


def test_cmyk_jpeg_becomes_rgb():
    assert opened(s.normalise(cmyk_jpeg()).data).mode == "RGB"


def test_sixteen_bit_grey_is_scaled_not_clamped():
    grey = Image.new("I;16", (4, 1))
    grey.putdata([0, 256, 32768, 65535])
    img = opened(s.normalise(enc(grey, "PNG")).data)
    assert img.mode == "L"
    assert list(img.getdata()) == [0, 1, 128, 255]


def test_mpo_and_plain_jpeg_are_stored_as_jpeg():
    assert opened(mpo_bytes()).format == "MPO"
    plain = enc(RGB, "JPEG")
    assert not hasattr(opened(plain), "n_frames") or opened(plain).n_frames == 1
    for data in (mpo_bytes(), plain):
        result = s.normalise(data)
        assert result.content_type == "image/jpeg"
        assert opened(result.data).format == "JPEG"


# ---------------------------------------------------------------------------
# normalise: the size retries of step 7 (forced by a small limit)
# ---------------------------------------------------------------------------


def _retry_input(fmt: str, quality: int) -> bytes:
    """Noise that must be re-encoded (a metadata block), saved at `quality`."""
    img = noise((300, 300))
    if fmt == "JPEG":
        return enc(img, "JPEG", quality=quality, comment=b"x")
    exif = Image.Exif()
    exif[0x010F] = "x"
    return enc(img, "WEBP", quality=quality, exif=exif)


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP"])
@pytest.mark.parametrize("input_quality,expected_quality", [(75, 70), (50, 55)])
def test_lossy_retries_lower_the_quality(fmt, input_quality, expected_quality):
    data = _retry_input(fmt, input_quality)
    result = s.normalise(data, max_bytes=len(data))
    reference = opened(data).convert("RGB")
    reference.info.clear()
    assert result.data == enc(reference, fmt, quality=expected_quality)
    assert_clean_and_idempotent(data, max_bytes=len(data))


def test_png_retries_shrink_the_dimensions():
    # A palette PNG is re-encoded as RGB: about three times larger than the input.
    data = enc(noise((300, 300), "P"), "PNG")
    limit = int(len(data) * 1.2)
    result = s.normalise(data, max_bytes=limit)
    assert (result.width, result.height) == (150, 150)
    assert result.size_bytes <= limit
    assert_clean_and_idempotent(data, max_bytes=limit)
    smaller = s.normalise(data, max_bytes=int(len(data) * 2.0))
    assert (smaller.width, smaller.height) == (225, 225)
    assert_clean_and_idempotent(data, max_bytes=int(len(data) * 2.0))


def test_image_that_never_fits_is_too_large(monkeypatch):
    monkeypatch.setattr(s, "_PNG_SCALES", (1.0, 0.95, 0.9))
    data = enc(noise((300, 300), "P"), "PNG")
    with pytest.raises(BuzzerError) as exc:
        s.normalise(data, max_bytes=int(len(data) * 1.2))
    assert (exc.value.status_code, exc.value.code) == (413, "IMAGE_TOO_LARGE")
    assert "could not be reduced" in exc.value.message


@pytest.mark.parametrize("name", sorted(REENCODE_FIXTURES))
def test_reencoded_output_is_clean_and_idempotent(name):
    assert_clean_and_idempotent(REENCODE_FIXTURES[name]())


def test_identical_stored_bytes_share_a_sha():
    a = s.normalise(png_with_text())
    info = PngImagePlugin.PngInfo()
    info.add_text("Other", "different")
    b = s.normalise(enc(RGB, "PNG", pnginfo=info))
    assert a.data == b.data and a.sha256 == b.sha256


# ---------------------------------------------------------------------------
# normalise: the error table of spec C
# ---------------------------------------------------------------------------


def _png_header_only(width: int, height: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )


def _animated(fmt: str) -> bytes:
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "blue")]
    out = BytesIO()
    frames[0].save(out, fmt, save_all=True, append_images=frames[1:])
    return out.getvalue()


@pytest.mark.parametrize(
    "name,data,status,code",
    [
        ("text", b"hello, not an image", 415, "UNSUPPORTED_IMAGE_TYPE"),
        ("empty", b"", 415, "UNSUPPORTED_IMAGE_TYPE"),
        (
            "svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
            415,
            "UNSUPPORTED_IMAGE_TYPE",
        ),
        ("gif", enc(RGB, "GIF"), 415, "UNSUPPORTED_IMAGE_TYPE"),
        ("animated png", _animated("PNG"), 415, "UNSUPPORTED_IMAGE_TYPE"),
        ("animated webp", _animated("WEBP"), 415, "UNSUPPORTED_IMAGE_TYPE"),
        ("truncated png", big_png()[:4000], 400, "INVALID_IMAGE"),
        ("truncated jpeg", enc(noise((64, 64)), "JPEG")[:600], 400, "INVALID_IMAGE"),
        ("truncated clean jpeg", enc(RGB, "JPEG")[:-200], 400, "INVALID_IMAGE"),
        ("over 2 MiB", b"\0" * (2 * 1024 * 1024 + 1), 413, "IMAGE_TOO_LARGE"),
        ("pixel bomb", _png_header_only(5000, 5000), 413, "IMAGE_TOO_LARGE"),
    ],
)
def test_error_table(name, data, status, code):
    with pytest.raises(BuzzerError) as exc:
        s.normalise(data)
    assert (exc.value.status_code, exc.value.code) == (status, code), name


def test_pixel_bomb_is_never_decoded(monkeypatch):
    def fail(*_a, **_k):
        raise AssertionError("load() must not run for a pixel bomb")

    monkeypatch.setattr(PngImagePlugin.PngImageFile, "load", fail)
    with pytest.raises(BuzzerError) as exc:
        s.normalise(_png_header_only(5000, 5000))
    assert exc.value.code == "IMAGE_TOO_LARGE"


def test_colour_mode_outside_the_table_is_invalid():
    with pytest.raises(BuzzerError) as exc:
        s._to_output_mode(Image.new("F", (2, 2)), "PNG")
    assert (exc.value.status_code, exc.value.code) == (400, "INVALID_IMAGE")


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "old,new,changed",
    [
        ((100, 100), (101, 100), False),  # exactly 1.00 %
        ((1000, 1000), (1000, 990), True),  # 1.0101 % (relative to the new height)
        ((10000, 10000), (10099, 10000), False),  # 0.99 %
        ((10000, 10000), (10101, 10000), True),  # 1.01 %
        ((400, 300), (800, 600), False),  # identical ratio
        ((50, 50), (50, 49), True),  # very small image
        ((1600, 1000), (1600, 1001), False),
        ((1_000_000, 1), (1_000_000, 1), False),  # very large values
    ],
)
def test_aspect_rule(old, new, changed):
    assert s.aspect_changed(*old, *new) is changed


def test_quota_counts_and_bytes():
    mib = 1024 * 1024
    s.check_quota(49, 0, 1)
    with pytest.raises(BuzzerError) as exc:
        s.check_quota(50, 0, 1)
    assert (exc.value.status_code, exc.value.code) == (409, "IMAGE_LIMIT")
    s.check_quota(10, 24 * mib, mib)
    with pytest.raises(BuzzerError):
        s.check_quota(10, 24 * mib, mib + 1)
    # A replace frees the old bytes and does not add to the count.
    s.check_quota(50, 25 * mib, 2 * mib, replaced_bytes=2 * mib)
    with pytest.raises(BuzzerError):
        s.check_quota(50, 25 * mib, 2 * mib + 1, replaced_bytes=2 * mib)


SHA = "a" * 64


@pytest.mark.parametrize(
    "header,match",
    [
        (f'"{SHA}"', True),
        (f'"other", "{SHA}"', True),
        (f'W/"{SHA}"', True),
        ("*", True),
        ('"other"', False),
        (None, False),
        ("", False),
    ],
)
def test_if_none_match(header, match):
    assert s.etag_matches(header, SHA) is match


# ---------------------------------------------------------------------------
# The config convention
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "qtype,config",
    [
        ("multiple_choice", {"options": ["a", "b"]}),
        ("true_false", {"image_id": UUID_A}),
        ("fill_in_the_blank", {"image_id": None}),
        (
            "multiple_choice",
            {"options": ["a", "b"], "option_image_ids": [UUID_A, None]},
        ),
        ("multi_select", {"options": ["a", "b"], "option_image_ids": [None, None]}),
        ("true_false", {"option_image_ids": None}),
        ("multiple_choice", "not a dict"),
    ],
)
def test_valid_image_fields(qtype, config):
    s.validate_image_fields(qtype, config)


@pytest.mark.parametrize(
    "qtype,config",
    [
        ("multiple_choice", {"image_id": "not-a-uuid"}),
        ("multiple_choice", {"image_id": UUID_A.upper()}),
        ("multiple_choice", {"image_id": 5}),
        ("multiple_choice", {"options": ["a", "b"], "option_image_ids": [UUID_A]}),
        ("true_false", {"option_image_ids": []}),
        ("multiple_choice", {"options": ["a", "b"], "option_image_ids": [UUID_A, 7]}),
        ("multiple_choice", {"options": ["a", "b"], "option_image_ids": "abc"}),
        ("multi_select", {"options": ["a", "b"], "option_image_ids": [None, "img1"]}),
    ],
)
def test_invalid_image_fields(qtype, config):
    with pytest.raises(BuzzerError) as exc:
        s.validate_image_fields(qtype, config)
    assert (exc.value.status_code, exc.value.code) == (422, "INVALID_IMAGE_REFERENCE")


def test_image_ids_is_tolerant_and_ordered():
    config = {
        "image_id": UUID_B,
        "option_image_ids": [UUID_A, None, 5, "x", {"a": 1}, UUID_B],
    }
    assert s.image_ids(config) == [UUID_B, UUID_A]
    assert s.image_ids({"image_id": 5, "option_image_ids": "abc"}) == []
    assert s.image_ids(None) == []
    assert s.image_ids([UUID_A]) == []


def test_remap_returns_a_deep_copy_and_touches_only_image_fields():
    config = {
        "options": ["img1", "Dog"],
        "image_id": "img1",
        "option_image_ids": ["img1", None],
        "other": {"image_id": "img1"},
    }
    before = repr(config)
    out = s.remap_image_ids(config, {"img1": UUID_A}, on_missing="error")
    assert repr(config) == before
    assert out == {
        "options": ["img1", "Dog"],
        "image_id": UUID_A,
        "option_image_ids": [UUID_A, None],
        "other": {"image_id": "img1"},
    }
    out["other"]["image_id"] = "changed"
    assert config["other"]["image_id"] == "img1"


def test_remap_passes_non_strings_through_and_handles_missing():
    config = {"image_id": 5, "option_image_ids": "abc"}
    assert s.remap_image_ids(config, {}, on_missing="error") == config
    config = {"image_id": "gone", "option_image_ids": [None, 3, "gone"]}
    assert s.remap_image_ids(config, {}, on_missing="null") == {
        "image_id": None,
        "option_image_ids": [None, 3, None],
    }
    with pytest.raises(s.UnknownImageKey) as exc:
        s.remap_image_ids(config, {}, on_missing="error")
    assert exc.value.value == "gone"
    assert s.remap_image_ids("x", {}, on_missing="error") == "x"


def test_export_cleanup_of_dirty_configs():
    mapping = {UUID_A: "img1"}
    ctx = {"game_id": 1, "question_id": 2}
    out = s.export_config(
        "multiple_choice", {"options": ["a", "b"], "image_id": 5}, mapping, **ctx
    )
    assert out["image_id"] is None
    out = s.export_config(
        "multiple_choice",
        {"options": ["a", "b"], "option_image_ids": [UUID_A]},
        mapping,
        **ctx,
    )
    assert "option_image_ids" not in out
    out = s.export_config(
        "multiple_choice", {"options": ["a"], "option_image_ids": "x"}, mapping, **ctx
    )
    assert "option_image_ids" not in out
    out = s.export_config(
        "true_false", {"option_image_ids": [UUID_A, None]}, mapping, **ctx
    )
    assert "option_image_ids" not in out
    out = s.export_config(
        "multi_select",
        {
            "options": ["a", "b", "c"],
            "option_image_ids": [UUID_A, 4, UUID_B],
            "image_id": UUID_B,
        },
        mapping,
        **ctx,
    )
    assert out == {
        "options": ["a", "b", "c"],
        "option_image_ids": ["img1", None, None],
        "image_id": None,
    }
    # The cleaned config passes the import's structure check.
    s.validate_image_fields(
        "multi_select", s.remap_image_ids(out, {"img1": UUID_A}, on_missing="error")
    )


def test_export_cleanup_logs_each_change():
    with capture_logs() as logs:
        s.export_config(
            "multiple_choice",
            {"options": ["a", "b"], "image_id": UUID_B, "option_image_ids": [7, None]},
            {},
            game_id=9,
            question_id=3,
        )
    events = [(e["event"], e["game_id"], e["question_id"]) for e in logs]
    assert events == [
        ("export_image_reference_nulled", 9, 3),
        ("export_image_id_dropped", 9, 3),
    ]


# ---------------------------------------------------------------------------
# The 503 handler
# ---------------------------------------------------------------------------


class _DriverError(Exception):
    pass


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/op/{code}")
    async def op(code: int):
        raise OperationalError("SELECT 1", {}, _DriverError(code, "driver message"))

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    @app.get("/buzzer")
    async def buzzer():
        raise BuzzerError("GAME_LOCKED", "locked", 409)

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("code", [1205, 1213])
def test_lock_conflicts_are_503_try_again(code):
    r = _client().get(f"/op/{code}")
    assert r.status_code == 503
    assert r.json()["error"] == "TRY_AGAIN"


def test_other_operational_errors_get_the_generic_500():
    client = _client()
    r = client.get("/op/2013")  # lost connection
    assert r.status_code == 500
    assert r.json() == client.get("/boom").json()
    r = client.get("/buzzer")
    assert (r.status_code, r.json()["error"]) == (409, "GAME_LOCKED")
