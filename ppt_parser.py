"""
PowerPoint Text Extractor for ZD Tool
-------------------------------------
Extracts structured text from PowerPoint files for Zero-Defect checking.
Supports conversion to JSON format optimized for AI analysis.
"""

import json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Any

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.enum.shapes import PP_PLACEHOLDER
except ImportError:
    raise ImportError("python-pptx is not installed. Run: pip install python-pptx")


class PPTExtractor:
    def __init__(self):
        pass

    def extract_text_recursive(self, shape) -> List[Dict[str, str]]:
        """Recursively extract text from a shape (handling groups, tables, charts)."""
        chunks = []
        sid = f"Shape ID {shape.shape_id}"

        # 1) Plain text frames
        if shape.has_text_frame and shape.text_frame.text.strip():
            text = shape.text_frame.text.strip()
            type_hint = "Body"
            if shape.is_placeholder:
                ph = shape.placeholder_format
                if ph.type in {
                    PP_PLACEHOLDER.TITLE,
                    PP_PLACEHOLDER.CENTER_TITLE,
                    PP_PLACEHOLDER.SUBTITLE,
                    PP_PLACEHOLDER.VERTICAL_TITLE,
                }:
                    type_hint = "Title/Subtitle"
                elif ph.type == PP_PLACEHOLDER.BODY:
                    type_hint = "Body Placeholder"
                elif ph.type == PP_PLACEHOLDER.OBJECT and "Title" in shape.name:
                    type_hint = "Object Title"

            chunks.append({"id": sid, "type": type_hint, "text": text})

        # 2) Table cells
        elif shape.has_table:
            tbl_txt = []
            for r, row in enumerate(shape.table.rows):
                for c, cell in enumerate(row.cells):
                    cell_txt = cell.text_frame.text.strip()
                    if cell_txt:
                        tbl_txt.append(f"Row {r+1}, Col {c+1}: {cell_txt}")
            if tbl_txt:
                chunks.append({"id": sid, "type": "Table", "text": "\\n".join(tbl_txt)})

        # 3) Grouped shapes
        elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for s in shape.shapes:
                chunks.extend(self.extract_text_recursive(s))

        # 4) Chart title (limited)
        elif shape.has_chart:
            ch = shape.chart
            if ch.has_title and ch.chart_title.text_frame.text.strip():
                chunks.append(
                    {
                        "id": sid,
                        "type": "Chart Info",
                        "text": f"Chart Title: {ch.chart_title.text_frame.text.strip()}",
                    }
                )

        return chunks

    def extract_powerpoint_text(self, pptx_path: str) -> Optional[List[Dict[str, Any]]]:
        """Extract text from PowerPoint file and return structured data."""
        if not Path(pptx_path).exists():
            raise FileNotFoundError(f"File not found: {pptx_path}")

        try:
            prs = Presentation(pptx_path)
        except Exception as exc:
            raise ValueError(f"Could not open presentation: {exc}")

        slides_data = []
        for idx, slide in enumerate(prs.slides, start=1):
            slide_info = {"slide_number": idx, "elements": [], "notes": None}

            for shp in slide.shapes:
                slide_info["elements"].extend(self.extract_text_recursive(shp))

            if slide.has_notes_slide:
                notes_tf = slide.notes_slide.notes_text_frame
                if notes_tf and notes_tf.text.strip():
                    slide_info["notes"] = notes_tf.text.strip()

            # Always add slide even if empty (for consistent page numbering)
            slides_data.append(slide_info)

        return slides_data

    def convert_to_zd_format(self, slides_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert extracted data to ZD Tool format."""
        zd_slides = []

        for slide in slides_data:
            slide_number = slide["slide_number"]

            # Separate title/tagline from body content
            titles = []
            body_parts = []

            for element in slide["elements"]:
                if element["type"] == "Title/Subtitle":
                    titles.append(element["text"])
                else:
                    # Filter out purely alphanumeric markers like "A.", "I-1"
                    text = element["text"]
                    if not re.match(r'^[A-Z]\.?$|^[IVX]+-?\d*\.?$', text.strip()):
                        body_parts.append(text)

            # Combine titles as tagline
            tagline = " | ".join(titles) if titles else ""

            # Combine body content
            body_other = "\\n".join(body_parts) if body_parts else ""

            # Notes (marked as "Do not review" per spec)
            speaker_notes = "Do not review" if slide["notes"] else ""

            zd_slide = {
                "page_number": slide_number,
                "tagline": tagline,
                "body_other": body_other,
                "speaker_notes": speaker_notes
            }

            zd_slides.append(zd_slide)

        return zd_slides

    def get_word_count(self, text: str) -> int:
        """Count words in English text."""
        if not text or not text.strip():
            return 0
        return len(text.split())

    def get_slide_stats(self, zd_slides: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about the slides."""
        total_slides = len(zd_slides)
        total_words = 0

        for slide in zd_slides:
            slide_words = (self.get_word_count(slide["tagline"]) +
                          self.get_word_count(slide["body_other"]))
            total_words += slide_words

        avg_words_per_slide = total_words / total_slides if total_slides > 0 else 0

        return {
            "total_slides": total_slides,
            "total_words": total_words,
            "avg_words_per_slide": round(avg_words_per_slide, 1),
            "recommended_mode": "fast" if avg_words_per_slide < 100 else "precise"
        }


class TextChunker:
    """Handles text chunking for ZD analysis."""

    def __init__(self):
        # Chunking configuration
        self.fast_config = {
            "target_words_min": 4000,
            "target_words_max": 6500,
            "max_pages": 10,
            "overlap_pages": 1
        }

        self.precise_config = {
            "target_words_min": 2500,
            "target_words_max": 4000,
            "max_pages": 5,
            "overlap_pages": 1
        }

    def count_slide_words(self, slide: Dict[str, Any]) -> int:
        """Count words in tagline and body_other only."""
        tagline_words = len(slide["tagline"].split()) if slide["tagline"] else 0
        body_words = len(slide["body_other"].split()) if slide["body_other"] else 0
        return tagline_words + body_words

    def create_chunks(self, zd_slides: List[Dict[str, Any]], mode: str = "fast") -> List[Dict[str, Any]]:
        """Create chunks based on the specified mode."""
        config = self.fast_config if mode == "fast" else self.precise_config
        chunks = []
        chunk_id = 1

        i = 0
        while i < len(zd_slides):
            chunk_slides = []
            chunk_words = 0
            chunk_pages = 0

            # Add slides to chunk until we hit limits
            while (i < len(zd_slides) and
                   chunk_pages < config["max_pages"] and
                   (chunk_words < config["target_words_min"] or
                    (chunk_words + self.count_slide_words(zd_slides[i]) <= config["target_words_max"]))):

                slide_words = self.count_slide_words(zd_slides[i])

                # Avoid infinite loop: if chunk is empty and adding this slide exceeds max, add it anyway
                if not chunk_slides and chunk_words + slide_words > config["target_words_max"]:
                    chunk_slides.append(zd_slides[i])
                    chunk_words += slide_words
                    chunk_pages += 1
                    i += 1
                    break
                elif chunk_words + slide_words <= config["target_words_max"]:
                    chunk_slides.append(zd_slides[i])
                    chunk_words += slide_words
                    chunk_pages += 1
                    i += 1
                else:
                    break

            if chunk_slides:
                chunk = {
                    "chunk_id": f"ck_{chunk_id:04d}",
                    "mode": mode,
                    "page_start": chunk_slides[0]["page_number"],
                    "page_end": chunk_slides[-1]["page_number"],
                    "page_numbers": [slide["page_number"] for slide in chunk_slides],
                    "word_count": chunk_words,
                    "slides": chunk_slides
                }
                chunks.append(chunk)
                chunk_id += 1

                # Handle overlap: move back by overlap_pages - 1
                overlap = min(config["overlap_pages"], len(chunk_slides) - 1)
                i -= overlap

        return chunks


def extract_ppt_for_zd(file_path: str, mode: str = "fast") -> Dict[str, Any]:
    """Main function to extract and chunk PPT for ZD analysis."""
    try:
        extractor = PPTExtractor()
        chunker = TextChunker()

        # Extract raw data
        raw_slides = extractor.extract_powerpoint_text(file_path)
        if not raw_slides:
            raise ValueError("No extractable text found in the presentation")

        # Convert to ZD format
        zd_slides = extractor.convert_to_zd_format(raw_slides)

        # Get statistics
        stats = extractor.get_slide_stats(zd_slides)

        # Create chunks
        chunks = chunker.create_chunks(zd_slides, mode)

        return {
            "success": True,
            "stats": stats,
            "slides": zd_slides,
            "chunks": chunks,
            "total_chunks": len(chunks)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stats": None,
            "slides": [],
            "chunks": [],
            "total_chunks": 0
        }