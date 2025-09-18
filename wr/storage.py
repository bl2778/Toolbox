"""Storage helpers for WR jobs and chunks."""

from __future__ import annotations

from typing import Dict, Any, Optional

from job_storage import PersistentJobStorage, ZDThreadPoolManager

from .config import MAX_WORKERS

storage = PersistentJobStorage(prefix="wr")
thread_pool = ZDThreadPoolManager(max_workers=MAX_WORKERS, thread_name_prefix="wr_worker")

wr_jobs: Dict[str, Dict[str, Any]] = {}
wr_results: Dict[str, Dict[str, Any]] = {}


def create_job(job_id: str, job_data: Dict[str, Any]) -> None:
    storage.create_job(job_id, job_data)
    wr_jobs[job_id] = job_data.copy()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    job = wr_jobs.get(job_id)
    if job:
        return job
    job = storage.get_job(job_id)
    if job:
        wr_jobs[job_id] = job
    return job


def update_job(job_id: str, updates: Dict[str, Any]) -> None:
    storage.update_job(job_id, updates)
    if job_id in wr_jobs:
        wr_jobs[job_id].update(updates)


def set_chunk_result(job_id: str, chunk_id: str, chunk_data: Dict[str, Any]) -> None:
    if job_id not in wr_results:
        wr_results[job_id] = {}
    wr_results[job_id][chunk_id] = chunk_data.copy()
    storage.set_chunk_result(job_id, chunk_id, chunk_data)


def update_chunk_result(job_id: str, chunk_id: str, updates: Dict[str, Any]) -> None:
    chunk = wr_results.setdefault(job_id, {}).setdefault(chunk_id, {})
    chunk.update(updates)
    storage.set_chunk_result(job_id, chunk_id, chunk)


def get_chunk_result(job_id: str, chunk_id: str) -> Optional[Dict[str, Any]]:
    chunk = wr_results.get(job_id, {}).get(chunk_id)
    if chunk:
        return chunk
    chunk = storage.get_chunk_result(job_id, chunk_id)
    if chunk:
        wr_results.setdefault(job_id, {})[chunk_id] = chunk
    return chunk


def get_chunk_results(job_id: str) -> Dict[str, Dict[str, Any]]:
    if job_id not in wr_results:
        wr_results[job_id] = storage.get_chunk_results(job_id)
    return wr_results[job_id]


def cleanup_job(job_id: str) -> None:
    storage.cleanup_job(job_id)
    wr_jobs.pop(job_id, None)
    wr_results.pop(job_id, None)
