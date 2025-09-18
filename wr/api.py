"""Flask blueprint implementing WR APIs."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, Optional

from flask import Blueprint, Response, jsonify, request, session

from .chunker import chunk_slides
from .config import DEFAULT_MODEL, DEFAULT_MODE
from .export import to_csv, to_xlsx, to_json
from .llm import process_chunk, update_thinking_progress
from .parser import extract_slim_json
from .storage import (
    create_job,
    get_job,
    update_job,
    get_chunk_results,
    get_chunk_result,
    update_chunk_result,
    thread_pool,
)
from .models import ChunkResultRow

wr_bp = Blueprint("wr", __name__, url_prefix="/api/wr")

ALLOWED_MODELS = {
    "gpt-5-pro",
    "gpt-5",
    "gpt-5-thinking",
    "gpt-4.5",
    "gpt-4",
}


def _require_auth() -> Optional[Response]:
    if request.endpoint == "wr.health":
        return None
    if not session.get("authenticated", False):
        return jsonify({"error": "Unauthorized"}), 401
    return None


@wr_bp.before_request
def before_request():
    auth_error = _require_auth()
    if auth_error:
        return auth_error


@wr_bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@wr_bp.route("/jobs", methods=["POST"])
def create_wr_job():
    if "ppt_file" not in request.files:
        return jsonify({"error": "No PPT file provided"}), 400
    file = request.files["ppt_file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not file.filename.lower().endswith(".pptx"):
        return jsonify({"error": "Invalid file format. Please upload a .pptx file"}), 400

    job_id = str(uuid.uuid4())
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pptx")
    file.save(temp_file.name)
    temp_file.close()

    job_data = {
        "job_id": job_id,
        "status": "UPLOADING",
        "filename": file.filename,
        "temp_file_path": temp_file.name,
        "created_at": time.time(),
        "last_update": time.time(),
        "chunks_total": 0,
        "chunks_sent": 0,
        "chunks_completed": 0,
        "chunks_failed": 0,
        "result_rows": [],
        "no_edits": False,
        "thinking_progress": 0,
    }
    create_job(job_id, job_data)

    return jsonify({"success": True, "job_id": job_id})


def _parse_mode(value: Optional[str]) -> str:
    if value in {"fast", "precise"}:
        return value
    return DEFAULT_MODE


def _parse_model(value: Optional[str]) -> str:
    if value and value.lower() in ALLOWED_MODELS:
        return value.lower()
    return DEFAULT_MODEL


@wr_bp.route("/jobs/<job_id>/run", methods=["POST"])
def run_wr_job(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    payload = request.get_json(silent=True) or {}
    mode = _parse_mode(payload.get("mode"))
    model = _parse_model(payload.get("model"))

    update_job(job_id, {"status": "PARSING", "mode": mode, "model": model, "last_update": time.time()})

    temp_file_path = job.get("temp_file_path")

    def process_job():
        try:
            slides = extract_slim_json(temp_file_path)
            update_job(job_id, {"status": "CHUNKING", "last_update": time.time(), "slides_count": len(slides)})

            chunks = chunk_slides(slides, mode)
            update_job(
                job_id,
                {
                    "chunks": chunks,
                    "chunks_total": len(chunks),
                    "status": "PROMPTING/THINKING" if chunks else "MERGING",
                    "last_update": time.time(),
                },
            )

            if not chunks:
                update_job(
                    job_id,
                    {
                        "status": "DONE",
                        "result_rows": [],
                        "no_edits": True,
                        "completion_time": time.time(),
                        "last_update": time.time(),
                    },
                )
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                return

            for chunk in chunks:
                chunk_copy = dict(chunk)
                chunk_copy["mode"] = mode
                chunk_copy.setdefault("attempts", 0)
                thread_pool.submit_chunk(
                    job_id,
                    chunk_copy["chunk_id"],
                    process_chunk,
                    job_id,
                    chunk_copy,
                    model,
                )
            update_thinking_progress(job_id)
        except Exception as exc:
            update_job(
                job_id,
                {"status": "ERROR", "error": str(exc), "last_update": time.time()},
            )
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

    threading.Thread(target=process_job, name=f"wr_main_{job_id}", daemon=True).start()

    return jsonify({"success": True})


@wr_bp.route("/jobs/<job_id>")
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    chunks = get_chunk_results(job_id)
    return jsonify({"job": job, "chunks": chunks})


@wr_bp.route("/jobs/<job_id>/result")
def get_job_result(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    rows = [
        ChunkResultRow(**row_dict) if isinstance(row_dict, dict) else row_dict
        for row_dict in job.get("result_rows", [])
    ]

    fmt = request.args.get("format", "json").lower()
    include_raw = request.args.get("include_raw", "false").lower() == "true"

    if fmt == "csv":
        data = to_csv(rows)
        return Response(
            data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=wr_{job_id[:8]}.csv"},
        )
    if fmt == "xlsx":
        data = to_xlsx(rows)
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=wr_{job_id[:8]}.xlsx"},
        )

    result: Dict[str, Any] = {"rows": to_json(rows), "no_edits": job.get("no_edits", False)}
    if include_raw:
        result["raw_chunks"] = get_chunk_results(job_id)
    return jsonify(result)


@wr_bp.route("/jobs/<job_id>/chunks/<chunk_id>/retry", methods=["POST"])
def retry_chunk(job_id: str, chunk_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    chunk_meta = next((chunk for chunk in job.get("chunks", []) if chunk["chunk_id"] == chunk_id), None)
    if not chunk_meta:
        return jsonify({"error": "Chunk not found"}), 404

    chunk_state = get_chunk_result(job_id, chunk_id)
    if chunk_state and chunk_state.get("status") not in {"failed", "completed"}:
        return jsonify({"error": "Chunk is currently processing"}), 400

    update_chunk_result(
        job_id,
        chunk_id,
        {
            "status": "starting",
            "streaming_output": "",
            "ai_progress": "Retrying...",
            "result_text": "",
            "error": None,
            "start_time": time.time(),
            "rows": [],
            "last_update": time.time(),
        },
    )
    attempts = chunk_state.get("attempts", 0) if chunk_state else 0
    chunk_payload = dict(chunk_meta)
    chunk_payload["attempts"] = attempts
    update_job(
        job_id,
        {
            "status": "PROMPTING/THINKING",
            "no_edits": False,
            "completion_time": None,
            "last_update": time.time(),
        },
    )
    thread_pool.submit_chunk(job_id, chunk_id, process_chunk, job_id, chunk_payload, job.get("model", DEFAULT_MODEL))
    update_thinking_progress(job_id)
    return jsonify({"success": True})


@wr_bp.route("/jobs/<job_id>/chunks/<chunk_id>/recheck", methods=["POST"])
def recheck_chunk(job_id: str, chunk_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    chunk_meta = next((chunk for chunk in job.get("chunks", []) if chunk["chunk_id"] == chunk_id), None)
    if not chunk_meta:
        return jsonify({"error": "Chunk not found"}), 404

    update_chunk_result(
        job_id,
        chunk_id,
        {
            "status": "starting",
            "streaming_output": "",
            "ai_progress": "Re-checking...",
            "result_text": "",
            "error": None,
            "start_time": time.time(),
            "rows": [],
            "last_update": time.time(),
        },
    )
    chunk_state = get_chunk_result(job_id, chunk_id)
    attempts = chunk_state.get("attempts", 0) if chunk_state else 0
    chunk_payload = dict(chunk_meta)
    chunk_payload["attempts"] = attempts
    update_job(
        job_id,
        {
            "status": "PROMPTING/THINKING",
            "no_edits": False,
            "completion_time": None,
            "last_update": time.time(),
        },
    )
    thread_pool.submit_chunk(job_id, chunk_id, process_chunk, job_id, chunk_payload, job.get("model", DEFAULT_MODEL))
    update_thinking_progress(job_id)
    return jsonify({"success": True})


@wr_bp.route("/jobs/<job_id>/debug")
def debug_job(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    chunks = get_chunk_results(job_id)
    return jsonify({"job": job, "chunks": chunks})
