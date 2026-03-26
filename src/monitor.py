"""
monitor.py - System Monitoring & Health Checks
================================================
This module watches the pipeline's health and raises alerts
if something is wrong.

WHAT WE MONITOR:
1. Database health (can we connect? is it slow?)
2. API health (what's the error rate?)
3. Pipeline health (when did it last run? did it succeed?)
4. Disk space (is the database growing too large?)
5. Data freshness (is our data recent enough?)
6. Weather alerts (any extreme weather?)

BEGINNER TIP:
Monitoring is like having a doctor check your system's vital signs.
Just like a doctor checks heart rate, blood pressure, temperature —
we check API error rate, database response time, pipeline success rate.

HEALTH LEVELS:
🟢 HEALTHY  — Everything working perfectly
🟡 DEGRADED — Some issues but still operational
🔴 UNHEALTHY — Critical problems need attention
"""

import logging
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import MONITOR_CONFIG, SQLITE_DB_PATH, LOG_DIR

logger = logging.getLogger(__name__)


class PipelineMonitor:
    """
    Monitors all components of the weather pipeline.

    KEY METRICS TRACKED:
    - db_response_ms : How long database queries take
    - api_error_rate : What % of API calls are failing
    - data_freshness_minutes : How old is our newest data
    - pipeline_last_run_ago : How long since pipeline ran
    - active_alerts : Count of unresolved weather alerts
    - disk_usage_mb : Size of the database file
    """

    def __init__(self, db=None):
        from database import DatabaseManager
        self.db     = db or DatabaseManager()
        self.config = MONITOR_CONFIG
        self.checks_run    = 0
        self.issues_found  = 0

    # ─────────────────────────────────────────────
    # INDIVIDUAL HEALTH CHECKS
    # ─────────────────────────────────────────────

    def check_database(self) -> Dict:
        """
        CHECK: Can we connect to the database? How fast is it?
        HEALTHY if response_ms < max_db_response_ms (default: 1000ms)
        """
        start = time.time()
        try:
            health    = self.db.health_check()
            resp_ms   = round((time.time() - start) * 1000, 2)
            max_ms    = self.config.get("max_db_response_ms", 1000)

            status = "HEALTHY" if resp_ms < max_ms else "DEGRADED"
            return {
                "check":        "database",
                "status":       status,
                "response_ms":  resp_ms,
                "table_counts": health.get("table_counts", {}),
                "message":      f"Response: {resp_ms}ms (limit: {max_ms}ms)",
            }
        except Exception as e:
            return {
                "check":   "database",
                "status":  "UNHEALTHY",
                "error":   str(e),
                "message": f"Database unreachable: {e}",
            }

    def check_api_health(self) -> Dict:
        """
        CHECK: What is the API call error rate over the last 24 hours?
        HEALTHY if error_rate < max_api_error_rate (default: 10%)
        """
        try:
            error_rate = self.db.get_api_error_rate(hours=24)
            max_rate   = self.config.get("max_api_error_rate", 0.10)

            status = (
                "HEALTHY"   if error_rate < max_rate / 2 else
                "DEGRADED"  if error_rate < max_rate else
                "UNHEALTHY"
            )
            return {
                "check":      "api_health",
                "status":     status,
                "error_rate": f"{error_rate*100:.1f}%",
                "threshold":  f"{max_rate*100:.0f}%",
                "message":    f"Error rate: {error_rate*100:.1f}% (limit: {max_rate*100:.0f}%)",
            }
        except Exception as e:
            return {
                "check":   "api_health",
                "status":  "UNKNOWN",
                "error":   str(e),
                "message": f"Could not check API health: {e}",
            }

    def check_data_freshness(self) -> Dict:
        """
        CHECK: How old is our most recent weather reading?
        HEALTHY if data is less than collection_interval × 2 minutes old.
        If data is older, the pipeline might have stopped running.
        """
        try:
            latest  = self.db.get_latest_readings(limit=1)
            max_age = self.config.get("pipeline_timeout_minutes", 15) * 2

            if not latest:
                return {
                    "check":   "data_freshness",
                    "status":  "DEGRADED",
                    "message": "No data in database yet (run pipeline first)",
                }

            collected_str = latest[0].get("collected_at", "")
            collected_at  = datetime.fromisoformat(str(collected_str))
            age_minutes   = (datetime.now() - collected_at).total_seconds() / 60

            status = (
                "HEALTHY"   if age_minutes <= max_age else
                "DEGRADED"  if age_minutes <= max_age * 3 else
                "UNHEALTHY"
            )
            return {
                "check":       "data_freshness",
                "status":      status,
                "age_minutes": round(age_minutes, 1),
                "threshold":   max_age,
                "latest_city": latest[0].get("city_name", "?"),
                "message":     f"Newest data: {age_minutes:.1f} min ago (limit: {max_age} min)",
            }
        except Exception as e:
            return {
                "check":   "data_freshness",
                "status":  "UNKNOWN",
                "error":   str(e),
                "message": f"Could not check freshness: {e}",
            }

    def check_pipeline_runs(self) -> Dict:
        """
        CHECK: Is the pipeline running successfully?
        Looks at the last 5 pipeline runs and checks for failures.
        """
        try:
            runs = self.db.get_pipeline_stats(limit=5)

            if not runs:
                return {
                    "check":   "pipeline_runs",
                    "status":  "DEGRADED",
                    "message": "No pipeline runs recorded yet",
                }

            last_run     = runs[0]
            last_status  = last_run.get("status", "UNKNOWN")
            last_time    = last_run.get("started_at", "?")
            success_count = sum(1 for r in runs if r.get("status") == "SUCCESS")
            partial_count = sum(1 for r in runs if r.get("status") == "PARTIAL")

            if last_status in ["FAILED"]:
                status = "UNHEALTHY"
            elif success_count + partial_count >= len(runs) - 1:
                status = "HEALTHY"
            else:
                status = "DEGRADED"

            return {
                "check":          "pipeline_runs",
                "status":         status,
                "last_run_status": last_status,
                "last_run_at":    last_time,
                "recent_success": f"{success_count}/{len(runs)}",
                "message":        f"Last run: {last_status} | Success: {success_count}/{len(runs)}",
            }
        except Exception as e:
            return {
                "check":   "pipeline_runs",
                "status":  "UNKNOWN",
                "error":   str(e),
                "message": f"Could not check pipeline runs: {e}",
            }

    def check_disk_space(self) -> Dict:
        """
        CHECK: How large is the database file? Is disk space OK?
        Warns at disk_usage_warning_pct (default: 80%).
        """
        try:
            db_path   = Path(SQLITE_DB_PATH)
            db_size_mb = 0.0
            if db_path.exists():
                db_size_mb = round(db_path.stat().st_size / (1024 * 1024), 2)

            # Get log directory size
            log_size_mb = 0.0
            for f in LOG_DIR.glob("*.log"):
                log_size_mb += f.stat().st_size / (1024 * 1024)
            log_size_mb = round(log_size_mb, 2)

            # Get total disk usage
            statvfs  = os.statvfs("/") if hasattr(os, "statvfs") else None
            disk_pct = 0
            if statvfs:
                total_bytes = statvfs.f_blocks * statvfs.f_frsize
                avail_bytes = statvfs.f_bavail * statvfs.f_frsize
                used_bytes  = total_bytes - avail_bytes
                disk_pct    = round((used_bytes / total_bytes) * 100, 1)

            threshold = self.config.get("disk_usage_warning_pct", 80)
            status    = "UNHEALTHY" if disk_pct >= threshold else "HEALTHY"

            return {
                "check":       "disk_space",
                "status":      status,
                "db_size_mb":  db_size_mb,
                "log_size_mb": round(log_size_mb, 2),
                "disk_pct":    disk_pct,
                "threshold":   threshold,
                "message":     f"DB: {db_size_mb}MB | Disk: {disk_pct}%",
            }
        except Exception as e:
            return {
                "check":   "disk_space",
                "status":  "UNKNOWN",
                "error":   str(e),
                "message": f"Could not check disk space: {e}",
            }

    def check_weather_alerts(self) -> Dict:
        """
        CHECK: How many unresolved weather alerts are there?
        This doesn't change SYSTEM health, but is useful info.
        """
        try:
            alerts = self.db.get_active_alerts()
            high_sev = [a for a in alerts if a.get("severity") == "HIGH"]

            return {
                "check":         "weather_alerts",
                "status":        "HEALTHY",
                "total_alerts":  len(alerts),
                "high_severity": len(high_sev),
                "alerts":        alerts[:5],
                "message":       f"{len(alerts)} active alerts ({len(high_sev)} HIGH severity)",
            }
        except Exception as e:
            return {
                "check":   "weather_alerts",
                "status":  "UNKNOWN",
                "error":   str(e),
                "message": f"Could not check alerts: {e}",
            }

    # ─────────────────────────────────────────────
    # FULL HEALTH CHECK (runs all individual checks)
    # ─────────────────────────────────────────────

    def full_health_check(self) -> Dict:
        """
        Runs ALL health checks and returns a comprehensive status report.
        This is the main method called by the scheduler.

        Returns:
            Dict with overall_status and individual check results
        """
        self.checks_run += 1
        start = time.time()

        logger.info("\n🔍 Running full health check...")

        # Run all checks
        checks = {
            "database":       self.check_database(),
            "api_health":     self.check_api_health(),
            "data_freshness": self.check_data_freshness(),
            "pipeline_runs":  self.check_pipeline_runs(),
            "disk_space":     self.check_disk_space(),
            "weather_alerts": self.check_weather_alerts(),
        }

        # Determine overall status
        statuses = [c["status"] for c in checks.values()]
        if "UNHEALTHY" in statuses:
            overall = "UNHEALTHY"
        elif "DEGRADED" in statuses:
            overall = "DEGRADED"
        elif "UNKNOWN" in statuses:
            overall = "DEGRADED"
        else:
            overall = "HEALTHY"

        # Count issues
        issues = [k for k, c in checks.items() if c["status"] != "HEALTHY"]
        if issues:
            self.issues_found += len(issues)
            logger.warning(f"  ⚠️  Issues found: {', '.join(issues)}")

        result = {
            "overall_status":  overall,
            "checked_at":      datetime.now().isoformat(),
            "duration_ms":     round((time.time() - start) * 1000, 2),
            "checks":          checks,
            "issues":          issues,
        }

        # Log summary
        icon = "✅" if overall == "HEALTHY" else ("⚠️" if overall == "DEGRADED" else "🔴")
        logger.info(f"  {icon} Overall Status: {overall}")
        for name, check in checks.items():
            status = check["status"]
            msg    = check.get("message", "")
            icon2  = "✅" if status == "HEALTHY" else ("⚠️" if status == "DEGRADED" else "❌")
            logger.info(f"     {icon2} {name:<20}: {msg}")

        return result

    def print_dashboard(self):
        """
        Prints a pretty text-based monitoring dashboard to the terminal.
        Like a 'command center' view of system health.
        """
        health = self.full_health_check()
        checks = health.get("checks", {})
        now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status_icons = {
            "HEALTHY":   "🟢",
            "DEGRADED":  "🟡",
            "UNHEALTHY": "🔴",
            "UNKNOWN":   "⚪",
        }

        overall      = health["overall_status"]
        overall_icon = status_icons.get(overall, "⚪")

        print("\n" + "╔" + "═"*68 + "╗")
        print(f"║  🌤  WEATHER PIPELINE MONITORING DASHBOARD{' '*25}║")
        print(f"║  Updated: {now}{' '*27}║")
        print("╠" + "═"*68 + "╣")
        print(f"║  OVERALL STATUS: {overall_icon} {overall:<49}║")
        print("╠" + "═"*68 + "╣")

        for check_name, check_data in checks.items():
            status  = check_data.get("status", "UNKNOWN")
            message = check_data.get("message", "")[:45]
            icon    = status_icons.get(status, "⚪")
            name_display = check_name.replace("_", " ").title()
            print(f"║  {icon} {name_display:<22}: {message:<38}║")

        print("╠" + "═"*68 + "╣")

        # Recent pipeline runs
        runs = self.db.get_pipeline_stats(limit=3)
        print(f"║  RECENT PIPELINE RUNS:{' '*45}║")
        if runs:
            for run in runs:
                s  = run.get("status", "?")[:7]
                at = str(run.get("started_at", "?"))[:16]
                ci = run.get("cities_processed", 0)
                ri = run.get("records_inserted", 0)
                print(f"║    {s:<8} | {at} | {ci} cities | {ri} records{' '*14}║")
        else:
            print(f"║    No runs recorded yet.{' '*43}║")

        print("╚" + "═"*68 + "╝\n")

    def get_metrics_summary(self) -> Dict:
        """Returns key metrics as a simple dict (for JSON API endpoints)."""
        health = self.full_health_check()
        db_count = self.db.get_record_count("weather_readings")
        city_count = self.db.get_record_count("cities")
        alert_count = self.db.get_record_count("weather_alerts")

        return {
            "status":           health["overall_status"],
            "total_readings":   db_count,
            "total_cities":     city_count,
            "total_alerts":     alert_count,
            "api_error_rate":   health["checks"].get("api_health", {}).get("error_rate", "N/A"),
            "data_age_minutes": health["checks"].get("data_freshness", {}).get("age_minutes", "N/A"),
            "db_size_mb":       health["checks"].get("disk_space", {}).get("db_size_mb", 0),
            "checked_at":       health["checked_at"],
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from database import setup_database

    print("\n" + "="*60)
    print("  MONITORING DASHBOARD TEST")
    print("="*60)

    db      = setup_database()
    monitor = PipelineMonitor(db)
    monitor.print_dashboard()

    print("\n📊 Quick Metrics:")
    metrics = monitor.get_metrics_summary()
    for k, v in metrics.items():
        print(f"   {k:<25}: {v}")
