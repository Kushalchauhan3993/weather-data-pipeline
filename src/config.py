"""
config.py - Configuration Settings
====================================
This is the CENTRAL HUB for all project settings.
Think of it like the control panel of an airplane.
All other files import settings from here.

BEGINNER TIP:
- Never hardcode passwords or API keys in other files
- Always use this config file to change settings
- The .env file keeps your secrets safe
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# STEP 1: Load environment variables from .env file
# ─────────────────────────────────────────────
# The .env file stores sensitive data like API keys
# It's like a secret drawer that only your program can open
load_dotenv()

# ─────────────────────────────────────────────
# STEP 2: Define all file paths
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent   # Root folder of the project
LOG_DIR  = BASE_DIR / "logs"              # Where log files are saved
REPORT_DIR = BASE_DIR / "reports"         # Where reports are saved
DB_DIR   = BASE_DIR / "database"          # Where database files live

# Create directories if they don't exist
LOG_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)
DB_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# STEP 3: API Configuration
# ─────────────────────────────────────────────
# OpenWeatherMap gives you a FREE API key after registration at:
# https://openweathermap.org/api
API_KEY         = os.getenv("OPENWEATHER_API_KEY", "demo_key")
BASE_URL        = "https://api.openweathermap.org/data/2.5"
GEOCODING_URL   = "https://api.openweathermap.org/geo/1.0"

# API rate limits (free tier allows 60 calls/minute)
API_RATE_LIMIT      = 60       # max calls per minute
API_TIMEOUT         = 30       # seconds to wait for response
API_RETRY_ATTEMPTS  = 3        # how many times to retry on failure
API_RETRY_DELAY     = 5        # seconds between retries

# ─────────────────────────────────────────────
# STEP 4: Cities to track (Enterprise: Multiple Cities)
# ─────────────────────────────────────────────
# Each city has: name, country code, and timezone
CITIES = [
    {"name": "London",    "country": "GB", "timezone": "Europe/London"},
    {"name": "New York",  "country": "US", "timezone": "America/New_York"},
    {"name": "Tokyo",     "country": "JP", "timezone": "Asia/Tokyo"},
    {"name": "Sydney",    "country": "AU", "timezone": "Australia/Sydney"},
    {"name": "Mumbai",    "country": "IN", "timezone": "Asia/Kolkata"},
    {"name": "Dubai",     "country": "AE", "timezone": "Asia/Dubai"},
    {"name": "Paris",     "country": "FR", "timezone": "Europe/Paris"},
    {"name": "New Delhi", "country": "IN", "timezone": "Asia/Kolkata"},
]

# ─────────────────────────────────────────────
# STEP 5: Database Configuration
# ─────────────────────────────────────────────
# SQLite = local file database (great for learning & small projects)
SQLITE_DB_PATH = str(DB_DIR / "weather_data.db")

# PostgreSQL = professional cloud database (Enterprise Option 4)
POSTGRES_CONFIG = {
    "host":     os.getenv("PG_HOST", "localhost"),
    "port":     int(os.getenv("PG_PORT", "5432")),
    "database": os.getenv("PG_DATABASE", "weather_db"),
    "user":     os.getenv("PG_USER", "weather_user"),
    "password": os.getenv("PG_PASSWORD", ""),
}

# Which database to USE (sqlite or postgresql)
ACTIVE_DB = os.getenv("ACTIVE_DB", "sqlite")  # Change to "postgresql" for cloud

# ─────────────────────────────────────────────
# STEP 6: ETL Pipeline Settings
# ─────────────────────────────────────────────
# ETL = Extract, Transform, Load
# These settings control HOW data flows through the pipeline
ETL_CONFIG = {
    "batch_size":           10,      # Process 10 cities at a time
    "collection_interval":  30,      # Collect data every 30 minutes
    "data_retention_days":  365,     # Keep data for 1 year
    "max_workers":          4,       # Run 4 parallel tasks
    "enable_demo_mode":     True,    # Use fake data when no API key
}

# ─────────────────────────────────────────────
# STEP 7: Data Quality Thresholds
# ─────────────────────────────────────────────
# These are the "rules" for valid weather data
VALIDATION_RULES = {
    "temperature": {
        "min": -90.0,   # °C — coldest ever recorded: -89.2°C
        "max": 60.0,    # °C — hottest ever recorded: 56.7°C
    },
    "humidity": {
        "min": 0,       # % — dry
        "max": 100,     # % — completely saturated
    },
    "pressure": {
        "min": 870,     # hPa — extreme low
        "max": 1085,    # hPa — extreme high
    },
    "wind_speed": {
        "min": 0,       # m/s — calm
        "max": 113,     # m/s — fastest gust ever recorded
    },
    "visibility": {
        "min": 0,       # meters — complete fog
        "max": 10000,   # meters — maximum reportable
    },
}

# ─────────────────────────────────────────────
# STEP 8: Alert Thresholds (Triggers Notifications)
# ─────────────────────────────────────────────
ALERT_THRESHOLDS = {
    "extreme_heat":     40.0,   # °C — trigger heat alert
    "extreme_cold":    -20.0,   # °C — trigger cold alert
    "high_wind":        20.0,   # m/s — trigger wind alert
    "low_visibility":  1000,    # meters — trigger fog alert
    "heavy_rain":       50.0,   # mm/hour — trigger rain alert
}

# ─────────────────────────────────────────────
# STEP 9: Reporting Configuration
# ─────────────────────────────────────────────
REPORT_CONFIG = {
    "daily_report_hour":    8,      # Generate report at 8 AM
    "weekly_report_day":    0,      # Monday = 0, Sunday = 6
    "output_formats":       ["txt", "json", "html"],  # Report file types
    "keep_reports_days":    90,     # Delete old reports after 90 days
}

# ─────────────────────────────────────────────
# STEP 10: Logging Configuration
# ─────────────────────────────────────────────
LOGGING_CONFIG = {
    "level":        "INFO",                         # Log INFO and above
    "format":       "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    "date_format":  "%Y-%m-%d %H:%M:%S",
    "log_file":     str(LOG_DIR / "pipeline.log"),
    "error_file":   str(LOG_DIR / "errors.log"),
    "max_bytes":    10 * 1024 * 1024,              # 10 MB per log file
    "backup_count": 5,                              # Keep 5 old log files
}

# ─────────────────────────────────────────────
# STEP 11: Email Alerts (Optional)
# ─────────────────────────────────────────────
EMAIL_CONFIG = {
    "enabled":          False,   # Set to True to enable email alerts
    "smtp_host":        os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port":        int(os.getenv("SMTP_PORT", "587")),
    "sender":           os.getenv("EMAIL_SENDER", ""),
    "password":         os.getenv("EMAIL_PASSWORD", ""),
    "recipients":       os.getenv("EMAIL_RECIPIENTS", "").split(","),
}

# ─────────────────────────────────────────────
# STEP 12: Monitoring Settings
# ─────────────────────────────────────────────
MONITOR_CONFIG = {
    "health_check_interval":    60,     # Check every 60 seconds
    "max_api_error_rate":       0.10,   # Alert if >10% of API calls fail
    "max_db_response_ms":       1000,   # Alert if DB takes >1 second
    "pipeline_timeout_minutes": 15,     # Alert if pipeline runs >15 min
    "disk_usage_warning_pct":   80,     # Alert if disk >80% full
}

print("✅ Configuration loaded successfully!")
print(f"   Active Database : {ACTIVE_DB.upper()}")
print(f"   Tracking Cities : {len(CITIES)} cities")
print(f"   Demo Mode       : {ETL_CONFIG['enable_demo_mode']}")
print(f"   Log Directory   : {LOG_DIR}")
