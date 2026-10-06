"""
Unit tests for the download-filename helper.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_export_filenames.py -v
"""
from __future__ import annotations

import pytest

from app.services.export_service import ascii_filename_part


@pytest.mark.parametrize(
    "title, expected",
    [
        ("SQL Fundamentals", "SQL Fundamentals"),
        ("quiz_1-final", "quiz_1-final"),
        ("Q&A: week 3", "Q_A_ week 3"),
        ("数据库基础", "fallback"),
        ("数据库 SQL", "___ SQL"),
        ("Café", "Caf_"),
        ("", "fallback"),
        ("???", "fallback"),
    ],
)
def test_ascii_filename_part(title: str, expected: str):
    assert ascii_filename_part(title, "fallback") == expected


def test_result_is_latin1_encodable():
    for title in ["数据库基础", "日本語 quiz", "Ünïcode", "emoji 🎉"]:
        ascii_filename_part(title, "x").encode("latin-1")
