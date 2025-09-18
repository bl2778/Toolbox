"""Page-level chunking for WR module."""

from __future__ import annotations

import itertools
import re
from typing import List, Dict

from .config import CFG_FAST, CFG_PRECISE, ChunkConfig

WORD_RE = re.compile(r"[A-Za-z']+")


def _count_slide_words(slide: Dict) -> int:
    count = 0
    for element in slide.get("elements", []):
        count += len(WORD_RE.findall(element.get("text", "")))
    return count


def _make_chunk(chunk_slides: List[Dict], mode: str, chunk_index: int) -> Dict:
    page_numbers = [slide["slide_number"] for slide in chunk_slides]
    return {
        "chunk_id": f"wr_{chunk_index:04d}",
        "page_start": page_numbers[0],
        "page_end": page_numbers[-1],
        "page_numbers": page_numbers,
        "mode": mode,
        "word_count": sum(_count_slide_words(slide) for slide in chunk_slides),
        "json_payload": chunk_slides,
    }


def _get_config(mode: str) -> ChunkConfig:
    return CFG_FAST if mode == "fast" else CFG_PRECISE


def chunk_slides(slides: List[Dict], mode: str) -> List[Dict]:
    if not slides:
        return []

    config = _get_config(mode)
    slides_sorted = sorted(slides, key=lambda slide: slide["slide_number"])
    chunks: List[Dict] = []
    buffer: List[Dict] = []
    buffer_word_count = 0
    chunk_index = 1

    for slide in slides_sorted:
        slide_words = _count_slide_words(slide)
        slide_number = slide["slide_number"]

        if not buffer:
            buffer.append(slide)
            buffer_word_count = slide_words
            continue

        projected_word_count = buffer_word_count + slide_words
        projected_page_count = slide_number - buffer[0]["slide_number"] + 1

        if (
            projected_word_count > config.word_max
            or projected_page_count > config.page_max
        ):
            chunks.append(_make_chunk(buffer, mode, chunk_index))
            chunk_index += 1

            overlap = buffer[-config.overlap_pages :] if config.overlap_pages else []
            buffer = list(overlap)
            buffer_word_count = sum(_count_slide_words(s) for s in buffer)

        buffer.append(slide)
        buffer_word_count += slide_words

    if buffer:
        chunks.append(_make_chunk(buffer, mode, chunk_index))

    return chunks
