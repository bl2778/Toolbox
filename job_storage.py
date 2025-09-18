"""
Persistent Job Storage for ZD Tool
---------------------------------
Provides Redis-based persistent storage for job status and results,
preventing data loss on server restarts.
"""

import json
import time
import redis
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
import os
from dotenv import load_dotenv

load_dotenv()

class PersistentJobStorage:
    """Redis-based persistent storage for modular job/result tracking."""

    def __init__(self, prefix: str = "zd"):
        """Create a storage helper scoped by a namespace prefix.

        The prefix ensures that multiple tools (e.g., ZD, WR) can safely
        coexist in the same Redis instance without key collisions.
        """

        # Redis connection with fallback to in-memory for development
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
            print("[INFO] Redis connected successfully")
        except (redis.ConnectionError, redis.RedisError) as e:
            print(f"[WARNING] Redis not available, falling back to in-memory storage: {e}")
            self.redis_available = False
            # Fallback to in-memory dictionaries
            self._memory_jobs = {}
            self._memory_results = {}

        # Key prefixes (scoped by namespace)
        namespace = prefix.strip() or "zd"
        self.JOB_PREFIX = f"{namespace}_job:"
        self.RESULT_PREFIX = f"{namespace}_result:"
        self.JOB_LIST_KEY = f"{namespace}_jobs_list"

        # TTL for jobs (24 hours)
        self.JOB_TTL = 86400

    def _get_job_key(self, job_id: str) -> str:
        """Get Redis key for job data."""
        return f"{self.JOB_PREFIX}{job_id}"

    def _get_result_key(self, job_id: str) -> str:
        """Get Redis key for job results."""
        return f"{self.RESULT_PREFIX}{job_id}"

    def _serialize(self, data: Any) -> str:
        """Serialize data for Redis storage."""
        return json.dumps(data, default=str, ensure_ascii=False)

    def _deserialize(self, data: str) -> Any:
        """Deserialize data from Redis."""
        return json.loads(data)

    # Job Management
    def create_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """Create a new job entry."""
        try:
            job_data['created_at'] = time.time()
            job_data['last_update'] = time.time()

            if self.redis_available:
                job_key = self._get_job_key(job_id)
                serialized_data = self._serialize(job_data)

                # Store job data with TTL
                self.redis_client.setex(job_key, self.JOB_TTL, serialized_data)

                # Add to jobs list
                self.redis_client.sadd(self.JOB_LIST_KEY, job_id)

                return True
            else:
                self._memory_jobs[job_id] = job_data.copy()
                return True

        except Exception as e:
            print(f"[ERROR] Failed to create job {job_id}: {e}")
            return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job data by ID."""
        try:
            if self.redis_available:
                job_key = self._get_job_key(job_id)
                data = self.redis_client.get(job_key)
                if data:
                    return self._deserialize(data)
                return None
            else:
                return self._memory_jobs.get(job_id)

        except Exception as e:
            print(f"[ERROR] Failed to get job {job_id}: {e}")
            return None

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update job data."""
        try:
            updates['last_update'] = time.time()

            if self.redis_available:
                job_key = self._get_job_key(job_id)

                # Get existing data
                existing_data = self.redis_client.get(job_key)
                if existing_data:
                    job_data = self._deserialize(existing_data)
                    job_data.update(updates)

                    # Update with new TTL
                    serialized_data = self._serialize(job_data)
                    self.redis_client.setex(job_key, self.JOB_TTL, serialized_data)
                    return True
                return False
            else:
                if job_id in self._memory_jobs:
                    self._memory_jobs[job_id].update(updates)
                    return True
                return False

        except Exception as e:
            print(f"[ERROR] Failed to update job {job_id}: {e}")
            return False

    # Chunk Results Management
    def set_chunk_result(self, job_id: str, chunk_id: str, chunk_data: Dict[str, Any]) -> bool:
        """Set chunk result data."""
        try:
            chunk_data['last_update'] = time.time()

            if self.redis_available:
                result_key = self._get_result_key(job_id)

                # Get existing results
                existing_results = self.redis_client.hget(result_key, "chunks") or "{}"
                results_data = self._deserialize(existing_results)

                # Update chunk data
                results_data[chunk_id] = chunk_data

                # Store back with TTL
                serialized_data = self._serialize(results_data)
                self.redis_client.hset(result_key, "chunks", serialized_data)
                self.redis_client.expire(result_key, self.JOB_TTL)

                return True
            else:
                if job_id not in self._memory_results:
                    self._memory_results[job_id] = {}
                self._memory_results[job_id][chunk_id] = chunk_data.copy()
                return True

        except Exception as e:
            print(f"[ERROR] Failed to set chunk result {job_id}:{chunk_id}: {e}")
            return False

    def get_chunk_results(self, job_id: str) -> Dict[str, Any]:
        """Get all chunk results for a job."""
        try:
            if self.redis_available:
                result_key = self._get_result_key(job_id)
                chunks_data = self.redis_client.hget(result_key, "chunks")
                if chunks_data:
                    return self._deserialize(chunks_data)
                return {}
            else:
                return self._memory_results.get(job_id, {})

        except Exception as e:
            print(f"[ERROR] Failed to get chunk results {job_id}: {e}")
            return {}

    def get_chunk_result(self, job_id: str, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get specific chunk result."""
        chunks = self.get_chunk_results(job_id)
        return chunks.get(chunk_id)

    # Job Discovery and Recovery
    def get_active_jobs(self) -> List[str]:
        """Get list of active job IDs."""
        try:
            if self.redis_available:
                job_ids = self.redis_client.smembers(self.JOB_LIST_KEY)
                # Filter out expired jobs
                active_jobs = []
                for job_id in job_ids:
                    if self.redis_client.exists(self._get_job_key(job_id)):
                        active_jobs.append(job_id)
                    else:
                        # Clean up expired job from list
                        self.redis_client.srem(self.JOB_LIST_KEY, job_id)
                return active_jobs
            else:
                return list(self._memory_jobs.keys())

        except Exception as e:
            print(f"[ERROR] Failed to get active jobs: {e}")
            return []

    def cleanup_job(self, job_id: str) -> bool:
        """Clean up job and its results."""
        try:
            if self.redis_available:
                job_key = self._get_job_key(job_id)
                result_key = self._get_result_key(job_id)

                # Remove from Redis
                self.redis_client.delete(job_key, result_key)
                self.redis_client.srem(self.JOB_LIST_KEY, job_id)
                return True
            else:
                self._memory_jobs.pop(job_id, None)
                self._memory_results.pop(job_id, None)
                return True

        except Exception as e:
            print(f"[ERROR] Failed to cleanup job {job_id}: {e}")
            return False


class ZDThreadPoolManager:
    """Manages ThreadPool for chunk processing."""

    def __init__(self, max_workers: int = 5, thread_name_prefix: str = "zd_worker"):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=thread_name_prefix)
        self.active_futures = {}

    def submit_chunk(self, job_id: str, chunk_id: str, func, *args, **kwargs):
        """Submit chunk processing task."""
        future = self.executor.submit(func, *args, **kwargs)
        self.active_futures[f"{job_id}:{chunk_id}"] = future
        return future

    def get_chunk_future(self, job_id: str, chunk_id: str):
        """Get future for specific chunk."""
        return self.active_futures.get(f"{job_id}:{chunk_id}")

    def cleanup_chunk(self, job_id: str, chunk_id: str):
        """Clean up completed chunk future."""
        key = f"{job_id}:{chunk_id}"
        if key in self.active_futures:
            del self.active_futures[key]

    def get_job_futures(self, job_id: str):
        """Get all futures for a job."""
        return {k: v for k, v in self.active_futures.items() if k.startswith(f"{job_id}:")}

    def shutdown(self, wait: bool = True):
        """Shutdown the executor."""
        self.executor.shutdown(wait=wait)


# Global instances for the ZD tool (default namespace)
job_storage = PersistentJobStorage(prefix="zd")
thread_pool = ZDThreadPoolManager(max_workers=5, thread_name_prefix="zd_worker")
