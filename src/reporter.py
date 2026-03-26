"""
reporter.py - Automated Report Generation
==========================================
This module generates weather analysis reports in multiple formats.

REPORTS GENERATED:
1. Daily Summary Report  — temperature, humidity, alerts per day
2. Weekly Trends Report  — 7-day trends and comparisons
3. City Comparison Report — which city is hottest/coldest/windiest
4. Seasonal Analysis     — patterns by season
5. Correlation Report    — humidity vs rainfall analysis

OUTPUT FORMATS:
- TXT  : Plain text (works anywhere)
- JSON : Machine-readable (for dashboards / APIs)
- HTML : Pretty browser report with tables

BEGINNER TIP:
Think of this file as a "newspaper editor" that takes raw database
data and formats it into readable, useful reports automatically.
"""

import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import REPORT_DIR, REPORT_CONFIG
from database import DatabaseManager

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# PART 1: Base Report Builder
# ═══════════════════════════════════════════════════════════

class ReportBuilder:
    """Base class with shared utility methods for all reports."""

    def __init__(self, db: DatabaseManager):
        self.db          = db
        self.report_dir  = REPORT_DIR
        self.generated   = []

    def _save(self, content: str, filename: str) -> str:
        """Saves report content to file and returns the file path."""
        filepath = self.report_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        self.generated.append(str(filepath))
        logger.info(f"  📄 Report saved: {filepath.name}")
        return str(filepath)

    def _header(self, title: str, width: int = 70) -> str:
        """Creates a nice text header."""
        line  = "═" * width
        return f"\n{line}\n  {title}\n  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{line}\n"

    def _section(self, title: str, width: int = 70) -> str:
        """Creates a section divider."""
        return f"\n{'─' * width}\n  {title.upper()}\n{'─' * width}\n"

    def _table(self, headers: List[str], rows: List[List],
                col_widths: List[int]) -> str:
        """Creates a formatted ASCII table."""
        lines = []
        # Header
        header_row = " | ".join(
            str(h).ljust(w) for h, w in zip(headers, col_widths)
        )
        lines.append(header_row)
        lines.append("-+-".join("-" * w for w in col_widths))
        # Data rows
        for row in rows:
            data_row = " | ".join(
                str(cell).ljust(w)[:w] for cell, w in zip(row, col_widths)
            )
            lines.append(data_row)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# PART 2: Daily Report
# ═══════════════════════════════════════════════════════════

class DailyReporter(ReportBuilder):
    """
    Generates the daily weather summary report.
    Runs every morning at 8 AM (configured in scheduler.py).
    """

    def generate(self, target_date: date = None) -> Dict[str, str]:
        """
        Creates today's (or a specific date's) daily report.

        Args:
            target_date: The date to report on (defaults to today)

        Returns:
            Dict mapping format → file path
        """
        target_date = target_date or date.today()
        date_str    = target_date.strftime("%Y-%m-%d")
        logger.info(f"📊 Generating daily report for {date_str}")

        # Fetch data from database
        temp_stats  = self.db.get_temperature_stats(days=1)
        alerts      = self.db.get_active_alerts()
        latest      = self.db.get_latest_readings(limit=20)
        api_errors  = self.db.get_api_error_rate(hours=24)

        # Generate in each format
        saved = {}
        saved["txt"]  = self._generate_txt(date_str, temp_stats, alerts, api_errors)
        saved["json"] = self._generate_json(date_str, temp_stats, alerts, api_errors, latest)
        saved["html"] = self._generate_html(date_str, temp_stats, alerts, latest)

        logger.info(f"  ✅ Daily report complete: {len(saved)} formats")
        return saved

    def _generate_txt(self, date_str, temp_stats, alerts, api_error_rate) -> str:
        lines = []
        lines.append(self._header(f"DAILY WEATHER REPORT — {date_str}"))

        lines.append(self._section("Temperature Summary by City"))
        if temp_stats:
            headers   = ["City", "Country", "Avg °C", "Max °C", "Min °C", "Readings"]
            col_w     = [15, 8, 8, 8, 8, 10]
            rows = [
                [r["city"], r["country"],
                 f"{r['avg_temp']}",
                 f"{r['max_temp']}",
                 f"{r['min_temp']}",
                 r["total_readings"]]
                for r in temp_stats
            ]
            lines.append(self._table(headers, rows, col_w))
        else:
            lines.append("  No data available for this period.")

        lines.append(self._section("Active Weather Alerts"))
        if alerts:
            for alert in alerts[:10]:
                emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "INFO": "🟢"}.get(
                    alert.get("severity", "INFO"), "⚪"
                )
                lines.append(
                    f"  {emoji} [{alert['severity']}] {alert['city_name']}: "
                    f"{alert['alert_type']} = {alert['value']}"
                )
        else:
            lines.append("  ✅ No active alerts — all clear!")

        lines.append(self._section("System Health"))
        lines.append(f"  API Error Rate (24h) : {api_error_rate*100:.1f}%")
        lines.append(f"  Status               : {'⚠️ HIGH ERRORS' if api_error_rate > 0.10 else '✅ OK'}")

        content = "\n".join(lines) + "\n"
        return self._save(content, f"daily_{date_str}.txt")

    def _generate_json(self, date_str, temp_stats, alerts, api_error_rate, latest) -> str:
        report = {
            "report_type":    "daily",
            "report_date":    date_str,
            "generated_at":   datetime.now().isoformat(),
            "summary": {
                "cities_reported":  len(temp_stats),
                "active_alerts":    len(alerts),
                "api_error_rate":   api_error_rate,
            },
            "temperature_stats": temp_stats,
            "active_alerts":     alerts[:20],
            "recent_readings":   latest[:10],
        }
        content = json.dumps(report, indent=2, default=str)
        return self._save(content, f"daily_{date_str}.json")

    def _generate_html(self, date_str, temp_stats, alerts, latest) -> str:
        # Build HTML rows for temperature table
        temp_rows = ""
        for r in temp_stats:
            bg = "#ffe4e4" if float(r.get("avg_temp", 0)) > 35 else (
                 "#e4eeff" if float(r.get("avg_temp", 0)) < 5 else "#ffffff")
            temp_rows += f"""
            <tr style="background:{bg}">
                <td><strong>{r['city']}</strong></td>
                <td>{r['country']}</td>
                <td>{r['avg_temp']}°C</td>
                <td style="color:#c0392b"><strong>{r['max_temp']}°C</strong></td>
                <td style="color:#2980b9"><strong>{r['min_temp']}°C</strong></td>
                <td>{r['total_readings']}</td>
            </tr>"""

        # Build HTML rows for alerts
        alert_rows = ""
        severity_colors = {"HIGH": "#e74c3c", "MEDIUM": "#f39c12", "INFO": "#27ae60"}
        for alert in alerts[:10]:
            color = severity_colors.get(alert.get("severity", "INFO"), "#999")
            alert_rows += f"""
            <tr>
                <td>{alert['city_name']}</td>
                <td><span style="color:{color};font-weight:bold">{alert.get('severity','')}</span></td>
                <td>{alert['alert_type']}</td>
                <td>{alert.get('value','N/A')}</td>
                <td>{alert.get('triggered_at','')[:16]}</td>
            </tr>"""

        if not alert_rows:
            alert_rows = '<tr><td colspan="5" style="text-align:center;color:green">✅ No active alerts</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Daily Weather Report — {date_str}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px;
          background: #f0f4f8; color: #333; }}
  .container {{ max-width: 1000px; margin: auto; }}
  h1 {{ background: linear-gradient(135deg, #1a237e, #283593);
        color: white; padding: 20px 30px; border-radius: 10px; margin-bottom: 20px; }}
  h2 {{ color: #1a237e; border-bottom: 2px solid #1a237e;
        padding-bottom: 8px; margin-top: 30px; }}
  .card {{ background: white; border-radius: 10px; padding: 20px;
           box-shadow: 0 2px 10px rgba(0,0,0,0.08); margin-bottom: 20px; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr);
                 gap: 15px; margin-bottom: 20px; }}
  .stat-box {{ background: white; border-radius: 8px; padding: 15px;
               text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.07); }}
  .stat-number {{ font-size: 2em; font-weight: bold; color: #1a237e; }}
  .stat-label {{ color: #666; font-size: 0.9em; margin-top: 5px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  th {{ background: #1a237e; color: white; padding: 10px 12px; text-align: left; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #f5f8ff; }}
  .footer {{ text-align: center; color: #999; font-size: 0.8em;
             margin-top: 30px; padding: 15px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🌤 Daily Weather Report<br>
    <small style="font-size:0.6em;font-weight:normal">{date_str}</small>
  </h1>

  <div class="stats-grid">
    <div class="stat-box">
      <div class="stat-number">{len(temp_stats)}</div>
      <div class="stat-label">Cities Tracked</div>
    </div>
    <div class="stat-box">
      <div class="stat-number" style="color:{'#e74c3c' if alerts else '#27ae60'}">
        {len(alerts)}
      </div>
      <div class="stat-label">Active Alerts</div>
    </div>
    <div class="stat-box">
      <div class="stat-number">
        {max((r['avg_temp'] for r in temp_stats), default='N/A')}°C
      </div>
      <div class="stat-label">Highest City Avg</div>
    </div>
  </div>

  <div class="card">
    <h2>🌡 Temperature Summary</h2>
    <table>
      <thead><tr>
        <th>City</th><th>Country</th>
        <th>Avg Temp</th><th>Max Temp</th><th>Min Temp</th><th>Readings</th>
      </tr></thead>
      <tbody>{temp_rows or '<tr><td colspan="6">No data</td></tr>'}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>🚨 Weather Alerts</h2>
    <table>
      <thead><tr>
        <th>City</th><th>Severity</th><th>Alert Type</th>
        <th>Value</th><th>Triggered At</th>
      </tr></thead>
      <tbody>{alert_rows}</tbody>
    </table>
  </div>

  <div class="footer">
    Generated by Weather Data Pipeline | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  </div>
</div>
</body>
</html>"""
        return self._save(html, f"daily_{date_str}.html")


# ═══════════════════════════════════════════════════════════
# PART 3: Analytics Report (answers the 5 analysis questions)
# ═══════════════════════════════════════════════════════════

class AnalyticsReporter(ReportBuilder):
    """
    Answers the 5 analysis questions from the project spec:
    1. Which city has the highest average temperature?
    2. What are the temperature trends over the last 30 days?
    3. How does humidity correlate with rainfall?
    4. Which seasons have the most extreme weather?
    5. What are the peak temperature hours?
    """

    def generate(self) -> str:
        """Generates the comprehensive analytics report."""
        logger.info("📈 Generating analytics report...")
        lines = []
        lines.append(self._header("WEATHER ANALYTICS REPORT — ALL CITIES"))

        # ── Question 1: Hottest City ─────────────────────────────
        lines.append(self._section("Q1: Which city has the highest average temperature?"))
        stats = self.db.get_temperature_stats(days=30)
        if stats:
            hottest = stats[0]
            lines.append(f"  🔥 HOTTEST : {hottest['city']}, {hottest['country']}")
            lines.append(f"     Avg Temp: {hottest['avg_temp']}°C")
            lines.append(f"     Max Temp: {hottest['max_temp']}°C")
            lines.append(f"     Min Temp: {hottest['min_temp']}°C")
            lines.append(f"\n  Full Ranking (last 30 days):")
            headers = ["Rank", "City", "Country", "Avg °C", "Max °C", "Min °C"]
            col_w   = [5, 15, 8, 8, 8, 8]
            rows = [
                [i+1, r["city"], r["country"],
                 r["avg_temp"], r["max_temp"], r["min_temp"]]
                for i, r in enumerate(stats)
            ]
            lines.append(self._table(headers, rows, col_w))
        else:
            lines.append("  No data available (run the pipeline first!)")

        # ── Question 2: Temperature Trends ───────────────────────
        lines.append(self._section("Q2: Temperature trends over the last 30 days"))
        cities_db = self.db.get_all_cities()
        for city in cities_db[:3]:   # Show first 3 cities
            trends = self.db.get_temperature_trends(city["id"], days=30)
            if trends:
                lines.append(f"\n  📍 {city['name']}, {city['country']}:")
                for t in trends[-7:]:  # Last 7 days
                    bar_len = max(0, int((float(t["avg_temp"]) + 20) / 3))
                    bar = "█" * bar_len
                    lines.append(
                        f"    {t['reading_date']}  {bar:<20}  {t['avg_temp']:>6}°C"
                        f"  (max: {t['max_temp']}  min: {t['min_temp']})"
                    )
            else:
                lines.append(f"\n  📍 {city['name']}: No trend data yet")

        # ── Question 3: Humidity vs Rain Correlation ─────────────
        lines.append(self._section("Q3: How does humidity correlate with rainfall?"))
        corr = self.db.get_humidity_rain_correlation()
        if corr:
            lines.append("  City             | Avg Humidity | Total Rain | Rainy Hours")
            lines.append("  " + "-"*65)
            for r in corr:
                lines.append(
                    f"  {r['city']:<16} | "
                    f"{r['avg_humidity']:>11}% | "
                    f"{r['total_rain']:>9} mm | "
                    f"{r['rainy_hours']:>11}"
                )
            lines.append("\n  INSIGHT: Higher humidity generally correlates with more rainfall.")
        else:
            lines.append("  No correlation data available yet.")

        # ── Question 4: Seasonal Extremes ────────────────────────
        lines.append(self._section("Q4: Which seasons have the most extreme weather?"))
        seasonal = self.db.get_seasonal_extremes()
        if seasonal:
            headers = ["City", "Season", "Avg °C", "Max °C", "Min °C", "Max Wind"]
            col_w   = [15, 8, 8, 8, 8, 10]
            rows = [
                [r["city"], r["season"],
                 r["avg_temp"], r["max_temp"], r["min_temp"], r["max_wind"]]
                for r in seasonal[:12]
            ]
            lines.append(self._table(headers, rows, col_w))
        else:
            lines.append("  No seasonal data available yet.")

        # ── Question 5: Peak Temperature Hours ──────────────────
        lines.append(self._section("Q5: What are the peak temperature hours?"))
        for city in cities_db[:3]:
            hours = self.db.get_peak_temperature_hours(city["id"])
            if hours:
                top3 = hours[:3]
                times = ", ".join([f"{h['hour_of_day']:02d}:00 ({h['avg_temp']}°C)"
                                   for h in top3])
                lines.append(f"  📍 {city['name']}: Hottest hours → {times}")
            else:
                lines.append(f"  📍 {city['name']}: No hourly data yet")

        content = "\n".join(lines) + "\n"
        return self._save(content, "analytics_report.txt")


# ═══════════════════════════════════════════════════════════
# PART 4: Report Manager (coordinates all reports)
# ═══════════════════════════════════════════════════════════

class ReportManager:
    """
    Coordinator that runs all reports and cleans up old ones.
    Called by the scheduler every day.
    """

    def __init__(self, db: DatabaseManager):
        self.db        = db
        self.daily     = DailyReporter(db)
        self.analytics = AnalyticsReporter(db)

    def run_all(self) -> Dict:
        """Generates all report types and returns file paths."""
        logger.info("\n📋 Running all reports...")
        results = {
            "daily":     self.daily.generate(),
            "analytics": self.analytics.generate(),
            "generated_at": datetime.now().isoformat(),
        }
        self._cleanup_old_reports()
        return results

    def _cleanup_old_reports(self):
        """Deletes reports older than KEEP_REPORTS_DAYS."""
        keep_days = REPORT_CONFIG.get("keep_reports_days", 90)
        cutoff    = datetime.now().timestamp() - (keep_days * 86400)
        deleted   = 0
        for f in REPORT_DIR.glob("*.txt"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        for f in REPORT_DIR.glob("*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        if deleted:
            logger.info(f"  🗑️  Cleaned up {deleted} old report files")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from database import setup_database

    print("\n" + "="*60)
    print("  REPORT GENERATION TEST")
    print("="*60)

    db = setup_database()
    manager = ReportManager(db)
    reports = manager.run_all()

    print("\n📂 Generated Files:")
    for report_type, paths in reports.items():
        if isinstance(paths, dict):
            for fmt, path in paths.items():
                print(f"   [{fmt.upper():4s}] {Path(path).name}")
        elif isinstance(paths, str):
            print(f"   [TXT ] {Path(paths).name}")
