"""Configuration constants for the Wording Revision (WR) module."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ChunkConfig:
    word_min: int
    word_max: int
    page_max: int
    overlap_pages: int


CFG_FAST = ChunkConfig(word_min=4000, word_max=6500, page_max=15, overlap_pages=1)
CFG_PRECISE = ChunkConfig(word_min=2500, word_max=4000, page_max=8, overlap_pages=1)

DEFAULT_MODE = "fast"
DEFAULT_MODEL = "gpt-5-pro"

MAX_WORKERS = int(os.getenv("WR_MAX_WORKERS", "8"))

REQUEST_TIMEOUT = 300
STREAM_IDLE_TIMEOUT = 60
STALL_THRESHOLD = 300

EXPORT_HEADERS = ["Page", "Original", "Revised"]
