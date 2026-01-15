"""
Background task scheduler for Pomodoro Web App.
Handles scheduled tasks using APScheduler with PostgreSQL job store.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler(database_url: str) -> BackgroundScheduler:
    """Get or create the global scheduler instance.

    Args:
        database_url: PostgreSQL database URL for job persistence

    Returns:
        BackgroundScheduler instance
    """
    global _scheduler

    if _scheduler is None:
        # Configure job store to persist jobs in PostgreSQL
        jobstores = {
            'default': SQLAlchemyJobStore(
                url=database_url,
                tablename='apscheduler_jobs'
            )
        }

        # Configure executor (thread pool for concurrent tasks)
        executors = {
            'default': ThreadPoolExecutor(max_workers=5)
        }

        # Job defaults
        job_defaults = {
            'coalesce': True,  # Combine missed jobs into one
            'max_instances': 1,  # Only one instance of each job
            'misfire_grace_time': 3600  # Allow 1 hour grace for missed jobs
        }

        _scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'  # Use UTC for consistency
        )

        logger.info("Scheduler created with PostgreSQL job store")

    return _scheduler


def start_auto_end_day_job():
    """Add the auto end-day job to run at 23:59 every day."""
    scheduler = get_scheduler()

    # Add job to run at 23:59 every day
    # Using cron expression: minute=59, hour=23
    scheduler.add_job(
        func=execute_auto_end_day,
        trigger=CronTrigger(hour=23, minute=59),
        id='auto_end_day',
        name='Auto End Day - Complete previous day at 23:59',
        replace_existing=True,
        misfire_grace_time=3600  # Allow 1 hour grace
    )

    logger.info("Scheduled auto end-day job for 23:59 daily")


def execute_auto_end_day():
    """Execute the auto end-day task (scheduled job)."""
    try:
        # Import here to avoid circular imports
        from models.database import check_and_complete_previous_day, get_auto_end_day_state, update_auto_end_day_state

        logger.info("Executing auto end-day scheduled job")

        # Check if feature is enabled
        state = get_auto_end_day_state()
        if not state.get('enabled', False):
            logger.info("Auto end-day feature is disabled, skipping")
            return

        # Get yesterday's date (the day we're completing)
        yesterday = date.today() - timedelta(days=1)

        # Check if we already completed this day
        last_completed = state.get('last_completed_date')
        if last_completed == str(yesterday):
            logger.info(f"Day {yesterday} already auto-completed, skipping")
            return

        # Perform the completion
        result = check_and_complete_previous_day(yesterday)

        if result:
            update_auto_end_day_state(
                last_run_at=datetime.now().isoformat()
            )
            logger.info(f"Auto end-day job completed successfully for {yesterday}")
        else:
            logger.info(f"Auto end-day job: day {yesterday} was already completed manually")

    except Exception as e:
        logger.error(f"Error in auto end-day scheduled job: {e}", exc_info=True)


def run_startup_catchup():
    """Run catch-up logic when app starts.

    Checks if the previous day wasn't completed and completes it if needed.
    This handles cases where:
    - App was stopped at 22:00 and restarted at 22:30
    - App was stopped for multiple days
    - Docker container was restarted
    """
    try:
        # Import here to avoid circular imports
        from models.database import check_and_complete_previous_day, get_auto_end_day_state

        logger.info("Running startup catch-up check")

        # Check if feature is enabled
        state = get_auto_end_day_state()
        if not state.get('enabled', False):
            logger.info("Auto end-day feature is disabled, skipping catch-up")
            return

        # Check yesterday
        yesterday = date.today() - timedelta(days=1)

        # Only complete if not already done
        last_completed = state.get('last_completed_date')
        if last_completed != str(yesterday):
            logger.info(f"Startup catch-up: checking day {yesterday}")
            result = check_and_complete_previous_day(yesterday)
            if result:
                logger.info(f"Startup catch-up: successfully completed {yesterday}")
            else:
                logger.info(f"Startup catch-up: day {yesterday} already completed")
        else:
            logger.info(f"Startup catch-up: day {yesterday} already marked as completed")

    except Exception as e:
        logger.error(f"Error in startup catch-up: {e}", exc_info=True)


def start_scheduler(database_url: str):
    """Start the scheduler with all jobs.

    Args:
        database_url: PostgreSQL database URL for job persistence
    """
    try:
        scheduler = get_scheduler(database_url)

        # Add the auto end-day job
        start_auto_end_day_job()

        # Start the scheduler
        scheduler.start()

        logger.info("Scheduler started successfully")

        # Run startup catch-up
        run_startup_catchup()

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)


def stop_scheduler():
    """Stop the scheduler gracefully."""
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")


def is_scheduler_running() -> bool:
    """Check if scheduler is running.

    Returns:
        True if scheduler is running
    """
    global _scheduler
    return _scheduler is not None and _scheduler.running


def get_scheduled_jobs() -> list:
    """Get list of scheduled jobs.

    Returns:
        List of job dictionaries with id, name, next_run_time
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        jobs = []
        for job in _scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': str(job.next_run_time) if job.next_run_time else None
            })
        return jobs
    return []
