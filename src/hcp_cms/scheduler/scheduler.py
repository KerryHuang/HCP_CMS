"""Scheduler manager — coordinates background jobs."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass
class JobConfig:
    """Configuration for a scheduled job."""
    name: str
    interval_seconds: int
    callback: Callable[[], None]
    enabled: bool = True
    last_run: datetime | None = None


class Scheduler:
    """Manages scheduled background jobs using threads."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobConfig] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._running = False

    def add_job(self, config: JobConfig) -> None:
        """Register a job."""
        self._jobs[config.name] = config

    def remove_job(self, name: str) -> None:
        """Remove a job."""
        self.stop_job(name)
        self._jobs.pop(name, None)

    def start_job(self, name: str) -> None:
        """Start a specific job's timer."""
        job = self._jobs.get(name)
        if not job or not job.enabled:
            return
        self._schedule_next(job)

    def stop_job(self, name: str) -> None:
        """Stop a specific job's timer."""
        timer = self._timers.pop(name, None)
        if timer:
            timer.cancel()

    def start_all(self) -> None:
        """Start all enabled jobs."""
        self._running = True
        for name, job in self._jobs.items():
            if job.enabled:
                self.start_job(name)

    def stop_all(self) -> None:
        """Stop all jobs."""
        self._running = False
        for name in list(self._timers.keys()):
            self.stop_job(name)

    def run_now(self, name: str) -> None:
        """Execute a job immediately (synchronously)."""
        job = self._jobs.get(name)
        if job:
            job.callback()
            job.last_run = datetime.now()

    def get_job_status(self) -> dict[str, dict]:
        """Get status of all jobs."""
        return {
            name: {
                "enabled": job.enabled,
                "interval": job.interval_seconds,
                "last_run": job.last_run.isoformat() if job.last_run else None,
            }
            for name, job in self._jobs.items()
        }

    def _schedule_next(self, job: JobConfig) -> None:
        """Schedule the next run of a job."""
        if not self._running:
            return

        def _run() -> None:
            try:
                job.callback()
                job.last_run = datetime.now()
            except Exception:
                pass  # Log in real app
            if self._running and job.enabled:
                self._schedule_next(job)

        timer = threading.Timer(job.interval_seconds, _run)
        timer.daemon = True
        self._timers[job.name] = timer
        timer.start()
