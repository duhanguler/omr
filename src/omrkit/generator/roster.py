"""Class roster CSV parser for personalized mail-merge OMR exam packets."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from pydantic import BaseModel, Field

_TR_ASCII_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

_ID_ALIASES = frozenset(
    {
        "student_id",
        "studentid",
        "id",
        "ogrenci_no",
        "ogrencino",
        "ogr_no",
        "numara",
        "no",
        "tc",
        "tc_no",
        "tckn",
        "tc_kimlik_no",
        "sis_id",
        "sis_user_id",
        "id_number",
        "matrikelnummer",
        "xuehao",
        "matricula",
    }
)
_NAME_ALIASES = frozenset(
    {
        "name",
        "full_name",
        "fullname",
        "student_name",
        "studentname",
        "student",
        "ad_soyad",
        "adsoyad",
        "adi_soyadi",
        "isim",
        "nombre",
        "imya",
        "fio",
        "xingming",
    }
)
_FIRST_NAME_ALIASES = frozenset({"first_name", "firstname", "first", "ad", "adi", "vorname"})
_LAST_NAME_ALIASES = frozenset(
    {"last_name", "lastname", "last", "surname", "soyad", "soyadi", "nachname", "apellido"}
)
_CLASS_ALIASES = frozenset(
    {
        "classroom",
        "class",
        "section",
        "sinif",
        "sube",
        "group",
        "klasse",
        "grupo",
        "klass",
        "banji",
    }
)
_BOOKLET_ALIASES = frozenset(
    {
        "booklet",
        "kitapcik",
        "kitapcik_turu",
        "version",
        "form",
        "variant",
        "cuadernillo",
        "heft",
    }
)
_EMAIL_ALIASES = frozenset({"email", "e_mail", "email_address", "eposta", "e_posta", "mail"})


class StudentRosterEntry(BaseModel):
    """Single student record used to personalize an optical answer sheet."""

    student_id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    classroom: str = Field(default="", max_length=32)
    booklet: str = Field(default="", max_length=8)
    email: str = Field(default="", max_length=120)


def _normalize_header(raw: str) -> str:
    cleaned = raw.strip().lstrip("\ufeff").translate(_TR_ASCII_MAP).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return cleaned


def _detect_delimiter(text: str) -> str:
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    if first_line.count(";") > first_line.count(","):
        return ";"
    if first_line.count("\t") > first_line.count(","):
        return "\t"
    return ","


def parse_roster_csv(content: str, max_students: int = 500) -> list[StudentRosterEntry]:
    """Parse a class roster CSV string with multilingual column header auto-mapping.

    Supports UTF-8/BOM, comma/semicolon/tab delimiters, and English/Turkish/German/Spanish/
    Russian/Chinese transliterated header variants.
    """
    text = content.lstrip("\ufeff").strip()
    if not text:
        raise ValueError("Roster CSV is empty.")

    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("Roster CSV is missing a header row.")

    col_map: dict[str, str] = {}
    for raw_col in reader.fieldnames:
        if raw_col is None:
            continue
        norm = _normalize_header(raw_col)
        if norm in _ID_ALIASES and "student_id" not in col_map:
            col_map["student_id"] = raw_col
        elif norm in _NAME_ALIASES and "name" not in col_map:
            col_map["name"] = raw_col
        elif norm in _FIRST_NAME_ALIASES and "first_name" not in col_map:
            col_map["first_name"] = raw_col
        elif norm in _LAST_NAME_ALIASES and "last_name" not in col_map:
            col_map["last_name"] = raw_col
        elif norm in _CLASS_ALIASES and "classroom" not in col_map:
            col_map["classroom"] = raw_col
        elif norm in _BOOKLET_ALIASES and "booklet" not in col_map:
            col_map["booklet"] = raw_col
        elif norm in _EMAIL_ALIASES and "email" not in col_map:
            col_map["email"] = raw_col

    has_name = "name" in col_map or ("first_name" in col_map)
    if "student_id" not in col_map and not has_name:
        raise ValueError(
            "Roster CSV must contain at least a 'student_id' (or 'ogrenci_no'/'id') "
            "or 'name' (or 'ad_soyad') column."
        )

    entries: list[StudentRosterEntry] = []
    for row_idx, row in enumerate(reader, start=1):
        sid = (row.get(col_map["student_id"]) or "").strip() if "student_id" in col_map else ""
        if "name" in col_map:
            name = (row.get(col_map["name"]) or "").strip()
        else:
            first = (
                (row.get(col_map["first_name"]) or "").strip() if "first_name" in col_map else ""
            )
            last = (row.get(col_map["last_name"]) or "").strip() if "last_name" in col_map else ""
            name = f"{first} {last}".strip()

        classroom = (row.get(col_map["classroom"]) or "").strip() if "classroom" in col_map else ""
        booklet = (
            (row.get(col_map["booklet"]) or "").strip().upper() if "booklet" in col_map else ""
        )
        email = (row.get(col_map["email"]) or "").strip() if "email" in col_map else ""

        if not sid and not name:
            continue
        if not sid:
            sid = f"{row_idx:04d}"
        if not name:
            name = f"Student {sid}"

        entries.append(
            StudentRosterEntry(
                student_id=sid[:32],
                name=name[:80],
                classroom=classroom[:32],
                booklet=booklet[:8],
                email=email[:120],
            )
        )
        if len(entries) > max_students:
            raise ValueError(
                f"Roster exceeds maximum allowed limit of {max_students} students per packet."
            )

    if not entries:
        raise ValueError("Roster CSV contains no valid student rows.")
    return entries


def parse_roster_file(path: str | Path, max_students: int = 500) -> list[StudentRosterEntry]:
    """Read and parse a roster CSV file from disk."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    return parse_roster_csv(raw, max_students=max_students)
