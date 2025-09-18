"""Chunk orchestration and LLM streaming for WR."""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Any, List

from openai import OpenAI

from .config import DEFAULT_MODEL, REQUEST_TIMEOUT, STALL_THRESHOLD
from .parse_table import parse_wr_table, merge_rows
from .prompt import build_user_message
from .storage import (
    get_job,
    update_job,
    set_chunk_result,
    update_chunk_result,
    get_chunk_results,
)
from .models import ChunkResultRow

OPENAI_CLIENT = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://chat01.ai"),
    timeout=REQUEST_TIMEOUT,
    max_retries=0,
)


ACTIVE_CHUNK_STATUSES = {"starting", "sending", "processing"}


def _initialize_chunk(job_id: str, chunk: Dict[str, Any]) -> Dict[str, Any]:
    now = time.time()
    chunk_state = {
        "chunk_id": chunk["chunk_id"],
        "status": "starting",
        "page_start": chunk["page_start"],
        "page_end": chunk["page_end"],
        "page_numbers": chunk["page_numbers"],
        "word_count": chunk["word_count"],
        "mode": chunk["mode"],
        "start_time": now,
        "streaming_output": "",
        "ai_progress": "Initializing...",
        "result_text": "",
        "rows": [],
        "error": None,
        "attempts": chunk.get("attempts", 0) + 1,
        "last_update": now,
    }
    set_chunk_result(job_id, chunk["chunk_id"], chunk_state)
    return chunk_state


def _recover_stalled_chunks(job_id: str, chunk_results: Dict[str, Any]) -> bool:
    now = time.time()
    recovered = False
    for chunk_id, chunk_state in chunk_results.items():
        status = chunk_state.get("status")
        if status not in ACTIVE_CHUNK_STATUSES:
            continue
        last_update = chunk_state.get("last_update") or chunk_state.get("start_time") or now
        if now - last_update <= STALL_THRESHOLD:
            continue
        recovered = True
        update_chunk_result(
            job_id,
            chunk_id,
            {
                "status": "failed",
                "completion_time": now,
                "error": "No response from model (stalled).",
                "ai_progress": "Failed: stalled without response",
                "last_update": now,
            },
        )
    return recovered


def update_thinking_progress(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return

    chunk_results = get_chunk_results(job_id)
    if _recover_stalled_chunks(job_id, chunk_results):
        chunk_results = get_chunk_results(job_id)

    sent = sum(
        1
        for chunk in chunk_results.values()
        if chunk.get("status") not in {None, "starting"}
    )
    completed = sum(1 for chunk in chunk_results.values() if chunk.get("status") == "completed")
    failed = sum(1 for chunk in chunk_results.values() if chunk.get("status") == "failed")
    percent = int((completed / sent) * 100) if sent else 0

    updates: Dict[str, Any] = {
        "thinking_progress": percent,
        "chunks_sent": sent,
        "chunks_completed": completed,
        "chunks_failed": failed,
        "last_update": time.time(),
    }
    if job.get("status") not in {"MERGING", "DONE", "ERROR"} and sent:
        updates["status"] = "PROMPTING/THINKING"

    update_job(job_id, updates)


def process_chunk(job_id: str, chunk: Dict[str, Any], model_name: str | None = None) -> None:
    model = model_name or DEFAULT_MODEL
    chunk_state = _initialize_chunk(job_id, chunk)

    update_job(job_id, {"status": "PROMPTING/THINKING", "last_update": time.time()})

    update_chunk_result(
        job_id,
        chunk["chunk_id"],
        {
            "status": "sending",
            "ai_progress": "Sending prompt to model...",
            "last_update": time.time(),
        },
    )

    job = get_job(job_id)
    sent_count = (job or {}).get("chunks_sent", 0) + 1
    update_job(
        job_id,
        {
            "chunks_sent": sent_count,
            "status": "PROMPTING/THINKING",
            "last_update": time.time(),
        },
    )

    payload_str = json.dumps(chunk["json_payload"], ensure_ascii=False, indent=2)
    user_message = build_user_message(payload_str)

    update_chunk_result(
        job_id,
        chunk["chunk_id"],
        {
            "status": "processing",
            "ai_progress": "Model is generating edits...",
            "last_update": time.time(),
        },
    )

    result_text = ""
    last_token_time = time.time()

    try:
        response = OPENAI_CLIENT.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_message}],
            temperature=0,
            top_p=1,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        )

        for part in response:
            delta = part.choices[0].delta.content if part.choices else None
            if delta:
                result_text += delta
                last_token_time = time.time()
                update_chunk_result(
                    job_id,
                    chunk["chunk_id"],
                    {
                        "streaming_output": result_text,
                        "ai_progress": "AI thinking...",
                        "last_update": last_token_time,
                    },
                )

        rows: List[ChunkResultRow] = []
        cleaned = result_text.strip()
        if cleaned.lower() == "no edits recommended.":
            rows = []
        else:
            rows = parse_wr_table(result_text)

        update_chunk_result(
            job_id,
            chunk["chunk_id"],
            {
                "status": "completed",
                "completion_time": time.time(),
                "result_text": result_text,
                "final_result_text": result_text,
                "rows": [row.__dict__ for row in rows],
                "ai_progress": "Completed",
                "last_update": time.time(),
            },
        )

        job = get_job(job_id) or {}
        completed_count = job.get("chunks_completed", 0) + 1
        update_job(
            job_id,
            {"chunks_completed": completed_count, "last_update": time.time()},
        )
        update_thinking_progress(job_id)

        _attempt_merge(job_id)
    except Exception as exc:
        update_chunk_result(
            job_id,
            chunk["chunk_id"],
            {
                "status": "failed",
                "completion_time": time.time(),
                "error": str(exc),
                "ai_progress": f"Failed: {exc}",
                "last_update": time.time(),
            },
        )
        job = get_job(job_id) or {}
        update_job(
            job_id,
            {"chunks_failed": job.get("chunks_failed", 0) + 1, "last_update": time.time()},
        )
        update_thinking_progress(job_id)


def _attempt_merge(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    total = job.get("chunks_total", 0)
    chunk_results = get_chunk_results(job_id)
    if not chunk_results:
        return
    completed_chunks = [
        chunk
        for chunk in chunk_results.values()
        if chunk.get("status") == "completed"
    ]
    if total and len(completed_chunks) < total:
        return

    all_rows: List[ChunkResultRow] = []
    for chunk in completed_chunks:
        for row_dict in chunk.get("rows", []):
            all_rows.append(ChunkResultRow(**row_dict))

    merged = merge_rows(all_rows)
    update_job(
        job_id,
        {
            "status": "MERGING", 
            "last_update": time.time(),
        },
    )

    final_rows = merged
    update_job(
        job_id,
        {
            "status": "DONE",
            "result_rows": [row.__dict__ for row in final_rows],
            "no_edits": len(final_rows) == 0,
            "completion_time": time.time(),
            "thinking_progress": 100,
            "last_update": time.time(),
        },
    )
