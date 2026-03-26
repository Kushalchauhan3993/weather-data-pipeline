"""
etl_pipeline.py - Main ETL Pipeline
======================================
ETL = Extract → Transform → Load

This is the CORE ENGINE of the entire project.
It orchestrates all other modules together.

PIPELINE FLOW:
┌─────────────────────────────────────────────────────────────┐
│                     ETL PIPELINE RUN                        │
│                                                             │
│  EXTRACT          TRANSFORM           LOAD                  │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────┐       │
│  │ API Call │───▶│  Clean Data │───▶│  Insert into │       │
│  │ per city │    │  Validate   │    │  Database    │       │
│  └──────────┘    │  Add alerts │    └──────────────┘       │
│       ×N cities  └─────────────┘           ↓               │
│                                    ┌──────────────┐        │
│                                    │ Log pipeline │        │
│                                    │ run result   │        │
│                                    └──────────────┘        │
└─────────────────────────────────────────────────────────────┘

ERROR HANDLING STRATEGY:
- Each city is processed independently
- If one city fails, others continue
- All errors are logged with full details
- Pipeline status is always recorded
"""

import uuid
import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import CITIES, ETL_CONFIG
from database import DatabaseManager
from api_client import WeatherAPIClient
from validators import WeatherValidator, DataCleaner

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# PART 1: Individual Processing Functions
# ═══════════════════════════════════════════════════════════

def extract(client: WeatherAPIClient, city: Dict) -> Optional[Dict]:
    """
    EXTRACT PHASE: Fetch raw weather data from the API.

    Args:
        client : WeatherAPIClient instance
        city   : Dict with 'name', 'country', optionally 'lat', 'lon'

    Returns:
        Raw weather dict from API, or None on failure
    """
    city_name = city.get("name", "Unknown")
    country   = city.get("country", "")
    lat       = city.get("latitude")
    lon       = city.get("longitude")

    try:
        raw_data = client.fetch_weather_for_city(city_name, country, lat, lon)
        return raw_data
    except Exception as e:
        logger.error(f"[EXTRACT] Failed for {city_name}: {e}")
        return None


def transform(raw_data: Dict, city_name: str,
              cleaner: DataCleaner,
              validator: WeatherValidator) -> Tuple[Optional[Dict], object]:
    """
    TRANSFORM PHASE: Clean and validate the raw data.

    Steps:
    1. Clean: Fix formatting, defaults, rounding
    2. Validate: Check all values are physically reasonable
    3. Return cleaned data + validation result

    Args:
        raw_data  : Output from extract()
        city_name : For logging
        cleaner   : DataCleaner instance
        validator : WeatherValidator instance

    Returns:
        Tuple of (cleaned_data_or_None, ValidationResult)
    """
    if not raw_data:
        return None, None

    try:
        # Step 1: Clean
        cleaned = cleaner.clean(raw_data)

        # Step 2: Validate
        validation = validator.validate(cleaned, city_name)

        # Step 3: Attach quality flag to the data
        cleaned["data_quality"] = validation.quality

        # Don't load REJECTED data
        if validation.quality == "REJECTED":
            logger.warning(f"[TRANSFORM] {city_name}: Data REJECTED — not loading")
            return None, validation

        return cleaned, validation

    except Exception as e:
        logger.error(f"[TRANSFORM] Failed for {city_name}: {e}")
        return None, None


def load(db: DatabaseManager, city_id: int, cleaned_data: Dict,
         validation_result, city_name: str) -> bool:
    """
    LOAD PHASE: Insert the clean data into the database.

    Also:
    - Logs API call result
    - Creates weather alerts if needed
    - Returns success/failure boolean

    Args:
        db              : DatabaseManager instance
        city_id         : ID of the city in the cities table
        cleaned_data    : Output from transform()
        validation_result: The ValidationResult object
        city_name       : For logging

    Returns:
        True if successfully inserted, False otherwise
    """
    try:
        # Insert the weather reading
        row_id = db.insert_weather_reading(city_id, cleaned_data)

        if not row_id:
            logger.error(f"[LOAD] Failed to insert reading for {city_name}")
            return False

        logger.info(f"[LOAD] ✅ {city_name} → Row ID {row_id}")

        # Insert any weather alerts that were triggered
        if validation_result and validation_result.alerts:
            for alert in validation_result.alerts:
                db.insert_alert(
                    city_id   = city_id,
                    alert_type= alert["type"],
                    severity  = alert["severity"],
                    message   = f"{alert['type']} detected: {alert['value']}",
                    value     = alert["value"],
                    threshold = alert["threshold"],
                )
                logger.warning(f"🚨 Alert saved: {alert['type']} in {city_name}")

        return True

    except Exception as e:
        logger.error(f"[LOAD] Exception for {city_name}: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# PART 2: ETLPipeline Class
# ═══════════════════════════════════════════════════════════

class ETLPipeline:
    """
    Orchestrates the full ETL process for all cities.

    Features:
    - Multi-threaded processing (processes multiple cities in parallel)
    - Automatic retry on failure
    - Detailed run logging
    - Error isolation (one city's failure doesn't stop others)
    - Pipeline history tracking
    """

    def __init__(self, db: DatabaseManager = None,
                 api_client: WeatherAPIClient = None):
        """
        Initialize the pipeline with optional pre-built components.
        If not provided, creates new instances automatically.
        """
        self.db        = db or DatabaseManager()
        self.client    = api_client or WeatherAPIClient()
        self.validator = WeatherValidator()
        self.cleaner   = DataCleaner()
        self.max_workers = ETL_CONFIG.get("max_workers", 4)
        logger.info(f"ETL Pipeline initialized | Max Workers: {self.max_workers}")

    def _get_or_create_city(self, city: Dict) -> Optional[int]:
        """
        Looks up a city in the database.
        If it doesn't exist, creates it first.

        Returns the city's database ID.
        """
        city_obj = self.db.get_city_by_name(city["name"], city.get("country"))
        if city_obj:
            return city_obj["id"]

        # City doesn't exist yet — add it
        logger.info(f"  New city detected: {city['name']}. Adding to database...")
        self.db.seed_cities([city])
        city_obj = self.db.get_city_by_name(city["name"], city.get("country"))
        return city_obj["id"] if city_obj else None

    def process_one_city(self, city: Dict) -> Dict:
        """
        Runs the full ETL pipeline for a SINGLE city.

        Returns a result dict with success/failure info.
        """
        city_name = city.get("name", "Unknown")
        start_time = time.time()
        result = {
            "city":     city_name,
            "success":  False,
            "error":    None,
            "quality":  None,
            "alerts":   [],
            "duration": 0,
        }

        try:
            # Step 0: Get city ID from database
            city_id = self._get_or_create_city(city)
            if not city_id:
                result["error"] = "Could not get/create city in database"
                return result

            # Step 1: EXTRACT
            raw_data = extract(self.client, city)
            if not raw_data:
                result["error"] = "Extract phase returned no data"
                self._log_api_failure(city_id, city_name)
                return result

            # Log successful API call
            self.db.insert_api_log(
                city_id       = city_id,
                endpoint      = "current_weather",
                status_code   = 200,
                success       = True,
                response_time_ms = 100,
            )

            # Step 2: TRANSFORM
            cleaned_data, validation = transform(
                raw_data, city_name, self.cleaner, self.validator
            )
            if cleaned_data is None:
                result["error"] = f"Transform phase rejected data"
                result["quality"] = getattr(validation, "quality", "REJECTED")
                return result

            result["quality"] = validation.quality if validation else "UNKNOWN"
            result["alerts"]  = validation.alerts if validation else []

            # Step 3: LOAD
            success = load(self.db, city_id, cleaned_data, validation, city_name)
            result["success"] = success
            if not success:
                result["error"] = "Load phase failed"

        except Exception as e:
            result["error"] = str(e)
            logger.exception(f"Unexpected error processing {city_name}: {e}")

        finally:
            result["duration"] = round(time.time() - start_time, 3)

        return result

    def _log_api_failure(self, city_id: int, city_name: str):
        """Records a failed API call in the database."""
        try:
            self.db.insert_api_log(
                city_id        = city_id,
                endpoint       = "current_weather",
                status_code    = 0,
                success        = False,
                response_time_ms = 0,
                error_message  = f"No data returned for {city_name}",
            )
        except Exception:
            pass

    def run(self, cities: List[Dict] = None,
            parallel: bool = True) -> Dict:
        """
        Runs the FULL ETL pipeline for all cities.

        Args:
            cities  : List of city dicts (defaults to config CITIES)
            parallel: If True, process multiple cities at once

        Returns:
            Summary dict with run statistics
        """
        cities = cities or CITIES
        run_id = str(uuid.uuid4())[:8].upper()
        start_time = time.time()

        logger.info(f"\n{'='*60}")
        logger.info(f"  PIPELINE RUN STARTED | Run ID: {run_id}")
        logger.info(f"  Cities: {len(cities)} | Parallel: {parallel}")
        logger.info(f"{'='*60}")

        # Log run start
        self.db.log_pipeline_run(run_id, "RUNNING")

        results = []
        errors  = []

        if parallel and self.max_workers > 1 and len(cities) > 1:
            # Process multiple cities simultaneously
            logger.info(f"  Using {self.max_workers} parallel workers")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_city = {
                    executor.submit(self.process_one_city, city): city
                    for city in cities
                }
                for future in as_completed(future_to_city):
                    result = future.result()
                    results.append(result)
                    if result.get("error"):
                        errors.append(f"{result['city']}: {result['error']}")
        else:
            # Process cities one at a time
            for city in cities:
                result = self.process_one_city(city)
                results.append(result)
                if result.get("error"):
                    errors.append(f"{result['city']}: {result['error']}")

        # Calculate summary statistics
        total_duration     = round(time.time() - start_time, 2)
        cities_succeeded   = sum(1 for r in results if r["success"])
        cities_failed      = sum(1 for r in results if not r["success"])
        alert_count        = sum(len(r.get("alerts", [])) for r in results)

        status = "SUCCESS" if cities_failed == 0 else (
            "PARTIAL" if cities_succeeded > 0 else "FAILED"
        )

        # Log pipeline completion
        self.db.log_pipeline_run(
            run_id            = run_id,
            status            = status,
            cities_processed  = cities_succeeded,
            records_inserted  = cities_succeeded,
            records_failed    = cities_failed,
            errors            = errors,
            duration_seconds  = total_duration,
        )

        summary = {
            "run_id":           run_id,
            "status":           status,
            "total_cities":     len(cities),
            "cities_succeeded": cities_succeeded,
            "cities_failed":    cities_failed,
            "total_alerts":     alert_count,
            "duration_seconds": total_duration,
            "errors":           errors,
            "city_results":     results,
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"  PIPELINE RUN COMPLETE | Run ID: {run_id}")
        logger.info(f"  Status    : {status}")
        logger.info(f"  Succeeded : {cities_succeeded}/{len(cities)} cities")
        logger.info(f"  Alerts    : {alert_count}")
        logger.info(f"  Duration  : {total_duration}s")
        logger.info(f"{'='*60}\n")

        return summary

    def run_backfill(self, num_readings: int = 100,
                     cities: List[Dict] = None) -> Dict:
        """
        SPECIAL MODE: Generate historical data for testing/demo.
        Creates multiple readings per city spread over the past 30 days.
        Very useful for testing reports and analytics.

        Args:
            num_readings: How many historical records to generate per city
            cities:       Which cities to backfill (defaults to all)
        """
        import random
        from datetime import timedelta
        from api_client import generate_demo_weather

        cities = cities or CITIES
        logger.info(f"\n🔄 Starting BACKFILL | {num_readings} readings × {len(cities)} cities")

        total_inserted = 0
        now = datetime.now()

        for city in cities:
            city_id = self._get_or_create_city(city)
            if not city_id:
                continue

            for i in range(num_readings):
                # Spread readings over the past 30 days
                hours_ago = random.uniform(0, 30 * 24)
                fake_time = now - timedelta(hours=hours_ago)

                # Generate fake weather data
                data = generate_demo_weather(city["name"])
                data["collected_at"] = fake_time.isoformat()
                data["data_quality"] = "GOOD"

                # Add seasonal variation to temperature
                month = fake_time.month
                if month in [12, 1, 2]:
                    data["temperature"] -= random.uniform(5, 15)
                elif month in [6, 7, 8]:
                    data["temperature"] += random.uniform(3, 10)

                # Clean and insert
                cleaned = self.cleaner.clean(data)
                row_id = self.db.insert_weather_reading(city_id, cleaned)
                if row_id:
                    total_inserted += 1

            logger.info(f"  ✅ Backfilled {num_readings} readings for {city['name']}")

        logger.info(f"\n✅ BACKFILL COMPLETE: {total_inserted} total records inserted")
        return {"total_inserted": total_inserted, "cities": len(cities)}

    def get_health_summary(self) -> Dict:
        """Returns a quick overview of pipeline health."""
        db_health  = self.db.health_check()
        api_errors = self.db.get_api_error_rate(hours=24)
        recent_runs = self.db.get_pipeline_stats(limit=5)
        alerts     = self.db.get_active_alerts()
        val_stats  = self.validator.get_statistics()

        return {
            "database":         db_health,
            "api_error_rate":   api_errors,
            "recent_runs":      recent_runs,
            "active_alerts":    len(alerts),
            "validation":       val_stats,
            "last_updated":     datetime.now().isoformat(),
        }


# ═══════════════════════════════════════════════════════════
# QUICK TEST — run this file directly
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )

    from database import setup_database

    print("\n" + "="*60)
    print("  ETL PIPELINE — FULL RUN TEST")
    print("="*60)

    # Setup
    db = setup_database()
    pipeline = ETLPipeline(db=db)

    # First: backfill some historical data
    print("\n[1/2] Generating historical data (backfill)...")
    backfill = pipeline.run_backfill(num_readings=50)
    print(f"      Inserted: {backfill['total_inserted']} historical records")

    # Then: run a fresh pipeline collection
    print("\n[2/2] Running live ETL pipeline...")
    summary = pipeline.run(parallel=True)

    print(f"\n✅ Pipeline Complete!")
    print(f"   Run ID    : {summary['run_id']}")
    print(f"   Status    : {summary['status']}")
    print(f"   Cities    : {summary['cities_succeeded']}/{summary['total_cities']}")
    print(f"   Alerts    : {summary['total_alerts']}")
    print(f"   Duration  : {summary['duration_seconds']}s")

    if summary.get("errors"):
        print(f"\n⚠️  Errors:")
        for err in summary["errors"]:
            print(f"   - {err}")
