"""
database.py - Database Connection & Operations
================================================
This file handles EVERYTHING related to databases.
We support BOTH SQLite (local) and PostgreSQL (cloud).

BEGINNER CONCEPTS:
- SQLite: A database stored as a single .db file (like a spreadsheet file)
- PostgreSQL: A full server database (like having a dedicated database computer)
- Tables: Like Excel sheets inside the database
- Rows: Individual records (one row = one weather reading)
- Columns: Fields of data (temperature, humidity, etc.)
- Foreign Key: Links between tables (like a city_id in weather_readings linking to cities table)
- Index: Makes searching faster (like a book's index)

DATABASE SCHEMA (3+ Normalized Tables):
┌─────────────┐     ┌──────────────────┐     ┌────────────────┐
│   cities    │────▶│ weather_readings  │     │  api_logs      │
│─────────────│     │──────────────────│     │────────────────│
│ id          │     │ id               │     │ id             │
│ name        │     │ city_id (FK)     │     │ city_id (FK)   │
│ country     │     │ temperature      │     │ timestamp      │
│ latitude    │     │ humidity         │     │ status_code    │
│ longitude   │     │ pressure         │     │ success        │
│ timezone    │     │ wind_speed       │     │ response_time  │
│ created_at  │     │ visibility       │     │ error_message  │
└─────────────┘     │ weather_desc     │     └────────────────┘
                    │ collected_at     │
                    └──────────────────┘
                           │
                    ┌──────────────────┐
                    │  daily_summaries │
                    │──────────────────│
                    │ id               │
                    │ city_id (FK)     │
                    │ date             │
                    │ avg_temp         │
                    │ max_temp         │
                    │ min_temp         │
                    │ avg_humidity     │
                    │ total_readings   │
                    └──────────────────┘
"""

import sqlite3
import logging
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from pathlib import Path

# Import our config settings
import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import SQLITE_DB_PATH, POSTGRES_CONFIG, ACTIVE_DB

# Set up logging for this module
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# PART 1: SQL STATEMENTS - All our database queries in one place
# ═══════════════════════════════════════════════════════════

# These are the CREATE TABLE statements
# They define the structure of each table
CREATE_TABLES_SQL = {

    # TABLE 1: cities
    # Stores information about each city we track
    "cities": """
        CREATE TABLE IF NOT EXISTS cities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            country     TEXT    NOT NULL,
            latitude    REAL,
            longitude   REAL,
            timezone    TEXT,
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(name, country)
        )
    """,

    # TABLE 2: weather_readings
    # One row = one weather snapshot for one city
    "weather_readings": """
        CREATE TABLE IF NOT EXISTS weather_readings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id         INTEGER NOT NULL,
            temperature     REAL,
            feels_like      REAL,
            temp_min        REAL,
            temp_max        REAL,
            humidity        INTEGER,
            pressure        INTEGER,
            wind_speed      REAL,
            wind_direction  INTEGER,
            wind_gust       REAL,
            visibility      INTEGER,
            cloudiness      INTEGER,
            weather_main    TEXT,
            weather_desc    TEXT,
            weather_icon    TEXT,
            rain_1h         REAL DEFAULT 0,
            snow_1h         REAL DEFAULT 0,
            uv_index        REAL,
            sunrise         TEXT,
            sunset          TEXT,
            data_quality    TEXT DEFAULT 'GOOD',
            collected_at    TEXT NOT NULL,
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
        )
    """,

    # TABLE 3: daily_summaries
    # Pre-computed daily stats (faster than calculating on-the-fly)
    "daily_summaries": """
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id         INTEGER NOT NULL,
            summary_date    TEXT    NOT NULL,
            avg_temp        REAL,
            max_temp        REAL,
            min_temp        REAL,
            avg_humidity    REAL,
            avg_pressure    REAL,
            avg_wind_speed  REAL,
            max_wind_speed  REAL,
            dominant_weather TEXT,
            total_rain      REAL DEFAULT 0,
            total_snow      REAL DEFAULT 0,
            total_readings  INTEGER DEFAULT 0,
            data_completeness REAL DEFAULT 100.0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE,
            UNIQUE(city_id, summary_date)
        )
    """,

    # TABLE 4: api_logs
    # Tracks every API call we make (for monitoring)
    "api_logs": """
        CREATE TABLE IF NOT EXISTS api_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id         INTEGER,
            endpoint        TEXT,
            status_code     INTEGER,
            success         INTEGER DEFAULT 1,
            response_time_ms INTEGER,
            error_message   TEXT,
            called_at       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (city_id) REFERENCES cities(id)
        )
    """,

    # TABLE 5: pipeline_runs
    # Tracks each time the ETL pipeline runs
    "pipeline_runs": """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT    UNIQUE NOT NULL,
            status          TEXT    DEFAULT 'RUNNING',
            cities_processed INTEGER DEFAULT 0,
            records_inserted INTEGER DEFAULT 0,
            records_failed  INTEGER DEFAULT 0,
            errors          TEXT,
            started_at      TEXT    DEFAULT (datetime('now')),
            completed_at    TEXT,
            duration_seconds REAL
        )
    """,

    # TABLE 6: weather_alerts
    # Stores alerts triggered by extreme weather
    "weather_alerts": """
        CREATE TABLE IF NOT EXISTS weather_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id         INTEGER NOT NULL,
            alert_type      TEXT    NOT NULL,
            severity        TEXT    DEFAULT 'INFO',
            message         TEXT,
            value           REAL,
            threshold       REAL,
            is_resolved     INTEGER DEFAULT 0,
            triggered_at    TEXT    DEFAULT (datetime('now')),
            resolved_at     TEXT,
            FOREIGN KEY (city_id) REFERENCES cities(id)
        )
    """,
}

# Index creation for faster queries
CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_readings_city_date ON weather_readings(city_id, collected_at)",
    "CREATE INDEX IF NOT EXISTS idx_readings_collected ON weather_readings(collected_at)",
    "CREATE INDEX IF NOT EXISTS idx_summaries_city_date ON daily_summaries(city_id, summary_date)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_city ON weather_alerts(city_id, triggered_at)",
    "CREATE INDEX IF NOT EXISTS idx_api_logs_city ON api_logs(city_id, called_at)",
]


# ═══════════════════════════════════════════════════════════
# PART 2: DatabaseManager Class
# ═══════════════════════════════════════════════════════════

class DatabaseManager:
    """
    DatabaseManager handles ALL database operations.

    BEGINNER TIP: A "class" is like a blueprint.
    When you write `db = DatabaseManager()`, you create
    one instance (object) from the blueprint.
    Then you call methods like `db.insert_reading(...)`.
    """

    def __init__(self, db_type: str = None):
        """
        Initialize the database manager.

        Args:
            db_type: "sqlite" or "postgresql" (defaults to config setting)
        """
        self.db_type = db_type or ACTIVE_DB
        self.db_path = SQLITE_DB_PATH   # Used only for SQLite
        logger.info(f"DatabaseManager initialized | Type: {self.db_type.upper()}")

    # ─────────────────────────────────────────────
    # CONNECTION MANAGEMENT
    # ─────────────────────────────────────────────

    @contextmanager
    def get_connection(self):
        """
        Context manager that gives you a database connection.

        BEGINNER TIP: The 'with' statement automatically
        closes the connection when done — even if an error occurs.
        This prevents "connection leaks".

        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM cities")
        """
        conn = None
        try:
            if self.db_type == "sqlite":
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row  # Makes rows act like dictionaries
                conn.execute("PRAGMA foreign_keys = ON")  # Enable FK constraints
                conn.execute("PRAGMA journal_mode = WAL")  # Better performance
            elif self.db_type == "postgresql":
                try:
                    import psycopg2
                    import psycopg2.extras
                    conn = psycopg2.connect(**POSTGRES_CONFIG)
                except ImportError:
                    raise ImportError("psycopg2 not installed. Run: pip install psycopg2-binary")
            else:
                raise ValueError(f"Unknown database type: {self.db_type}")

            yield conn
            conn.commit()  # Save all changes

        except Exception as e:
            if conn:
                conn.rollback()  # Undo changes if error occurred
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()  # Always close the connection

    # ─────────────────────────────────────────────
    # SETUP METHODS
    # ─────────────────────────────────────────────

    def initialize_database(self) -> bool:
        """
        Creates all tables and indexes if they don't exist.
        Safe to run multiple times — uses CREATE IF NOT EXISTS.

        Returns:
            True if successful, False if failed
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Create all tables
                logger.info("Creating database tables...")
                for table_name, sql in CREATE_TABLES_SQL.items():
                    # Adapt SQL for PostgreSQL if needed
                    adapted_sql = self._adapt_sql(sql)
                    cursor.execute(adapted_sql)
                    logger.debug(f"  ✓ Table '{table_name}' ready")

                # Create indexes for faster queries
                logger.info("Creating indexes...")
                for index_sql in CREATE_INDEXES_SQL:
                    try:
                        cursor.execute(self._adapt_sql(index_sql))
                    except Exception:
                        pass  # Index might already exist

            logger.info("✅ Database initialized successfully!")
            return True

        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return False

    def _adapt_sql(self, sql: str) -> str:
        """Converts SQLite SQL to PostgreSQL SQL if needed."""
        if self.db_type == "postgresql":
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            sql = sql.replace("datetime('now')", "NOW()")
            sql = sql.replace("TEXT DEFAULT", "VARCHAR DEFAULT")
        return sql

    def seed_cities(self, cities: List[Dict]) -> int:
        """
        Inserts the initial list of cities into the database.
        Uses INSERT OR IGNORE to avoid duplicates.

        Args:
            cities: List of city dicts from config.py

        Returns:
            Number of new cities inserted
        """
        inserted = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for city in cities:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO cities (name, country, timezone)
                        VALUES (?, ?, ?)
                    """, (city["name"], city["country"], city.get("timezone", "")))
                    if cursor.rowcount > 0:
                        inserted += 1
                        logger.debug(f"  Added city: {city['name']}, {city['country']}")
                except Exception as e:
                    logger.warning(f"Could not insert city {city['name']}: {e}")

        logger.info(f"✅ Cities seeded: {inserted} new cities added")
        return inserted

    # ─────────────────────────────────────────────
    # INSERT / WRITE METHODS
    # ─────────────────────────────────────────────

    def insert_weather_reading(self, city_id: int, data: Dict) -> Optional[int]:
        """
        Inserts one weather reading into weather_readings table.

        Args:
            city_id: The ID of the city (from cities table)
            data: Dict containing weather values

        Returns:
            The new row's ID, or None if failed
        """
        sql = """
            INSERT INTO weather_readings (
                city_id, temperature, feels_like, temp_min, temp_max,
                humidity, pressure, wind_speed, wind_direction, wind_gust,
                visibility, cloudiness, weather_main, weather_desc,
                weather_icon, rain_1h, snow_1h, uv_index,
                sunrise, sunset, data_quality, collected_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?
            )
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (
                    city_id,
                    data.get("temperature"),
                    data.get("feels_like"),
                    data.get("temp_min"),
                    data.get("temp_max"),
                    data.get("humidity"),
                    data.get("pressure"),
                    data.get("wind_speed"),
                    data.get("wind_direction"),
                    data.get("wind_gust"),
                    data.get("visibility"),
                    data.get("cloudiness"),
                    data.get("weather_main"),
                    data.get("weather_desc"),
                    data.get("weather_icon"),
                    data.get("rain_1h", 0),
                    data.get("snow_1h", 0),
                    data.get("uv_index"),
                    data.get("sunrise"),
                    data.get("sunset"),
                    data.get("data_quality", "GOOD"),
                    data.get("collected_at", datetime.now().isoformat()),
                ))
                row_id = cursor.lastrowid
                logger.debug(f"  Inserted reading ID={row_id} for city_id={city_id}")
                return row_id
        except Exception as e:
            logger.error(f"Failed to insert reading for city_id={city_id}: {e}")
            return None

    def insert_api_log(self, city_id: Optional[int], endpoint: str,
                       status_code: int, success: bool,
                       response_time_ms: int, error_message: str = None):
        """Logs every API call for monitoring and debugging."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO api_logs
                        (city_id, endpoint, status_code, success, response_time_ms, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (city_id, endpoint, status_code, int(success),
                      response_time_ms, error_message))
        except Exception as e:
            logger.error(f"Failed to log API call: {e}")

    def insert_alert(self, city_id: int, alert_type: str, severity: str,
                     message: str, value: float, threshold: float) -> Optional[int]:
        """Creates a weather alert record."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO weather_alerts
                        (city_id, alert_type, severity, message, value, threshold)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (city_id, alert_type, severity, message, value, threshold))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert alert: {e}")
            return None

    def log_pipeline_run(self, run_id: str, status: str,
                         cities_processed: int = 0, records_inserted: int = 0,
                         records_failed: int = 0, errors: List = None,
                         duration_seconds: float = None):
        """Records the result of each pipeline execution."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Check if run_id exists
                cursor.execute("SELECT id FROM pipeline_runs WHERE run_id = ?", (run_id,))
                existing = cursor.fetchone()

                if existing:
                    # Update existing run
                    cursor.execute("""
                        UPDATE pipeline_runs
                        SET status=?, cities_processed=?, records_inserted=?,
                            records_failed=?, errors=?, completed_at=datetime('now'),
                            duration_seconds=?
                        WHERE run_id=?
                    """, (status, cities_processed, records_inserted,
                          records_failed, json.dumps(errors or []),
                          duration_seconds, run_id))
                else:
                    # Insert new run
                    cursor.execute("""
                        INSERT INTO pipeline_runs
                            (run_id, status, cities_processed, records_inserted,
                             records_failed, errors, duration_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (run_id, status, cities_processed, records_inserted,
                          records_failed, json.dumps(errors or []), duration_seconds))
        except Exception as e:
            logger.error(f"Failed to log pipeline run: {e}")

    # ─────────────────────────────────────────────
    # QUERY / READ METHODS
    # ─────────────────────────────────────────────

    def get_all_cities(self) -> List[Dict]:
        """Returns all active cities from the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cities WHERE is_active = 1 ORDER BY name")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_city_by_name(self, name: str, country: str = None) -> Optional[Dict]:
        """Finds a city by name (and optionally country)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if country:
                cursor.execute(
                    "SELECT * FROM cities WHERE LOWER(name) = LOWER(?) AND country = ?",
                    (name, country)
                )
            else:
                cursor.execute(
                    "SELECT * FROM cities WHERE LOWER(name) = LOWER(?)", (name,)
                )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_latest_readings(self, limit: int = 10) -> List[Dict]:
        """Gets the most recent weather readings across all cities."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    wr.*,
                    c.name AS city_name,
                    c.country
                FROM weather_readings wr
                JOIN cities c ON c.id = wr.city_id
                ORDER BY wr.collected_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_city_readings(self, city_id: int, days: int = 7,
                          limit: int = 500) -> List[Dict]:
        """Gets weather readings for a specific city over the past N days."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM weather_readings
                WHERE city_id = ?
                  AND collected_at >= datetime('now', ? || ' days')
                ORDER BY collected_at DESC
                LIMIT ?
            """, (city_id, f"-{days}", limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_temperature_stats(self, days: int = 30) -> List[Dict]:
        """
        ANALYSIS QUERY: Average temperature per city.
        Answers: "Which city has the highest average temperature?"
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    c.name                      AS city,
                    c.country,
                    ROUND(AVG(wr.temperature), 2) AS avg_temp,
                    ROUND(MAX(wr.temperature), 2) AS max_temp,
                    ROUND(MIN(wr.temperature), 2) AS min_temp,
                    COUNT(*)                    AS total_readings
                FROM weather_readings wr
                JOIN cities c ON c.id = wr.city_id
                WHERE wr.collected_at >= datetime('now', ? || ' days')
                  AND wr.data_quality = 'GOOD'
                GROUP BY c.id, c.name, c.country
                ORDER BY avg_temp DESC
            """, (f"-{days}",))
            return [dict(row) for row in cursor.fetchall()]

    def get_temperature_trends(self, city_id: int, days: int = 30) -> List[Dict]:
        """
        ANALYSIS QUERY: Daily average temperature trends.
        Answers: "What are the temperature trends over the last 30 days?"
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    DATE(collected_at)            AS reading_date,
                    ROUND(AVG(temperature), 2)    AS avg_temp,
                    ROUND(MAX(temperature), 2)    AS max_temp,
                    ROUND(MIN(temperature), 2)    AS min_temp,
                    ROUND(AVG(humidity), 1)       AS avg_humidity,
                    COUNT(*)                      AS num_readings
                FROM weather_readings
                WHERE city_id = ?
                  AND collected_at >= datetime('now', ? || ' days')
                GROUP BY DATE(collected_at)
                ORDER BY reading_date ASC
            """, (city_id, f"-{days}"))
            return [dict(row) for row in cursor.fetchall()]

    def get_humidity_rain_correlation(self) -> List[Dict]:
        """
        ANALYSIS QUERY: Humidity vs Rainfall correlation.
        Answers: "How does humidity correlate with rainfall?"
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    c.name                          AS city,
                    ROUND(AVG(wr.humidity), 1)       AS avg_humidity,
                    ROUND(SUM(wr.rain_1h), 2)        AS total_rain,
                    ROUND(AVG(wr.rain_1h), 3)        AS avg_rain_per_hour,
                    COUNT(CASE WHEN wr.rain_1h > 0 THEN 1 END) AS rainy_hours
                FROM weather_readings wr
                JOIN cities c ON c.id = wr.city_id
                GROUP BY c.id, c.name
                ORDER BY avg_humidity DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_seasonal_extremes(self) -> List[Dict]:
        """
        ANALYSIS QUERY: Seasonal weather extremes.
        Answers: "Which seasons have the most extreme weather?"
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    c.name                         AS city,
                    CASE
                        WHEN CAST(strftime('%m', collected_at) AS INTEGER)
                             IN (12,1,2)  THEN 'Winter'
                        WHEN CAST(strftime('%m', collected_at) AS INTEGER)
                             IN (3,4,5)   THEN 'Spring'
                        WHEN CAST(strftime('%m', collected_at) AS INTEGER)
                             IN (6,7,8)   THEN 'Summer'
                        ELSE 'Autumn'
                    END                            AS season,
                    ROUND(AVG(temperature), 2)     AS avg_temp,
                    ROUND(MAX(temperature), 2)     AS max_temp,
                    ROUND(MIN(temperature), 2)     AS min_temp,
                    ROUND(MAX(wind_speed), 2)      AS max_wind,
                    COUNT(*)                       AS readings
                FROM weather_readings wr
                JOIN cities c ON c.id = wr.city_id
                GROUP BY c.id, c.name, season
                ORDER BY c.name, season
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_peak_temperature_hours(self, city_id: int) -> List[Dict]:
        """
        ANALYSIS QUERY: Hottest hours of the day.
        Answers: "What are the peak temperature hours for each city?"
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    CAST(strftime('%H', collected_at) AS INTEGER) AS hour_of_day,
                    ROUND(AVG(temperature), 2)                    AS avg_temp,
                    ROUND(MAX(temperature), 2)                    AS max_temp,
                    COUNT(*)                                      AS readings
                FROM weather_readings
                WHERE city_id = ?
                GROUP BY hour_of_day
                ORDER BY avg_temp DESC
            """, (city_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_pipeline_stats(self, limit: int = 10) -> List[Dict]:
        """Returns recent pipeline execution stats for monitoring."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_active_alerts(self) -> List[Dict]:
        """Returns all unresolved weather alerts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT wa.*, c.name AS city_name
                FROM weather_alerts wa
                JOIN cities c ON c.id = wa.city_id
                WHERE wa.is_resolved = 0
                ORDER BY wa.triggered_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_api_error_rate(self, hours: int = 24) -> float:
        """Returns the API error rate for the past N hours."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failures
                FROM api_logs
                WHERE called_at >= datetime('now', ? || ' hours')
            """, (f"-{hours}",))
            row = dict(cursor.fetchone())
            if row["total"] == 0:
                return 0.0
            return round(row["failures"] / row["total"], 4)

    def get_record_count(self, table: str) -> int:
        """Returns total row count for a table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            return cursor.fetchone()[0]

    def health_check(self) -> Dict:
        """
        Tests if the database is working correctly.
        Returns a dict with status and stats.
        """
        import time
        start = time.time()
        try:
            counts = {}
            for table in ["cities", "weather_readings", "daily_summaries",
                          "api_logs", "weather_alerts", "pipeline_runs"]:
                counts[table] = self.get_record_count(table)

            elapsed_ms = round((time.time() - start) * 1000, 2)
            return {
                "status":       "HEALTHY",
                "db_type":      self.db_type,
                "response_ms":  elapsed_ms,
                "table_counts": counts,
            }
        except Exception as e:
            elapsed_ms = round((time.time() - start) * 1000, 2)
            return {
                "status":       "UNHEALTHY",
                "db_type":      self.db_type,
                "response_ms":  elapsed_ms,
                "error":        str(e),
            }


# ═══════════════════════════════════════════════════════════
# PART 3: Quick Setup Function (called by main.py)
# ═══════════════════════════════════════════════════════════

def setup_database(cities: List[Dict] = None) -> DatabaseManager:
    """
    One-call setup: creates all tables and seeds cities.

    Args:
        cities: List of city dicts to pre-load

    Returns:
        A ready-to-use DatabaseManager instance
    """
    from config import CITIES
    db = DatabaseManager()
    db.initialize_database()
    db.seed_cities(cities or CITIES)
    return db


if __name__ == "__main__":
    # DEMO: Run this file directly to test the database
    import logging
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*50)
    print("  DATABASE SETUP & HEALTH CHECK")
    print("="*50)

    db = setup_database()
    health = db.health_check()

    print(f"\n📊 Database Status: {health['status']}")
    print(f"   Response Time : {health['response_ms']} ms")
    print(f"   Table Counts  :")
    for table, count in health.get("table_counts", {}).items():
        print(f"     {table:25s}: {count} rows")
