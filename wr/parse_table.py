"""Markdown table parsing for WR chunk results."""

from __future__ import annotations

import re
from typing import List

from .models import ChunkResultRow

HEADER_RE = re.compile(r"\bpage\b", re.IGNORECASE)
TABLE_LINE_RE = re.compile(r"^\|.*\|")
SEPARATOR_RE = re.compile(r"^\s*\|?\s*-{2,}")
THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _clean_text(text: str) -> str:
    cleaned = THINK_TAG_RE.sub("", text)
    cleaned = cleaned.replace("Answer:", "").replace("answer:", "")
    return cleaned.strip()


def _normalize_original(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _smart_split(line: str) -> List[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    parts = [part.strip() for part in stripped.split("|")]
    if len(parts) <= 3:
        return parts
    first = parts[0]
    last = parts[-1]
    middle = "|".join(parts[1:-1]).strip()
    return [first, middle, last]


def parse_wr_table(text: str) -> List[ChunkResultRow]:
    cleaned_text = _clean_text(text)
    if not cleaned_text:
        return []

    lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
    if not lines:
        return []

    header_index = -1
    for idx, line in enumerate(lines):
        if HEADER_RE.search(line) and "original" in line.lower() and "revised" in line.lower():
            header_index = idx
            break
    if header_index == -1:
        return []

    rows: List[ChunkResultRow] = []
    for line in lines[header_index + 1 :]:
        if SEPARATOR_RE.match(line):
            continue
        if not TABLE_LINE_RE.match(line):
            continue
        columns = _smart_split(line)
        if len(columns) < 3:
            continue
        try:
            page = int(columns[0].strip())
        except ValueError:
            continue
        original = columns[1].strip()
        revised = columns[2].strip()
        if not original or not revised:
            continue
        rows.append(ChunkResultRow(page=page, original=original, revised=revised))
    return rows


def merge_rows(rows: List[ChunkResultRow]) -> List[ChunkResultRow]:
    best = {}
    for row in rows:
        key = (row.page, _normalize_original(row.original))
        existing = best.get(key)
        if not existing or len(row.revised) > len(existing.revised):
            best[key] = row
    return sorted(best.values(), key=lambda row: row.page)
