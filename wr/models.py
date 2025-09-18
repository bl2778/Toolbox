"""Typed models used by the Wording Revision (WR) module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SlideElement:
    id: str
    type: str
    text: str


@dataclass
class SlimSlide:
    slide_number: int
    elements: List[SlideElement]


@dataclass
class Chunk:
    chunk_id: str
    page_start: int
    page_end: int
    page_numbers: List[int]
    mode: str
    word_count: int
    json_payload: List[Dict[str, Any]]


@dataclass
class ChunkResultRow:
    page: int
    original: str
    revised: str


@dataclass
class ChunkState:
    chunk_id: str
    status: str
    page_start: int
    page_end: int
    page_numbers: List[int]
    word_count: int
    mode: str
    start_time: float
    completion_time: Optional[float] = None
    streaming_output: str = ""
    ai_progress: str = ""
    result_text: str = ""
    rows: List[ChunkResultRow] = field(default_factory=list)
    error: Optional[str] = None
    attempts: int = 0


@dataclass
class JobResult:
    rows: List[ChunkResultRow]
    no_edits: bool
