# Database Directory
This folder contains the SQLite database file.

Files here:
- weather_data.db — SQLite database with all weather records

The database is auto-created when you run:
    python main.py setup

It is excluded from Git because it contains collected data
and grows large over time. Each user generates their own.

## Schema Overview
- cities            — 9 cities tracked
- weather_readings  — one row per weather snapshot
- daily_summaries   — pre-computed daily statistics
- api_logs          — every API call recorded
- pipeline_runs     — every ETL execution recorded
- weather_alerts    — extreme weather alerts
