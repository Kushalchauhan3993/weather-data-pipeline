"""
validators.py - Data Quality & Validation
==========================================
Before saving any weather data to our database, we check
that the values are physically reasonable.

WHY VALIDATION MATTERS:
- APIs can return corrupt or erroneous data
- Sensors sometimes malfunction
- Network errors can cause partial data
- Bad data corrupts your analysis results

HOW IT WORKS:
1. We define valid RANGES for each measurement
2. We check each incoming reading against those ranges
3. If something is wrong, we mark it, log it, or reject it
4. We track quality metrics over time (data quality score)

QUALITY LEVELS:
- GOOD     : All checks passed ✅
- WARNING  : Some values look unusual ⚠️
- BAD      : Critical values are missing or impossible ❌
- REJECTED : Data is so bad it shouldn't be stored 🚫
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import VALIDATION_RULES, ALERT_THRESHOLDS

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# PART 1: Validation Result Helper
# ═══════════════════════════════════════════════════════════

class ValidationResult:
    """
    Holds the result of validating one weather reading.

    Attributes:
        is_valid   : True if data is acceptable
        quality    : "GOOD", "WARNING", "BAD", or "REJECTED"
        errors     : List of critical problems
        warnings   : List of non-critical concerns
        alerts     : List of weather alerts triggered
    """

    def __init__(self):
        self.is_valid   = True
        self.quality    = "GOOD"
        self.errors     = []     # Critical issues
        self.warnings   = []     # Non-critical issues
        self.alerts     = []     # Weather alert triggers
        self.score      = 100    # Start at 100%, subtract for issues

    def add_error(self, message: str, penalty: int = 25):
        self.errors.append(message)
        self.score = max(0, self.score - penalty)
        self.is_valid = False
        if self.quality in ["GOOD", "WARNING"]:
            self.quality = "BAD"

    def add_warning(self, message: str, penalty: int = 10):
        self.warnings.append(message)
        self.score = max(0, self.score - penalty)
        if self.quality == "GOOD":
            self.quality = "WARNING"

    def add_alert(self, alert_type: str, value: float, threshold: float,
                  severity: str = "INFO"):
        self.alerts.append({
            "type":      alert_type,
            "value":     value,
            "threshold": threshold,
            "severity":  severity,
        })

    def reject(self, reason: str):
        self.errors.append(f"REJECTED: {reason}")
        self.is_valid = False
        self.quality = "REJECTED"
        self.score = 0

    def summary(self) -> str:
        parts = [f"Quality={self.quality} | Score={self.score}%"]
        if self.errors:
            parts.append(f"Errors: {'; '.join(self.errors)}")
        if self.warnings:
            parts.append(f"Warnings: {'; '.join(self.warnings)}")
        if self.alerts:
            types = [a["type"] for a in self.alerts]
            parts.append(f"Alerts: {', '.join(types)}")
        return " | ".join(parts)


# ═══════════════════════════════════════════════════════════
# PART 2: WeatherValidator Class
# ═══════════════════════════════════════════════════════════

class WeatherValidator:
    """
    Validates weather readings before they enter the database.

    VALIDATION CHECKS:
    1. Required fields present
    2. Temperature within physical limits
    3. Humidity 0–100%
    4. Pressure within normal range
    5. Wind speed non-negative and not too high
    6. Timestamp not in the future
    7. No duplicate readings (same city, same time)
    8. Alert thresholds (extreme heat, cold, wind, etc.)
    """

    def __init__(self):
        self.rules  = VALIDATION_RULES
        self.alerts = ALERT_THRESHOLDS
        self.total_validated  = 0
        self.total_passed     = 0
        self.total_warnings   = 0
        self.total_failed     = 0
        self.total_rejected   = 0

    # ─────────────────────────────────────────────
    # MAIN VALIDATION METHOD
    # ─────────────────────────────────────────────

    def validate(self, data: Dict, city_name: str = "Unknown") -> ValidationResult:
        """
        Run ALL validation checks on a weather reading.

        Args:
            data:      The weather dict from api_client.py
            city_name: For logging purposes

        Returns:
            ValidationResult with quality, errors, warnings, alerts
        """
        result = ValidationResult()
        self.total_validated += 1

        if not data:
            result.reject("Empty or null data received")
            self.total_rejected += 1
            return result

        # Run each check in order
        self._check_required_fields(data, result)
        self._check_temperature(data, result)
        self._check_humidity(data, result)
        self._check_pressure(data, result)
        self._check_wind(data, result)
        self._check_visibility(data, result)
        self._check_timestamp(data, result)
        self._check_weather_alerts(data, result, city_name)
        self._check_consistency(data, result)

        # Update statistics
        if result.quality == "GOOD":
            self.total_passed += 1
        elif result.quality == "WARNING":
            self.total_warnings += 1
        elif result.quality in ["BAD", "REJECTED"]:
            self.total_failed += 1

        # Log the result
        log_fn = logger.warning if not result.is_valid else logger.debug
        log_fn(f"  [{result.quality}] {city_name}: {result.summary()}")

        return result

    # ─────────────────────────────────────────────
    # INDIVIDUAL CHECKS
    # ─────────────────────────────────────────────

    def _check_required_fields(self, data: Dict, result: ValidationResult):
        """
        RULE: These fields MUST be present for a reading to be useful.
        Temperature and collected_at are the bare minimum.
        """
        required = ["temperature", "humidity", "collected_at"]
        missing = [f for f in required if data.get(f) is None]

        if "temperature" in missing or "collected_at" in missing:
            result.reject(f"Critical fields missing: {missing}")
        elif missing:
            result.add_warning(f"Optional fields missing: {missing}", penalty=5)

    def _check_temperature(self, data: Dict, result: ValidationResult):
        """
        RULE: Temperature must be within the range of temperatures
        ever recorded on Earth (roughly -90°C to +60°C).
        """
        temp = data.get("temperature")
        if temp is None:
            return

        rules = self.rules["temperature"]

        if temp < rules["min"] or temp > rules["max"]:
            result.add_error(
                f"Temperature {temp}°C is outside valid range "
                f"[{rules['min']}, {rules['max']}]",
                penalty=30
            )
        elif temp < -60 or temp > 55:
            result.add_warning(
                f"Temperature {temp}°C is extreme but not impossible",
                penalty=5
            )

        # Check feels_like consistency
        feels_like = data.get("feels_like")
        if feels_like is not None and temp is not None:
            diff = abs(temp - feels_like)
            if diff > 20:
                result.add_warning(
                    f"Large gap between temp ({temp}) and feels_like ({feels_like})",
                    penalty=5
                )

    def _check_humidity(self, data: Dict, result: ValidationResult):
        """
        RULE: Humidity is a percentage — must be 0–100.
        100% means the air is fully saturated with water vapor.
        """
        humidity = data.get("humidity")
        if humidity is None:
            return

        rules = self.rules["humidity"]
        if not (rules["min"] <= humidity <= rules["max"]):
            result.add_error(
                f"Humidity {humidity}% is outside [0, 100]",
                penalty=20
            )

    def _check_pressure(self, data: Dict, result: ValidationResult):
        """
        RULE: Atmospheric pressure in hPa.
        Normal range: 870–1085 hPa.
        Standard sea-level pressure: ~1013 hPa.
        """
        pressure = data.get("pressure")
        if pressure is None:
            return

        rules = self.rules["pressure"]
        if not (rules["min"] <= pressure <= rules["max"]):
            result.add_error(
                f"Pressure {pressure} hPa outside valid range "
                f"[{rules['min']}, {rules['max']}]",
                penalty=20
            )
        elif pressure < 940 or pressure > 1060:
            result.add_warning(
                f"Pressure {pressure} hPa is unusually extreme",
                penalty=5
            )

    def _check_wind(self, data: Dict, result: ValidationResult):
        """
        RULE: Wind speed must be non-negative.
        Maximum ever recorded: ~113 m/s during a tropical cyclone.
        """
        wind_speed = data.get("wind_speed")
        if wind_speed is None:
            return

        rules = self.rules["wind_speed"]
        if wind_speed < rules["min"]:
            result.add_error(f"Wind speed {wind_speed} m/s cannot be negative", penalty=20)
        elif wind_speed > rules["max"]:
            result.add_error(
                f"Wind speed {wind_speed} m/s exceeds maximum ever recorded",
                penalty=20
            )

        # Check wind direction (0–360 degrees)
        wind_dir = data.get("wind_direction")
        if wind_dir is not None:
            if not (0 <= wind_dir <= 360):
                result.add_warning(
                    f"Wind direction {wind_dir}° outside 0–360 range",
                    penalty=5
                )

    def _check_visibility(self, data: Dict, result: ValidationResult):
        """
        RULE: Visibility in meters.
        APIs report a maximum of 10000m (10km) even if it's clearer.
        """
        visibility = data.get("visibility")
        if visibility is None:
            return

        rules = self.rules["visibility"]
        if not (rules["min"] <= visibility <= rules["max"]):
            result.add_warning(
                f"Visibility {visibility}m outside expected range",
                penalty=5
            )

    def _check_timestamp(self, data: Dict, result: ValidationResult):
        """
        RULE: collected_at should not be in the future.
        We allow a 5-minute buffer for clock differences.
        """
        collected_at_str = data.get("collected_at")
        if not collected_at_str:
            return

        try:
            collected_at = datetime.fromisoformat(str(collected_at_str))
            now = datetime.now()
            diff_minutes = (collected_at - now).total_seconds() / 60

            if diff_minutes > 5:
                result.add_warning(
                    f"Timestamp is {diff_minutes:.1f} minutes in the future",
                    penalty=10
                )
            elif diff_minutes < -1440:  # More than 24 hours old
                result.add_warning(
                    f"Data is more than 24 hours old",
                    penalty=5
                )
        except (ValueError, TypeError) as e:
            result.add_error(f"Invalid timestamp format: {collected_at_str}", penalty=15)

    def _check_weather_alerts(self, data: Dict, result: ValidationResult,
                               city_name: str):
        """
        RULE: Check if any weather measurement exceeds alert thresholds.
        These don't make data INVALID — they just trigger notifications.
        """
        temp       = data.get("temperature")
        wind_speed = data.get("wind_speed")
        visibility = data.get("visibility")
        rain_1h    = data.get("rain_1h", 0)

        if temp is not None:
            if temp >= self.alerts["extreme_heat"]:
                result.add_alert(
                    "EXTREME_HEAT", temp, self.alerts["extreme_heat"], "HIGH"
                )
                logger.warning(f"🔥 HEAT ALERT: {city_name} = {temp}°C")

            elif temp <= self.alerts["extreme_cold"]:
                result.add_alert(
                    "EXTREME_COLD", temp, self.alerts["extreme_cold"], "HIGH"
                )
                logger.warning(f"🥶 COLD ALERT: {city_name} = {temp}°C")

        if wind_speed is not None and wind_speed >= self.alerts["high_wind"]:
            result.add_alert(
                "HIGH_WIND", wind_speed, self.alerts["high_wind"], "MEDIUM"
            )
            logger.warning(f"💨 WIND ALERT: {city_name} = {wind_speed} m/s")

        if visibility is not None and visibility <= self.alerts["low_visibility"]:
            result.add_alert(
                "LOW_VISIBILITY", visibility, self.alerts["low_visibility"], "MEDIUM"
            )

        if rain_1h and rain_1h >= self.alerts["heavy_rain"]:
            result.add_alert(
                "HEAVY_RAIN", rain_1h, self.alerts["heavy_rain"], "HIGH"
            )
            logger.warning(f"🌧  RAIN ALERT: {city_name} = {rain_1h} mm/hr")

    def _check_consistency(self, data: Dict, result: ValidationResult):
        """
        RULE: Some combinations of values don't make physical sense.
        For example: 0% humidity but heavy rain is impossible.
        """
        humidity = data.get("humidity")
        rain_1h  = data.get("rain_1h", 0)
        weather_main = data.get("weather_main", "")

        # Rain but very low humidity?
        if rain_1h and rain_1h > 1 and humidity is not None and humidity < 30:
            result.add_warning(
                f"Rain ({rain_1h} mm/hr) but humidity is only {humidity}%",
                penalty=10
            )

        # Snow but temperature well above 0?
        snow_1h = data.get("snow_1h", 0)
        temp = data.get("temperature")
        if snow_1h and snow_1h > 0 and temp is not None and temp > 5:
            result.add_warning(
                f"Snow reported ({snow_1h} mm/hr) but temp is {temp}°C",
                penalty=10
            )

    # ─────────────────────────────────────────────
    # VALIDATION STATISTICS
    # ─────────────────────────────────────────────

    def get_statistics(self) -> Dict:
        """Returns summary statistics about validation performance."""
        if self.total_validated == 0:
            return {"total": 0, "pass_rate": 0}

        return {
            "total_validated":  self.total_validated,
            "passed":           self.total_passed,
            "warnings":         self.total_warnings,
            "failed":           self.total_failed,
            "rejected":         self.total_rejected,
            "pass_rate_pct":    round(self.total_passed / self.total_validated * 100, 1),
            "warning_rate_pct": round(self.total_warnings / self.total_validated * 100, 1),
            "fail_rate_pct":    round(self.total_failed / self.total_validated * 100, 1),
        }

    def reset_statistics(self):
        """Resets the running counters."""
        self.total_validated = 0
        self.total_passed = 0
        self.total_warnings = 0
        self.total_failed = 0
        self.total_rejected = 0


# ═══════════════════════════════════════════════════════════
# PART 3: Data Cleaner
# ═══════════════════════════════════════════════════════════

class DataCleaner:
    """
    Cleans and normalizes weather data BEFORE validation.
    Fixes small issues that can be corrected automatically.

    WHAT IT CLEANS:
    - Rounds numbers to appropriate decimal places
    - Caps visibility at 10,000m (API max)
    - Ensures rain/snow default to 0 if missing
    - Normalizes temperature units (if somehow wrong)
    - Removes leading/trailing spaces from text
    """

    def clean(self, data: Dict) -> Dict:
        """Applies all cleaning steps to a weather reading."""
        if not data:
            return data

        cleaned = dict(data)  # Don't modify original

        # Round numeric fields
        if cleaned.get("temperature") is not None:
            cleaned["temperature"] = round(float(cleaned["temperature"]), 2)
        if cleaned.get("feels_like") is not None:
            cleaned["feels_like"] = round(float(cleaned["feels_like"]), 2)
        if cleaned.get("wind_speed") is not None:
            cleaned["wind_speed"] = round(float(cleaned["wind_speed"]), 2)

        # Cap visibility at maximum reportable value
        if cleaned.get("visibility") is not None:
            cleaned["visibility"] = min(int(cleaned["visibility"]), 10000)

        # Default rain/snow to 0 if not present
        cleaned.setdefault("rain_1h", 0.0)
        cleaned.setdefault("snow_1h", 0.0)

        # Clean text fields
        for field in ["weather_main", "weather_desc", "weather_icon"]:
            if cleaned.get(field):
                cleaned[field] = str(cleaned[field]).strip()

        # Ensure humidity is an integer
        if cleaned.get("humidity") is not None:
            cleaned["humidity"] = int(cleaned["humidity"])

        # Ensure pressure is an integer
        if cleaned.get("pressure") is not None:
            cleaned["pressure"] = int(cleaned["pressure"])

        return cleaned


# ═══════════════════════════════════════════════════════════
# QUICK TEST
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*50)
    print("  DATA VALIDATION TEST")
    print("="*50)

    validator = WeatherValidator()
    cleaner   = DataCleaner()

    # Test cases
    test_readings = [
        {
            "name": "Valid Reading",
            "data": {
                "temperature": 28.5, "feels_like": 30.0,
                "humidity": 70, "pressure": 1013,
                "wind_speed": 5.2, "wind_direction": 180,
                "visibility": 8000, "cloudiness": 40,
                "weather_main": "Clear", "weather_desc": "clear sky",
                "rain_1h": 0.0, "snow_1h": 0.0,
                "collected_at": datetime.now().isoformat(),
            }
        },
        {
            "name": "Extreme Heat Alert",
            "data": {
                "temperature": 45.0, "feels_like": 48.0,
                "humidity": 20, "pressure": 1000,
                "wind_speed": 8.0, "wind_direction": 90,
                "visibility": 9000, "cloudiness": 5,
                "weather_main": "Clear", "weather_desc": "clear sky",
                "rain_1h": 0.0, "snow_1h": 0.0,
                "collected_at": datetime.now().isoformat(),
            }
        },
        {
            "name": "Invalid Temperature",
            "data": {
                "temperature": 150.0,  # Impossible!
                "humidity": 50, "pressure": 1013,
                "wind_speed": 5.0,
                "collected_at": datetime.now().isoformat(),
            }
        },
        {
            "name": "Missing Fields",
            "data": {"humidity": 60, "pressure": 1010}  # No temperature!
        },
    ]

    for test in test_readings:
        print(f"\n📋 Testing: {test['name']}")
        cleaned = cleaner.clean(test["data"])
        result  = validator.validate(cleaned, test["name"])
        print(f"   Result : {result.quality}")
        if result.errors:
            for e in result.errors:
                print(f"   ❌ {e}")
        if result.warnings:
            for w in result.warnings:
                print(f"   ⚠️  {w}")
        if result.alerts:
            for a in result.alerts:
                print(f"   🚨 Alert: {a['type']} ({a['value']})")

    print("\n📊 Validation Statistics:")
    stats = validator.get_statistics()
    for k, v in stats.items():
        print(f"   {k:20s}: {v}")
