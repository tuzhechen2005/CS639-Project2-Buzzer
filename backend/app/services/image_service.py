"""
Images stored in MySQL, owned by a game (docs/plans/t8-image-support.md).

Everything about images lives here: the limits, decoding and re-encoding uploads
(`normalise`), quotas, the `config` reference convention (`image_id`,
`option_image_ids`) and its checks, and the image rows themselves. Question and game
services call into this module; schemas and the T7 registry do not.

The pure functions (no database) come first so they can be unit-tested without the
stack. Like every service, this module never imports routers/ or websocket/.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal

import structlog
from fastapi import UploadFile
from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ..common.exceptions import BuzzerError, NotFoundError
from ..models.game import Image, Question

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Limits (spec B). MiB = 1,048,576 bytes.
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 1600
MAX_PIXELS = 16_000_000
MAX_IMAGES_PER_GAME = 50
MAX_BYTES_PER_GAME = 25 * 1024 * 1024
MAX_BUNDLE_BYTES = 40 * 1024 * 1024
MAX_CONCURRENT_DECODES = 2
MAX_CONCURRENT_BUNDLE_OPS = 2

decode_slots = asyncio.Semaphore(MAX_CONCURRENT_DECODES)
bundle_slots = asyncio.Semaphore(MAX_CONCURRENT_BUNDLE_OPS)

OPTION_IMAGE_TYPES = ("multiple_choice", "multi_select")

_CANONICAL_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def new_image_id() -> str:
    return str(uuid.uuid4())


def is_canonical_id(value: Any) -> bool:
    """The lowercase, hyphenated form str(uuid.uuid4()) produces; nothing else."""
    return isinstance(value, str) and bool(_CANONICAL_ID.match(value))


# ---------------------------------------------------------------------------
# Errors (spec C: the only mapping of image-reading problems)
# ---------------------------------------------------------------------------


def image_too_large(
    message: str = "The image is too large (at most 2 MiB and 16 megapixels)",
) -> BuzzerError:
    return BuzzerError("IMAGE_TOO_LARGE", message, 413)


def unsupported_image(
    message: str = "Only PNG, JPEG and WebP images are supported",
) -> BuzzerError:
    return BuzzerError("UNSUPPORTED_IMAGE_TYPE", message, 415)


def invalid_image(
    message: str = "The image file is damaged or could not be read",
) -> BuzzerError:
    return BuzzerError("INVALID_IMAGE", message, 400)


def image_limit(message: str) -> BuzzerError:
    return BuzzerError("IMAGE_LIMIT", message, 409)


def invalid_reference(message: str) -> BuzzerError:
    return BuzzerError("INVALID_IMAGE_REFERENCE", message, 422)


# ---------------------------------------------------------------------------
# normalise: bytes in, stored bytes out (spec C)
# ---------------------------------------------------------------------------

# MPO has no opener of its own: Pillow's JPEG opener returns an MpoImageFile for
# multi-frame JPEGs, so "MPO" must not be listed (it would raise KeyError). WebP is
# registered lazily, hence init().
PILImage.init()
_ALLOWED_FORMATS = ["PNG", "JPEG", "WEBP"]
_CONTENT_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "MPO": "image/jpeg",
    "WEBP": "image/webp",
}
_OUTPUT_FORMAT = {"PNG": "PNG", "JPEG": "JPEG", "MPO": "JPEG", "WEBP": "WEBP"}
_ALLOWED_MODES = {
    "PNG": {"1", "L", "LA", "RGB", "RGBA"},
    "JPEG": {"L", "RGB"},
    "WEBP": {"RGB", "RGBA"},
}
_CLEAN_INFO_KEYS = {
    "dpi",
    "gamma",
    "transparency",
    "interlace",
    "progressive",
    "progression",
    "jfif",
    "jfif_version",
    "jfif_unit",
    "jfif_density",
    # Every static WebP Pillow reads reports these four (after load()).
    "background",
    "loop",
    "timestamp",
    "duration",
}
_SIXTEEN_BIT_GREY = {"I;16", "I;16B", "I;16L", "I"}
_TO_RGB = {"CMYK", "YCbCr", "LAB", "HSV"}
# Attempts for step 7: JPEG/WebP quality, PNG scale of the dimensions.
_QUALITIES = (85, 70, 55)
_PNG_SCALES = (1.0, 0.75, 0.5)


@dataclass(frozen=True)
class NormalisedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    sha256: str

    @property
    def size_bytes(self) -> int:
        return len(self.data)


def _is_clean(img: PILImage.Image) -> bool:
    fmt = img.format
    if fmt not in ("PNG", "JPEG", "WEBP"):  # MPO is never clean
        return False
    if getattr(img, "n_frames", 1) > 1:
        return False
    if max(img.size) > MAX_DIMENSION:
        return False
    if img.mode not in _ALLOWED_MODES[fmt]:
        return False
    if len(img.getexif()) > 0:
        return False
    return set(img.info) <= _CLEAN_INFO_KEYS


def _to_output_mode(img: PILImage.Image, out_fmt: str) -> PILImage.Image:
    mode = img.mode
    if mode in _SIXTEEN_BIT_GREY:
        # A plain convert("L") would clamp everything above 255.
        img = img.point(lambda i: i * (1 / 256)).convert("L")
    elif mode == "P":
        img = img.convert("RGBA" if img.has_transparency_data else "RGB")
    elif mode in _TO_RGB:
        img = img.convert("RGB")
    elif out_fmt == "PNG" and mode in ("1", "L", "RGB") and "transparency" in img.info:
        # The tRNS colour lives in info, which is cleared before saving.
        img = img.convert("RGBA")
    if out_fmt == "WEBP":
        if img.mode in ("L", "1"):
            img = img.convert("RGB")
        elif img.mode == "LA":
            img = img.convert("RGBA")
    if img.mode not in _ALLOWED_MODES[out_fmt]:
        raise invalid_image(f"Unsupported colour mode {img.mode}")
    return img


def _encode(img: PILImage.Image, out_fmt: str, attempt: int) -> bytes:
    if out_fmt == "PNG":
        scale = _PNG_SCALES[attempt]
        if scale != 1.0:
            size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
            img = img.resize(size, PILImage.Resampling.LANCZOS)
            img.info.clear()
        params: dict[str, Any] = {"optimize": True}
    else:
        params = {"quality": _QUALITIES[attempt]}
    out = BytesIO()
    img.save(out, format=out_fmt, **params)
    return out.getvalue()


def normalise(data: bytes, *, max_bytes: int = MAX_UPLOAD_BYTES) -> NormalisedImage:
    """Decode, check and (if needed) re-encode an upload. Pure and CPU-bound: callers
    run it in the threadpool under `decode_slots`. Raises the spec C errors only."""
    # 1. Size of the input.
    if len(data) > max_bytes:
        raise image_too_large()
    # 2. Recognise the format against the allow-list, before any decoding.
    try:
        img = PILImage.open(BytesIO(data), formats=_ALLOWED_FORMATS)
    except UnidentifiedImageError as exc:
        raise unsupported_image() from exc
    except PILImage.DecompressionBombError as exc:
        raise image_too_large() from exc
    except Exception as exc:  # anything else while reading the header
        raise invalid_image() from exc
    try:
        # 3. Pixel count from the header, then animation.
        if img.width * img.height > MAX_PIXELS:
            raise image_too_large()
        if img.format in ("PNG", "WEBP") and getattr(img, "n_frames", 1) > 1:
            raise unsupported_image("Animated images are not supported")
        # 4. Decode fully, so truncated files are rejected even when stored untouched.
        try:
            img.load()
        except PILImage.DecompressionBombError as exc:
            raise image_too_large() from exc
        except BuzzerError:
            raise
        except Exception as exc:
            raise invalid_image() from exc

        # 5. Store the received bytes unchanged when they are already clean.
        if _is_clean(img):
            return _result(data, img.format, img.width, img.height)

        out_fmt = _OUTPUT_FORMAT[img.format]
        try:
            work = ImageOps.exif_transpose(img)
            work = _to_output_mode(work, out_fmt)
            work.thumbnail((MAX_DIMENSION, MAX_DIMENSION), PILImage.Resampling.LANCZOS)
            # Pillow re-uses info["icc_profile"] (PNG) and info["comment"] (JPEG) on save.
            work.info.clear()
            # 7. Bound the stored size.
            for attempt in range(len(_QUALITIES)):
                encoded = _encode(work, out_fmt, attempt)
                if len(encoded) <= max_bytes:
                    break
            else:
                raise image_too_large(
                    "The image could not be reduced below 2 MiB; use a smaller image"
                )
        except BuzzerError:
            raise
        except Exception as exc:
            raise invalid_image() from exc
        with PILImage.open(BytesIO(encoded)) as stored:
            return _result(encoded, out_fmt, stored.width, stored.height)
    finally:
        img.close()


def _result(data: bytes, fmt: str, width: int, height: int) -> NormalisedImage:
    return NormalisedImage(
        data=data,
        content_type=_CONTENT_TYPES[fmt],
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )


async def normalise_async(data: bytes) -> NormalisedImage:
    async with decode_slots:
        return await run_in_threadpool(normalise, data)


async def read_upload(file: UploadFile, limit: int) -> bytes | None:
    """At most `limit` bytes of an upload; None when the file is larger."""
    data = await file.read(limit + 1)
    return None if len(data) > limit else data


# ---------------------------------------------------------------------------
# Pure rules: aspect ratio, quota, ETag
# ---------------------------------------------------------------------------


def aspect_changed(w_old: int, h_old: int, w_new: int, h_new: int) -> bool:
    """More than 1 % change of the width/height ratio (exactly 1 % is allowed)."""
    return abs(w_new * h_old - w_old * h_new) * 100 > w_old * h_new


def check_quota(
    count: int, total_bytes: int, new_bytes: int, *, replaced_bytes: int | None = None
) -> None:
    """`count`/`total_bytes` describe the game's images now. For a replace, pass the
    size of the image being replaced: the count is unchanged and its bytes are freed."""
    if replaced_bytes is None:
        if count + 1 > MAX_IMAGES_PER_GAME:
            raise image_limit(f"A game can hold at most {MAX_IMAGES_PER_GAME} images")
        after = total_bytes + new_bytes
    else:
        after = total_bytes - replaced_bytes + new_bytes
    if after > MAX_BYTES_PER_GAME:
        raise image_limit("A game can hold at most 25 MiB of images")


def etag_matches(if_none_match: str | None, sha256: str) -> bool:
    if not if_none_match:
        return False
    for tag in if_none_match.split(","):
        tag = tag.strip()
        if tag == "*":
            return True
        if tag.startswith("W/"):
            tag = tag[2:]
        if tag.strip('"') == sha256:
            return True
    return False


# ---------------------------------------------------------------------------
# The config convention (spec E)
# ---------------------------------------------------------------------------


def validate_image_fields(qtype: str, config: Any) -> None:
    """Structure only (no database). 422 INVALID_IMAGE_REFERENCE."""
    if not isinstance(config, dict):
        return
    image_id = config.get("image_id")
    if image_id is not None and not is_canonical_id(image_id):
        raise invalid_reference("image_id must be null or an image id")
    option_ids = config.get("option_image_ids")
    if option_ids is None:
        return
    if qtype not in OPTION_IMAGE_TYPES:
        raise invalid_reference(
            "option_image_ids is only allowed on multiple_choice and multi_select questions"
        )
    options = config.get("options")
    if not isinstance(option_ids, list) or not isinstance(options, list):
        raise invalid_reference("option_image_ids must be a list parallel to options")
    if len(option_ids) != len(options):
        raise invalid_reference(
            "option_image_ids must have exactly one entry per option"
        )
    for entry in option_ids:
        if entry is not None and not is_canonical_id(entry):
            raise invalid_reference(
                "option_image_ids entries must be null or image ids"
            )


def image_ids(config: Any) -> list[str]:
    """Every canonical id the config references, in order of first use. Tolerant:
    malformed values are ignored, never raised on."""
    if not isinstance(config, dict):
        return []
    found: list[str] = []
    candidates = [config.get("image_id")]
    option_ids = config.get("option_image_ids")
    if isinstance(option_ids, list):
        candidates.extend(option_ids)
    for value in candidates:
        if is_canonical_id(value) and value not in found:
            found.append(value)
    return found


class UnknownImageKey(Exception):
    def __init__(self, value: str):
        self.value = value
        super().__init__(value)


def remap_image_ids(
    config: Any,
    mapping: dict[str, str],
    *,
    on_missing: Literal["null", "error"],
) -> Any:
    """A deep copy with only `image_id` and `option_image_ids` entries rewritten through
    `mapping`. Non-string values pass through unchanged. An unmapped string becomes None
    (`on_missing="null"`) or raises UnknownImageKey (`"error"`)."""
    result = copy.deepcopy(config)
    if not isinstance(result, dict):
        return result

    def remap(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if value in mapping:
            return mapping[value]
        if on_missing == "error":
            raise UnknownImageKey(value)
        return None

    if "image_id" in result:
        result["image_id"] = remap(result["image_id"])
    option_ids = result.get("option_image_ids")
    if isinstance(option_ids, list):
        result["option_image_ids"] = [remap(v) for v in option_ids]
    return result


def export_config(
    qtype: str, config: Any, mapping: dict[str, str], *, game_id: int, question_id: int
) -> Any:
    """remap_image_ids in "null" mode plus the export cleanup of E: a non-string
    image_id becomes null, a malformed option_image_ids is dropped. Each change is
    logged, so an exported file with only valid references always re-imports."""
    if not isinstance(config, dict):
        return copy.deepcopy(config)
    result = remap_image_ids(config, mapping, on_missing="null")
    log = {"game_id": game_id, "question_id": question_id}

    old_id = config.get("image_id")
    if isinstance(old_id, str) and old_id not in mapping:
        logger.warning("export_image_reference_nulled", value=old_id, **log)
    elif old_id is not None and not isinstance(old_id, str):
        result["image_id"] = None
        logger.warning("export_image_id_dropped", value=repr(old_id), **log)

    if "option_image_ids" in result:
        option_ids = result["option_image_ids"]
        options = result.get("options")
        if option_ids is not None and (
            qtype not in OPTION_IMAGE_TYPES
            or not isinstance(option_ids, list)
            or not isinstance(options, list)
            or len(option_ids) != len(options)
        ):
            del result["option_image_ids"]
            logger.warning("export_option_image_ids_dropped", **log)
        elif isinstance(option_ids, list):
            originals = config["option_image_ids"]
            for i, (old, new) in enumerate(zip(originals, option_ids)):
                if isinstance(old, str) and old not in mapping:
                    logger.warning("export_image_reference_nulled", value=old, **log)
                elif old is not None and not isinstance(old, str):
                    option_ids[i] = None
                    logger.warning("export_image_id_dropped", value=repr(old), **log)
    return result


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


async def list_images(db: AsyncSession, game_id: int) -> list[Image]:
    """Metadata only: `data` is deferred and never loaded here."""
    result = await db.execute(
        select(Image)
        .where(Image.game_id == game_id)
        .order_by(Image.created_at, Image.id)
    )
    return list(result.scalars().all())


async def get_image_in_game_or_404(
    db: AsyncSession, game_id: int, image_id: str
) -> Image:
    image = None
    if is_canonical_id(image_id):
        result = await db.execute(
            select(Image)
            .where(Image.id == image_id, Image.game_id == game_id)
            .execution_options(populate_existing=True)
        )
        image = result.scalar_one_or_none()
    if image is None:
        raise NotFoundError(f"Image {image_id} not found in game {game_id}")
    return image


async def _question_refs(
    db: AsyncSession, game_id: int
) -> list[tuple[int, int, list[str]]]:
    """(question id, order_index, referenced ids) for every question of the game."""
    result = await db.execute(
        select(Question.id, Question.order_index, Question.config)
        .where(Question.game_id == game_id)
        .order_by(Question.order_index, Question.id)
    )
    return [(qid, order, image_ids(config)) for qid, order, config in result.all()]


async def used_by(db: AsyncSession, game_id: int) -> dict[str, list[int]]:
    """image id -> ids of the game's questions that reference it."""
    usage: dict[str, list[int]] = {}
    for qid, _, ids in await _question_refs(db, game_id):
        for image_id in ids:
            usage.setdefault(image_id, []).append(qid)
    return usage


async def question_numbers_using(
    db: AsyncSession, game_id: int, image_id: str
) -> list[int]:
    """Question numbers (order_index + 1, as the editor shows them) using the image."""
    return [
        order + 1
        for _, order, ids in await _question_refs(db, game_id)
        if image_id in ids
    ]


async def assert_references_valid(db: AsyncSession, game_id: int, config: Any) -> None:
    """Every referenced id exists and belongs to this game (422)."""
    ids = image_ids(config)
    if not ids:
        return
    result = await db.execute(
        select(Image.id).where(Image.game_id == game_id, Image.id.in_(ids))
    )
    present = set(result.scalars().all())
    for image_id in ids:
        if image_id not in present:
            raise invalid_reference(f"Image {image_id} is not part of this game")


async def check_question_images(
    db: AsyncSession, game_id: int, qtype: str, config: Any
) -> None:
    validate_image_fields(qtype, config)
    await assert_references_valid(db, game_id, config)


async def _usage_totals(db: AsyncSession, game_id: int) -> tuple[int, int]:
    count, total = (
        await db.execute(
            select(
                func.count(Image.id), func.coalesce(func.sum(Image.size_bytes), 0)
            ).where(Image.game_id == game_id)
        )
    ).one()
    return int(count), int(total)


async def _find_by_sha(db: AsyncSession, game_id: int, sha256: str) -> Image | None:
    result = await db.execute(
        select(Image)
        .where(Image.game_id == game_id, Image.sha256 == sha256)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def store_upload(
    db: AsyncSession, game_id: int, processed: NormalisedImage
) -> tuple[Image, bool]:
    """Inside the game lock, after assert_questions_editable. Returns (image, created):
    identical bytes return the existing image without a quota check."""
    existing = await _find_by_sha(db, game_id, processed.sha256)
    if existing is not None:
        return existing, False
    count, total = await _usage_totals(db, game_id)
    check_quota(count, total, processed.size_bytes)
    image = Image(
        id=new_image_id(),
        game_id=game_id,
        content_type=processed.content_type,
        size_bytes=processed.size_bytes,
        width=processed.width,
        height=processed.height,
        sha256=processed.sha256,
        data=processed.data,
    )
    try:
        async with db.begin_nested():
            db.add(image)
    except IntegrityError:
        # Unique (game_id, sha256); defensive only, the game lock serialises writers.
        existing = await _find_by_sha(db, game_id, processed.sha256)
        if existing is None:
            raise
        return existing, False
    await db.refresh(image)
    logger.info(
        "image_uploaded", game_id=game_id, image_id=image.id, size=image.size_bytes
    )
    return image, True


async def replace_image(
    db: AsyncSession, game_id: int, image: Image, processed: NormalisedImage
) -> Image:
    """Inside the game lock, after assert_questions_editable (spec D, PUT)."""
    if processed.sha256 == image.sha256:
        return image
    other = await _find_by_sha(db, game_id, processed.sha256)
    if other is not None:
        raise BuzzerError(
            "IMAGE_DUPLICATE",
            "This game already has an image with exactly these bytes",
            409,
        )
    if await question_numbers_using(db, game_id, image.id) and aspect_changed(
        image.width, image.height, processed.width, processed.height
    ):
        raise BuzzerError(
            "IMAGE_ASPECT_CHANGED",
            "This image is used by questions and the new one has a different shape. "
            "Upload a new image and update the questions instead.",
            409,
        )
    count, total = await _usage_totals(db, game_id)
    check_quota(count, total, processed.size_bytes, replaced_bytes=image.size_bytes)
    image.content_type = processed.content_type
    image.size_bytes = processed.size_bytes
    image.width = processed.width
    image.height = processed.height
    image.sha256 = processed.sha256
    image.data = processed.data
    image.updated_at = func.now()
    await db.flush()
    await db.refresh(image)
    logger.info("image_replaced", game_id=game_id, image_id=image.id)
    return image


async def delete_image(db: AsyncSession, game_id: int, image: Image) -> None:
    """Inside the game lock, after assert_questions_editable (spec D, DELETE)."""
    numbers = await question_numbers_using(db, game_id, image.id)
    if numbers:
        listed = ", ".join(f"Q{n}" for n in numbers)
        raise BuzzerError(
            "IMAGE_IN_USE",
            f"This image is used by {listed}; remove it there first",
            409,
        )
    await db.execute(delete(Image).where(Image.id == image.id))
    await db.flush()
    logger.info("image_deleted", game_id=game_id, image_id=image.id)


async def read_image_meta(db: AsyncSession, image_id: str) -> tuple[str, str] | None:
    """(content_type, sha256) without the bytes, for the public read endpoint."""
    if not is_canonical_id(image_id):
        return None
    row = (
        await db.execute(
            select(Image.content_type, Image.sha256).where(Image.id == image_id)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def read_image_data(db: AsyncSession, image_id: str) -> bytes | None:
    return (
        await db.execute(select(Image.data).where(Image.id == image_id))
    ).scalar_one_or_none()


async def images_with_data(db: AsyncSession, game_id: int) -> list[tuple[Image, bytes]]:
    """Every image row of the game with its bytes, selected explicitly (duplicate)."""
    result = await db.execute(
        select(Image, Image.data)
        .where(Image.game_id == game_id)
        .order_by(Image.created_at, Image.id)
    )
    return [(row[0], row[1]) for row in result.all()]
