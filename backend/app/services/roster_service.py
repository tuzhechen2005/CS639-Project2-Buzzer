from __future__ import annotations

import csv
import io
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import BuzzerError
from ..models.course import CourseRoster
from ..schemas.admin import RosterUploadResult

logger = structlog.get_logger()

# Canvas gradebook column names (matched case-insensitively)
STUDENT_COL = "student"  # "Last, First [Middle]"
SIS_LOGIN_COL = "sis login id"  # "NETID@WISC.EDU"

MAX_ROWS = 1000

RosterMode = Literal["replace", "add_only"]


def _reject_truncated_replace(mode: RosterMode, truncated: bool) -> None:
    """
    `replace` deactivates every active entry that is not in the upload. If the upload was
    cut at MAX_ROWS, the students in the unprocessed rows would be deactivated too, so
    refuse it (also for dry runs, so the preview shows the problem). `add_only` never
    deactivates anyone and keeps the old behaviour.
    """
    if truncated and mode == "replace":
        raise BuzzerError(
            "ROSTER_TOO_LARGE",
            f"This upload has more than {MAX_ROWS} students. Replace mode would deactivate "
            f"the ones past row {MAX_ROWS}; split the upload or use add-only mode.",
            422,
        )


def _is_metadata_row(row: dict[str, str]) -> bool:
    """Skip the Canvas 'Points Possible' row that always appears as row 2."""
    first_val = next(iter(row.values()), "").strip().lower()
    return first_val.startswith("points possible")


def _parse_display_name(raw: str) -> str:
    """
    Extract given name(s) from Canvas 'Last, First [Middle]' format, title-cased.
    Examples:
      "Abboud, Masa"           → "Masa"
      "ABDUL KADIR, KHAYYUM"   → "Khayyum"
      "Bachu, Revanth Krishna" → "Revanth Krishna"
    """
    raw = raw.strip()
    if "," in raw:
        _, _, given = raw.partition(",")
        display = given.strip()
    else:
        display = raw
    return display.title() if display else raw.title()


def _parse_sis_login(raw: str) -> tuple[str, str]:
    """Parse 'NETID@WISC.EDU' into (netid, email), both lowercased."""
    raw = raw.strip().lower()
    netid = raw.partition("@")[0].strip() if "@" in raw else raw
    return netid, raw


async def process_roster_csv(
    db: AsyncSession,
    course_id: int,
    file_bytes: bytes,
    *,
    mode: RosterMode = "replace",
    dry_run: bool = False,
) -> RosterUploadResult:
    """
    Parse a Canvas gradebook CSV export, upsert rows into course_rosters,
    and deactivate entries whose netid is absent from this upload.

    Expected columns (case-insensitive):
      'Student'      — "Last, First [Middle]"
      'SIS Login ID' — "NETID@WISC.EDU"

    Row 2 ('Points Possible') is automatically skipped.
    All other columns are ignored. See `_apply_rows` for `mode` and `dry_run`.
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        return RosterUploadResult(
            imported=0,
            updated=0,
            deactivated=0,
            errors=["CSV file is empty or has no header row"],
        )

    # Case-insensitive column lookup: normalised → original header
    col_map: dict[str, str] = {f.strip().lower(): f for f in reader.fieldnames}

    missing = {STUDENT_COL, SIS_LOGIN_COL} - col_map.keys()
    if missing:
        return RosterUploadResult(
            imported=0,
            updated=0,
            deactivated=0,
            errors=[
                f"Missing required columns: {', '.join(sorted(missing))}. "
                "Expected 'Student' and 'SIS Login ID' (Canvas gradebook export)."
            ],
        )

    student_header = col_map[STUDENT_COL]
    sis_header = col_map[SIS_LOGIN_COL]

    errors: list[str] = []
    rows: list[dict[str, str]] = []
    seen_netids: set[str] = set()
    truncated = False
    csv_row = 1  # row 1 = header; incremented before each data row

    for raw_row in reader:
        csv_row += 1

        if _is_metadata_row(raw_row):
            continue

        student_raw = raw_row.get(student_header, "").strip()
        sis_raw = raw_row.get(sis_header, "").strip()

        if not student_raw and not sis_raw:
            continue  # blank trailing row

        row_errors = []
        if not student_raw:
            row_errors.append("Student column is empty")
        if not sis_raw:
            row_errors.append("SIS Login ID column is empty")
        if row_errors:
            errors.append(
                f"Row {csv_row} ('{student_raw or '?'}'): {'; '.join(row_errors)}"
            )
            continue

        display_name = _parse_display_name(student_raw)
        netid, email = _parse_sis_login(sis_raw)

        if not netid:
            errors.append(f"Row {csv_row}: could not extract netid from '{sis_raw}'")
            continue

        if len(seen_netids) >= MAX_ROWS:
            errors.append(
                f"Reached {MAX_ROWS}-row limit; remaining rows were not processed."
            )
            truncated = True
            break

        seen_netids.add(netid)
        rows.append({"netid": netid, "full_name": display_name, "email": email})

    _reject_truncated_replace(mode, truncated)
    return await _apply_rows(
        db, course_id, rows, errors, mode=mode, dry_run=dry_run, event="roster_uploaded"
    )


async def process_roster_rows(
    db: AsyncSession,
    course_id: int,
    rows: list[dict[str, str]],
    *,
    mode: RosterMode = "replace",
    dry_run: bool = False,
) -> RosterUploadResult:
    """
    Process pre-mapped roster rows (already resolved to netid/full_name/email
    by the frontend column-mapping wizard). See `_apply_rows` for `mode` and `dry_run`.
    """
    errors: list[str] = []
    clean: list[dict[str, str]] = []
    seen_netids: set[str] = set()
    truncated = False

    for i, row in enumerate(rows, start=1):
        netid = row.get("netid", "").strip().lower()
        full_name = row.get("full_name", "").strip()
        email = row.get("email", "").strip().lower()

        if not netid or not full_name or not email:
            errors.append(f"Row {i}: missing required field(s) — skipped")
            continue

        if len(seen_netids) >= MAX_ROWS:
            errors.append(
                f"Reached {MAX_ROWS}-row limit; remaining rows were not processed."
            )
            truncated = True
            break

        seen_netids.add(netid)
        clean.append({"netid": netid, "full_name": full_name, "email": email})

    _reject_truncated_replace(mode, truncated)
    return await _apply_rows(
        db,
        course_id,
        clean,
        errors,
        mode=mode,
        dry_run=dry_run,
        event="roster_imported_rows",
    )


async def _apply_rows(
    db: AsyncSession,
    course_id: int,
    rows: list[dict[str, str]],
    errors: list[str],
    *,
    mode: RosterMode,
    dry_run: bool,
    event: str,
) -> RosterUploadResult:
    """
    Upsert `rows` into the course roster.

    mode="replace": also deactivate every active entry whose netid is not in `rows`
                    (the original behaviour; kept by the admin aliases).
    mode="add_only": deactivate nobody (default on the host-facing endpoints).
    dry_run=True:    compute the same counts but write nothing.

    An upload with no valid rows never deactivates anyone, in either mode.
    """
    existing = {
        e.netid: e
        for e in (
            await db.execute(
                select(CourseRoster).where(CourseRoster.course_id == course_id)
            )
        )
        .scalars()
        .all()
    }

    imported = updated = 0
    planned_new: dict[str, CourseRoster] = {}
    for row in rows:
        entry = existing.get(row["netid"]) or planned_new.get(row["netid"])
        if entry is not None:
            updated += 1
            if not dry_run:
                entry.full_name = row["full_name"]
                entry.email = row["email"]
                entry.is_active = True
            continue
        imported += 1
        new_entry = CourseRoster(
            course_id=course_id,
            netid=row["netid"],
            full_name=row["full_name"],
            email=row["email"],
            is_active=True,
        )
        planned_new[row["netid"]] = new_entry
        if not dry_run:
            db.add(new_entry)

    deactivated = 0
    if mode == "replace" and rows:
        seen = {r["netid"] for r in rows}
        for netid, entry in existing.items():
            if netid not in seen and entry.is_active:
                deactivated += 1
                if not dry_run:
                    entry.is_active = False

    if not dry_run:
        await db.flush()

    logger.info(
        event,
        course_id=course_id,
        mode=mode,
        dry_run=dry_run,
        imported=imported,
        updated=updated,
        deactivated=deactivated,
        error_count=len(errors),
    )

    return RosterUploadResult(
        imported=imported,
        updated=updated,
        deactivated=deactivated,
        errors=errors,
    )
