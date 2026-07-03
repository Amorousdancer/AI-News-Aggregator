"""APScheduler setup and management.

Uses AsyncIOScheduler with a SQLAlchemy job store (PostgreSQL-backed).
Jobs survive restarts — state is persisted in the database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.scheduler.tasks import (
    analyze_pending_articles,
    cleanup_old_articles,
    fetch_all_sources,
    generate_daily_report,
)

logger = logging.getLogger(__name__)

# Module-level singleton — created once, shared across the application
scheduler_manager: SchedulerManager | None = None


class SchedulerManager:
    """Manages the APScheduler instance and registered jobs."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            timezone=timezone.utc,
            job_defaults={
                "coalesce": True,      # If a job is missed, don't queue multiple runs
                "max_instances": 1,     # No overlapping runs of the same job
                "misfire_grace_time": 300,  # 5 minutes grace for missed jobs
            },
        )
        self._jobs_registered = False

    def register_jobs(self) -> None:
        """Register all scheduled jobs."""
        if self._jobs_registered:
            return

        # Fetch articles from all sources every 30 minutes
        self.scheduler.add_job(
            fetch_all_sources,
            trigger=IntervalTrigger(minutes=30),
            id="fetch_all_sources",
            name="Fetch all sources",
            replace_existing=True,
        )

        # Analyze pending articles every hour
        self.scheduler.add_job(
            analyze_pending_articles,
            trigger=IntervalTrigger(minutes=60),
            id="analyze_pending_articles",
            name="Analyze pending articles",
            replace_existing=True,
        )

        # Generate daily report at 08:00 UTC
        self.scheduler.add_job(
            generate_daily_report,
            trigger=CronTrigger(hour=8, minute=0),
            id="generate_daily_report",
            name="Generate daily report",
            replace_existing=True,
        )

        # Cleanup old articles at 03:00 UTC
        self.scheduler.add_job(
            cleanup_old_articles,
            trigger=CronTrigger(hour=3, minute=0),
            id="cleanup_old_articles",
            name="Cleanup old articles",
            replace_existing=True,
        )

        self._jobs_registered = True
        logger.info("Scheduler jobs registered")

    def start(self) -> None:
        """Start the scheduler."""
        self.register_jobs()
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler shut down")

    def get_health(self) -> dict:
        """Return scheduler health status for the /health endpoint."""
        jobs = {}
        for job in self.scheduler.get_jobs():
            jobs[job.id] = {
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }

        return {
            "scheduler_running": self.scheduler.running,
            "jobs": jobs,
        }


def get_scheduler_manager() -> SchedulerManager:
    """Get or create the global scheduler manager singleton."""
    global scheduler_manager
    if scheduler_manager is None:
        scheduler_manager = SchedulerManager()
    return scheduler_manager
