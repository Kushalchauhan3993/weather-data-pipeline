"""
scheduler.py - Automated Job Scheduling
=========================================
This module handles running the pipeline automatically on a schedule.

BEGINNER CONCEPT — SCHEDULING:
Think of this like a digital alarm clock for your pipeline.
You set up "jobs" that run at specific times:
- Every 30 minutes: Collect fresh weather data
- Every morning at 8 AM: Generate daily report
- Every Monday at 6 AM: Generate weekly summary
- Every hour: Run health checks

HOW IT WORKS:
1. The APScheduler library lets us define scheduled jobs
2. We register each job with a time rule (cron or interval)
3. The scheduler runs in the background, triggering jobs automatically
4. If the program is restarted, it picks up the schedule again

SCHEDULE OVERVIEW:
┌────────────────────────────────────────────────────────┐
│  JOB                │ SCHEDULE        │ RUNS           │
│─────────────────────│─────────────────│────────────────│
│ ETL Pipeline        │ Every 30 min    │ 48x per day    │
│ Daily Report        │ 8:00 AM daily   │ 1x per day     │
│ Weekly Report       │ Mon 6:00 AM     │ 1x per week    │
│ Health Check        │ Every 1 hour    │ 24x per day    │
│ Data Cleanup        │ 2:00 AM daily   │ 1x per day     │
└────────────────────────────────────────────────────────┘
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from config import ETL_CONFIG, REPORT_CONFIG, MONITOR_CONFIG

logger = logging.getLogger(__name__)

# Try to import APScheduler
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler not installed. Install with: pip install apscheduler")


# ═══════════════════════════════════════════════════════════
# PART 1: Job Functions (what each scheduled task actually does)
# ═══════════════════════════════════════════════════════════

def job_collect_weather(pipeline=None, db=None):
    """
    JOB 1: Collect weather data (runs every 30 minutes).
    This is the core ETL pipeline run.
    """
    logger.info(f"\n⏰ [SCHEDULED] Weather collection started at {datetime.now().strftime('%H:%M:%S')}")
    try:
        from etl_pipeline import ETLPipeline
        from database import DatabaseManager

        if pipeline is None:
            db = db or DatabaseManager()
            pipeline = ETLPipeline(db=db)

        summary = pipeline.run(parallel=True)
        logger.info(f"⏰ [SCHEDULED] Collection done: {summary['cities_succeeded']} cities succeeded")
        return summary
    except Exception as e:
        logger.error(f"⏰ [SCHEDULED] Collection FAILED: {e}")
        return {"error": str(e)}


def job_generate_daily_report(db=None):
    """
    JOB 2: Generate the daily weather report (runs at 8 AM).
    Creates TXT, JSON, and HTML reports.
    """
    logger.info(f"\n⏰ [SCHEDULED] Daily report started at {datetime.now().strftime('%H:%M:%S')}")
    try:
        from reporter import DailyReporter
        from database import DatabaseManager

        db = db or DatabaseManager()
        reporter = DailyReporter(db)
        paths = reporter.generate()
        logger.info(f"⏰ [SCHEDULED] Daily report done: {len(paths)} files generated")
        return paths
    except Exception as e:
        logger.error(f"⏰ [SCHEDULED] Daily report FAILED: {e}")
        return {"error": str(e)}


def job_generate_analytics_report(db=None):
    """
    JOB 3: Generate the analytics report (runs weekly on Mondays).
    Answers all 5 analysis questions.
    """
    logger.info(f"\n⏰ [SCHEDULED] Analytics report started")
    try:
        from reporter import AnalyticsReporter
        from database import DatabaseManager

        db = db or DatabaseManager()
        reporter = AnalyticsReporter(db)
        path = reporter.generate()
        logger.info(f"⏰ [SCHEDULED] Analytics report saved: {path}")
        return path
    except Exception as e:
        logger.error(f"⏰ [SCHEDULED] Analytics report FAILED: {e}")
        return {"error": str(e)}


def job_health_check(db=None, monitor=None):
    """
    JOB 4: Run health checks (runs every hour).
    Checks database, API, and pipeline status.
    """
    try:
        from monitor import PipelineMonitor
        from database import DatabaseManager

        db = db or DatabaseManager()
        monitor = monitor or PipelineMonitor(db)
        health = monitor.full_health_check()
        status = health.get("overall_status", "UNKNOWN")

        if status == "HEALTHY":
            logger.info(f"⏰ [SCHEDULED] Health check: ✅ {status}")
        else:
            logger.warning(f"⏰ [SCHEDULED] Health check: ⚠️ {status}")

        return health
    except Exception as e:
        logger.error(f"⏰ [SCHEDULED] Health check FAILED: {e}")
        return {"error": str(e)}


def job_cleanup_old_data(db=None):
    """
    JOB 5: Delete old data to keep database size manageable (runs at 2 AM daily).
    Keeps data according to data_retention_days in config.
    """
    logger.info(f"\n⏰ [SCHEDULED] Data cleanup started")
    try:
        from database import DatabaseManager

        db = db or DatabaseManager()
        retention_days = ETL_CONFIG.get("data_retention_days", 365)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Delete old weather readings
            cursor.execute("""
                DELETE FROM weather_readings
                WHERE collected_at < datetime('now', ? || ' days')
            """, (f"-{retention_days}",))
            deleted_readings = cursor.rowcount

            # Delete old api logs (keep only 30 days)
            cursor.execute("""
                DELETE FROM api_logs
                WHERE called_at < datetime('now', '-30 days')
            """)
            deleted_logs = cursor.rowcount

            # Delete resolved alerts older than 7 days
            cursor.execute("""
                DELETE FROM weather_alerts
                WHERE is_resolved = 1
                  AND triggered_at < datetime('now', '-7 days')
            """)
            deleted_alerts = cursor.rowcount

        result = {
            "deleted_readings": deleted_readings,
            "deleted_logs":     deleted_logs,
            "deleted_alerts":   deleted_alerts,
        }
        logger.info(f"⏰ [SCHEDULED] Cleanup done: {result}")
        return result
    except Exception as e:
        logger.error(f"⏰ [SCHEDULED] Cleanup FAILED: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# PART 2: WeatherScheduler Class
# ═══════════════════════════════════════════════════════════

class WeatherScheduler:
    """
    Manages all scheduled jobs for the weather pipeline.

    USAGE:
        scheduler = WeatherScheduler()
        scheduler.start()           # Start running in background
        scheduler.show_jobs()       # List all scheduled jobs
        scheduler.stop()            # Stop gracefully
    """

    def __init__(self, db=None, blocking: bool = False):
        """
        Args:
            db:       DatabaseManager instance (creates one if not provided)
            blocking: If True, start() will block (hold) the terminal.
                      If False, runs in background while your code continues.
        """
        from database import DatabaseManager
        self.db       = db or DatabaseManager()
        self.blocking = blocking
        self.scheduler = None
        self.job_history = []

        if not APSCHEDULER_AVAILABLE:
            logger.error("APScheduler not available. Cannot schedule jobs.")
            return

        if blocking:
            self.scheduler = BlockingScheduler(timezone="UTC")
        else:
            self.scheduler = BackgroundScheduler(timezone="UTC")

        # Listen for job events (success/error)
        self.scheduler.add_listener(self._on_job_event,
                                    EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    def _on_job_event(self, event):
        """Called whenever a scheduled job finishes (success or error)."""
        job_id    = event.job_id
        timestamp = datetime.now().isoformat()
        if event.exception:
            logger.error(f"❌ Job '{job_id}' raised: {event.exception}")
            self.job_history.append({
                "job_id": job_id, "status": "ERROR",
                "error": str(event.exception), "at": timestamp
            })
        else:
            logger.debug(f"✅ Job '{job_id}' completed successfully")
            self.job_history.append({
                "job_id": job_id, "status": "OK", "at": timestamp
            })

    def register_all_jobs(self):
        """
        Registers all pipeline jobs with their schedules.
        Call this BEFORE start().
        """
        if not self.scheduler:
            return

        collection_interval = ETL_CONFIG.get("collection_interval", 30)
        report_hour         = REPORT_CONFIG.get("daily_report_hour", 8)

        # ── JOB 1: Weather collection every N minutes ──
        self.scheduler.add_job(
            func        = lambda: job_collect_weather(db=self.db),
            trigger     = IntervalTrigger(minutes=collection_interval),
            id          = "collect_weather",
            name        = f"Collect Weather (every {collection_interval} min)",
            replace_existing = True,
            misfire_grace_time = 300,   # If missed, retry within 5 minutes
        )
        logger.info(f"  ✅ Registered: collect_weather (every {collection_interval} min)")

        # ── JOB 2: Daily report at 8 AM ──
        self.scheduler.add_job(
            func        = lambda: job_generate_daily_report(db=self.db),
            trigger     = CronTrigger(hour=report_hour, minute=0),
            id          = "daily_report",
            name        = f"Daily Report ({report_hour:02d}:00 AM)",
            replace_existing = True,
        )
        logger.info(f"  ✅ Registered: daily_report (daily at {report_hour:02d}:00)")

        # ── JOB 3: Weekly analytics report (Monday 6 AM) ──
        self.scheduler.add_job(
            func        = lambda: job_generate_analytics_report(db=self.db),
            trigger     = CronTrigger(day_of_week="mon", hour=6, minute=0),
            id          = "analytics_report",
            name        = "Analytics Report (Monday 06:00)",
            replace_existing = True,
        )
        logger.info(f"  ✅ Registered: analytics_report (weekly Mon 06:00)")

        # ── JOB 4: Hourly health check ──
        self.scheduler.add_job(
            func        = lambda: job_health_check(db=self.db),
            trigger     = IntervalTrigger(hours=1),
            id          = "health_check",
            name        = "Health Check (hourly)",
            replace_existing = True,
        )
        logger.info(f"  ✅ Registered: health_check (every hour)")

        # ── JOB 5: Daily data cleanup at 2 AM ──
        self.scheduler.add_job(
            func        = lambda: job_cleanup_old_data(db=self.db),
            trigger     = CronTrigger(hour=2, minute=0),
            id          = "data_cleanup",
            name        = "Data Cleanup (02:00 AM)",
            replace_existing = True,
        )
        logger.info(f"  ✅ Registered: data_cleanup (daily at 02:00)")

    def start(self):
        """Starts the scheduler. Runs all registered jobs automatically."""
        if not self.scheduler:
            logger.error("Cannot start — APScheduler not available")
            return

        self.register_all_jobs()

        logger.info("\n🚀 Starting Weather Pipeline Scheduler...")
        self.show_jobs()

        try:
            self.scheduler.start()  # Blocks if blocking=True
        except (KeyboardInterrupt, SystemExit):
            logger.info("\n⛔ Scheduler interrupted. Shutting down gracefully...")
            self.stop()

    def stop(self):
        """Stops the scheduler cleanly."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("🛑 Scheduler stopped.")

    def show_jobs(self):
        """Prints a table of all scheduled jobs."""
        if not self.scheduler:
            return

        jobs = self.scheduler.get_jobs()
        print(f"\n{'─'*65}")
        print(f"  {'JOB NAME':<35} {'NEXT RUN':<25}")
        print(f"{'─'*65}")
        for job in jobs:
            next_run = job.next_run_time
            next_str = next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "Not scheduled"
            print(f"  {job.name:<35} {next_str:<25}")
        print(f"{'─'*65}\n")

    def run_job_now(self, job_id: str):
        """Manually triggers a specific job immediately."""
        job_map = {
            "collect":   job_collect_weather,
            "daily":     job_generate_daily_report,
            "analytics": job_generate_analytics_report,
            "health":    job_health_check,
            "cleanup":   job_cleanup_old_data,
        }
        fn = job_map.get(job_id)
        if fn:
            logger.info(f"▶️  Manually running job: {job_id}")
            return fn(db=self.db)
        else:
            logger.warning(f"Unknown job: {job_id}. Options: {list(job_map.keys())}")


# ═══════════════════════════════════════════════════════════
# PART 3: Simple Manual Runner (no scheduler needed)
# ═══════════════════════════════════════════════════════════

class ManualRunner:
    """
    Simple alternative to the scheduler.
    Runs the pipeline manually (useful for testing or no-scheduler setups).
    """

    def __init__(self, db=None):
        from database import DatabaseManager
        self.db = db or DatabaseManager()

    def run_once(self):
        """Collect weather for all cities right now."""
        return job_collect_weather(db=self.db)

    def run_reports(self):
        """Generate all reports right now."""
        daily     = job_generate_daily_report(db=self.db)
        analytics = job_generate_analytics_report(db=self.db)
        return {"daily": daily, "analytics": analytics}

    def run_health_check(self):
        """Run health check right now."""
        return job_health_check(db=self.db)


# ═══════════════════════════════════════════════════════════
# QUICK TEST
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )
    from database import setup_database

    print("\n" + "="*60)
    print("  SCHEDULER TEST (runs jobs once manually)")
    print("="*60)

    db = setup_database()
    runner = ManualRunner(db=db)

    print("\n[1] Running weather collection...")
    result = runner.run_once()
    print(f"    Status: {result.get('status', result.get('error', 'DONE'))}")

    print("\n[2] Running reports...")
    reports = runner.run_reports()
    print(f"    Daily   : {type(reports['daily'])} generated")
    print(f"    Analytics: generated")

    print("\n[3] Running health check...")
    health = runner.run_health_check()
    print(f"    Status: {health.get('overall_status', 'DONE')}")

    if APSCHEDULER_AVAILABLE:
        print("\n[INFO] To start AUTOMATED scheduling, run:")
        print("       scheduler = WeatherScheduler(blocking=True)")
        print("       scheduler.start()")
    else:
        print("\n[WARNING] APScheduler not installed.")
        print("          Install: pip install apscheduler")
        print("          Then run jobs manually or with cron.")
