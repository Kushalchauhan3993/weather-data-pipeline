"""
tests/test_pipeline.py — Unit & Integration Tests
===================================================
BEGINNER CONCEPT — TESTING:
Tests verify that your code works correctly.
Think of them as "automated checkups" for your code.

WHY WRITE TESTS?
- Catch bugs early (before they go to production)
- Know when your changes break something
- Document what your code is supposed to do
- Build confidence to refactor code

HOW TO RUN:
    pytest tests/ -v              # Run all tests
    pytest tests/ -v --cov=src    # Run with coverage report
    pytest tests/test_pipeline.py::TestValidator -v  # Run one class

TEST TYPES:
- Unit Test    : Tests one small function in isolation
- Integration  : Tests multiple pieces working together
- End-to-End   : Tests the full pipeline from API to database
"""

import sys
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ═══════════════════════════════════════════════════════════
# TEST FIXTURES (shared setup objects)
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def temp_db():
    """
    Creates a temporary in-memory database for each test.
    This ensures tests don't affect each other.
    The 'yield' gives the test the db object.
    After the test, everything after yield runs as cleanup.
    """
    # Temporarily override the db path to use a temp file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name

    from config import CITIES
    import config
    original_path = config.SQLITE_DB_PATH
    config.SQLITE_DB_PATH = temp_path  # Point to temp file

    from database import DatabaseManager
    db = DatabaseManager(db_type="sqlite")
    db.db_path = temp_path
    db.initialize_database()
    db.seed_cities(CITIES[:3])  # Only 3 cities for speed

    yield db  # Give the test its database

    # Cleanup after test
    config.SQLITE_DB_PATH = original_path
    try:
        os.unlink(temp_path)
    except Exception:
        pass


@pytest.fixture
def sample_weather_data():
    """Provides a valid weather reading for use in multiple tests."""
    return {
        "temperature":      22.5,
        "feels_like":       23.0,
        "temp_min":         18.0,
        "temp_max":         26.0,
        "humidity":         65,
        "pressure":         1013,
        "wind_speed":       5.2,
        "wind_direction":   180,
        "wind_gust":        8.0,
        "visibility":       8000,
        "cloudiness":       40,
        "weather_main":     "Clouds",
        "weather_desc":     "scattered clouds",
        "weather_icon":     "03d",
        "rain_1h":          0.0,
        "snow_1h":          0.0,
        "uv_index":         4.5,
        "sunrise":          "2024-01-15T06:30:00",
        "sunset":           "2024-01-15T18:45:00",
        "data_quality":     "GOOD",
        "collected_at":     datetime.now().isoformat(),
        "data_source":      "demo",
    }


# ═══════════════════════════════════════════════════════════
# TEST 1: Database Tests
# ═══════════════════════════════════════════════════════════

class TestDatabase:
    """Tests for database.py"""

    def test_database_initializes(self, temp_db):
        """Test that all tables are created on initialization."""
        health = temp_db.health_check()
        assert health["status"] == "HEALTHY"
        assert "cities" in health["table_counts"]
        assert "weather_readings" in health["table_counts"]
        assert "daily_summaries" in health["table_counts"]

    def test_cities_seeded(self, temp_db):
        """Test that cities are correctly inserted."""
        cities = temp_db.get_all_cities()
        assert len(cities) == 3  # We seeded 3 cities in fixture
        assert all("name" in c for c in cities)
        assert all("country" in c for c in cities)

    def test_insert_weather_reading(self, temp_db, sample_weather_data):
        """Test that a weather reading can be inserted."""
        cities  = temp_db.get_all_cities()
        city_id = cities[0]["id"]

        row_id = temp_db.insert_weather_reading(city_id, sample_weather_data)
        assert row_id is not None
        assert row_id > 0

    def test_get_latest_readings(self, temp_db, sample_weather_data):
        """Test that we can retrieve inserted readings."""
        cities  = temp_db.get_all_cities()
        city_id = cities[0]["id"]
        temp_db.insert_weather_reading(city_id, sample_weather_data)

        readings = temp_db.get_latest_readings(limit=5)
        assert len(readings) >= 1
        assert "temperature" in readings[0]
        assert "city_name" in readings[0]

    def test_temperature_stats_query(self, temp_db, sample_weather_data):
        """Test the temperature stats analytics query."""
        cities  = temp_db.get_all_cities()
        city_id = cities[0]["id"]

        # Insert a few readings
        for _ in range(3):
            temp_db.insert_weather_reading(city_id, sample_weather_data)

        stats = temp_db.get_temperature_stats(days=1)
        assert len(stats) >= 1
        assert "avg_temp" in stats[0]
        assert "max_temp" in stats[0]
        assert "min_temp" in stats[0]

    def test_api_log_insert(self, temp_db):
        """Test that API call logs are saved."""
        temp_db.insert_api_log(
            city_id         = 1,
            endpoint        = "current_weather",
            status_code     = 200,
            success         = True,
            response_time_ms = 150,
        )
        error_rate = temp_db.get_api_error_rate(hours=24)
        assert 0.0 <= error_rate <= 1.0

    def test_health_check_returns_dict(self, temp_db):
        """Test that health check returns expected structure."""
        health = temp_db.health_check()
        assert isinstance(health, dict)
        assert "status" in health
        assert "response_ms" in health
        assert health["status"] in ["HEALTHY", "UNHEALTHY"]

    def test_get_city_by_name(self, temp_db):
        """Test city lookup by name."""
        cities = temp_db.get_all_cities()
        first_city = cities[0]
        found = temp_db.get_city_by_name(first_city["name"])
        assert found is not None
        assert found["name"] == first_city["name"]

    def test_missing_city_returns_none(self, temp_db):
        """Test that looking up a non-existent city returns None."""
        result = temp_db.get_city_by_name("Atlantis", "XX")
        assert result is None


# ═══════════════════════════════════════════════════════════
# TEST 2: Validator Tests
# ═══════════════════════════════════════════════════════════

class TestValidator:
    """Tests for validators.py"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from validators import WeatherValidator, DataCleaner
        self.validator = WeatherValidator()
        self.cleaner   = DataCleaner()

    def test_valid_data_passes(self, sample_weather_data):
        """Valid data should pass with GOOD quality."""
        result = self.validator.validate(sample_weather_data, "TestCity")
        assert result.is_valid
        assert result.quality == "GOOD"
        assert len(result.errors) == 0

    def test_extreme_temperature_fails(self, sample_weather_data):
        """Temperature of 200°C should fail validation."""
        bad_data = dict(sample_weather_data)
        bad_data["temperature"] = 200.0
        result = self.validator.validate(bad_data, "TestCity")
        assert not result.is_valid
        assert result.quality in ["BAD", "REJECTED"]
        assert len(result.errors) > 0

    def test_negative_temperature_extremes(self, sample_weather_data):
        """Temperature of -200°C should fail validation."""
        bad_data = dict(sample_weather_data)
        bad_data["temperature"] = -200.0
        result = self.validator.validate(bad_data, "TestCity")
        assert not result.is_valid

    def test_invalid_humidity(self, sample_weather_data):
        """Humidity > 100 is impossible — should fail."""
        bad_data = dict(sample_weather_data)
        bad_data["humidity"] = 150
        result = self.validator.validate(bad_data, "TestCity")
        assert not result.is_valid

    def test_negative_humidity(self, sample_weather_data):
        """Negative humidity is impossible — should fail."""
        bad_data = dict(sample_weather_data)
        bad_data["humidity"] = -10
        result = self.validator.validate(bad_data, "TestCity")
        assert not result.is_valid

    def test_extreme_heat_triggers_alert(self, sample_weather_data):
        """Temperature of 45°C should trigger an alert."""
        hot_data = dict(sample_weather_data)
        hot_data["temperature"] = 45.0
        result = self.validator.validate(hot_data, "Dubai")
        assert len(result.alerts) > 0
        alert_types = [a["type"] for a in result.alerts]
        assert "EXTREME_HEAT" in alert_types

    def test_high_wind_triggers_alert(self, sample_weather_data):
        """Wind speed of 25 m/s should trigger a wind alert."""
        windy_data = dict(sample_weather_data)
        windy_data["wind_speed"] = 25.0
        result = self.validator.validate(windy_data, "TestCity")
        alert_types = [a["type"] for a in result.alerts]
        assert "HIGH_WIND" in alert_types

    def test_missing_critical_field_rejected(self):
        """Data without temperature and collected_at should be rejected."""
        bad_data = {"humidity": 60, "pressure": 1010}
        result = self.validator.validate(bad_data, "TestCity")
        assert not result.is_valid
        assert result.quality == "REJECTED"

    def test_empty_data_rejected(self):
        """None/empty data should be rejected."""
        result = self.validator.validate(None, "TestCity")
        assert not result.is_valid
        assert result.quality == "REJECTED"

    def test_validator_tracks_statistics(self, sample_weather_data):
        """Validator should count how many records it has checked."""
        self.validator.reset_statistics()
        self.validator.validate(sample_weather_data, "City1")
        self.validator.validate(sample_weather_data, "City2")
        stats = self.validator.get_statistics()
        assert stats["total_validated"] == 2

    def test_cleaner_caps_visibility(self, sample_weather_data):
        """DataCleaner should cap visibility at 10,000m."""
        data = dict(sample_weather_data)
        data["visibility"] = 99999  # Way too high
        cleaned = self.cleaner.clean(data)
        assert cleaned["visibility"] == 10000

    def test_cleaner_defaults_rain(self, sample_weather_data):
        """DataCleaner should default rain_1h to 0 if missing."""
        data = dict(sample_weather_data)
        del data["rain_1h"]
        cleaned = self.cleaner.clean(data)
        assert cleaned["rain_1h"] == 0.0


# ═══════════════════════════════════════════════════════════
# TEST 3: API Client Tests
# ═══════════════════════════════════════════════════════════

class TestAPIClient:
    """Tests for api_client.py"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from api_client import WeatherAPIClient
        # Force demo mode (no real API calls in tests)
        import config
        config.ETL_CONFIG["enable_demo_mode"] = True
        self.client = WeatherAPIClient(api_key="demo_key")

    def test_demo_mode_enabled(self):
        """Client should be in demo mode with demo_key."""
        assert self.client.is_demo_mode

    def test_fetch_returns_data(self):
        """Demo mode should return valid weather data."""
        data = self.client.fetch_weather_for_city("London", "GB")
        assert data is not None
        assert "temperature" in data
        assert "humidity" in data
        assert "collected_at" in data

    def test_fetch_temperature_range(self):
        """Returned temperature should be within a reasonable range."""
        data = self.client.fetch_weather_for_city("Dubai", "AE")
        assert data is not None
        temp = data["temperature"]
        assert -90 <= temp <= 70

    def test_fetch_humidity_range(self):
        """Returned humidity should be 0-100%."""
        data = self.client.fetch_weather_for_city("Mumbai", "IN")
        assert data is not None
        assert 0 <= data["humidity"] <= 100

    def test_demo_data_for_known_city(self):
        """Demo data for London should be colder on average than Dubai."""
        london_data = self.client.fetch_weather_for_city("London", "GB")
        dubai_data  = self.client.fetch_weather_for_city("Dubai", "AE")

        # Run 10 times to get statistical significance
        london_temps = []
        dubai_temps  = []
        for _ in range(10):
            london_temps.append(
                self.client.fetch_weather_for_city("London", "GB")["temperature"]
            )
            dubai_temps.append(
                self.client.fetch_weather_for_city("Dubai", "AE")["temperature"]
            )

        avg_london = sum(london_temps) / len(london_temps)
        avg_dubai  = sum(dubai_temps) / len(dubai_temps)

        # Dubai should average warmer than London
        assert avg_dubai > avg_london


# ═══════════════════════════════════════════════════════════
# TEST 4: ETL Pipeline Integration Tests
# ═══════════════════════════════════════════════════════════

class TestETLPipeline:
    """Integration tests for the full ETL pipeline."""

    def test_full_pipeline_run(self, temp_db):
        """Test a full pipeline run with demo data."""
        from etl_pipeline import ETLPipeline
        from config import CITIES

        pipeline = ETLPipeline(db=temp_db)
        summary  = pipeline.run(cities=CITIES[:2], parallel=False)

        assert summary["status"] in ["SUCCESS", "PARTIAL"]
        assert summary["cities_succeeded"] > 0
        assert summary["duration_seconds"] > 0

    def test_pipeline_records_inserted(self, temp_db):
        """Pipeline should insert records into the database."""
        from etl_pipeline import ETLPipeline
        from config import CITIES

        initial_count = temp_db.get_record_count("weather_readings")
        pipeline = ETLPipeline(db=temp_db)
        pipeline.run(cities=CITIES[:2], parallel=False)

        new_count = temp_db.get_record_count("weather_readings")
        assert new_count > initial_count

    def test_backfill_creates_data(self, temp_db):
        """Backfill should create historical records."""
        from etl_pipeline import ETLPipeline
        from config import CITIES

        pipeline = ETLPipeline(db=temp_db)
        result   = pipeline.run_backfill(num_readings=10,
                                          cities=CITIES[:2])

        assert result["total_inserted"] > 0
        assert temp_db.get_record_count("weather_readings") >= 10

    def test_pipeline_logs_run(self, temp_db):
        """Pipeline should log its execution to pipeline_runs table."""
        from etl_pipeline import ETLPipeline
        from config import CITIES

        pipeline = ETLPipeline(db=temp_db)
        summary  = pipeline.run(cities=CITIES[:1], parallel=False)

        runs = temp_db.get_pipeline_stats(limit=5)
        assert len(runs) >= 1
        assert runs[0]["run_id"] == summary["run_id"]


# ═══════════════════════════════════════════════════════════
# TEST 5: Monitor Tests
# ═══════════════════════════════════════════════════════════

class TestMonitor:
    """Tests for monitor.py"""

    def test_health_check_returns_status(self, temp_db):
        """Health check should return a valid status."""
        from monitor import PipelineMonitor
        monitor = PipelineMonitor(db=temp_db)
        health  = monitor.full_health_check()

        assert "overall_status" in health
        assert health["overall_status"] in ["HEALTHY", "DEGRADED", "UNHEALTHY"]
        assert "checks" in health
        assert "database" in health["checks"]

    def test_metrics_summary_keys(self, temp_db):
        """Metrics summary should have all expected keys."""
        from monitor import PipelineMonitor
        monitor = PipelineMonitor(db=temp_db)
        metrics = monitor.get_metrics_summary()

        expected_keys = ["status", "total_readings", "total_cities",
                         "total_alerts", "checked_at"]
        for key in expected_keys:
            assert key in metrics, f"Missing key: {key}"


# ═══════════════════════════════════════════════════════════
# RUN TESTS IF EXECUTED DIRECTLY
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Run tests with: pytest tests/ -v")
    print("Or with coverage: pytest tests/ -v --cov=src --cov-report=term-missing")
