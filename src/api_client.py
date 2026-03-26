"""
api_client.py - Weather API Client
====================================
This file handles ALL communication with OpenWeatherMap API.

BEGINNER CONCEPTS:
- API (Application Programming Interface): A way for programs to talk to each other
- HTTP Request: Like sending a letter to a server asking for data
- JSON Response: The server's reply — data formatted like Python dictionaries
- Rate Limiting: APIs limit how often you can call them (free tier = 60/minute)
- Retry Logic: If a request fails, wait and try again automatically

HOW AN API CALL WORKS:
1. You build a URL with your API key and city name
2. You send an HTTP GET request to that URL
3. OpenWeatherMap returns JSON data
4. You parse (extract) the values you need

EXAMPLE API RESPONSE (simplified):
{
    "main": {"temp": 22.5, "humidity": 65, "pressure": 1013},
    "wind": {"speed": 5.2, "deg": 180},
    "weather": [{"main": "Clouds", "description": "overcast clouds"}]
}
"""

import time
import logging
import random
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import (API_KEY, BASE_URL, GEOCODING_URL,
                    API_TIMEOUT, API_RETRY_ATTEMPTS,
                    API_RETRY_DELAY, ETL_CONFIG)

logger = logging.getLogger(__name__)

# Check if the 'requests' library is available
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("'requests' library not installed. Using demo mode only.")


# ═══════════════════════════════════════════════════════════
# PART 1: Demo Data Generator (works without an API key)
# ═══════════════════════════════════════════════════════════

# Realistic weather patterns for each city (demo mode)
CITY_WEATHER_PROFILES = {
    "London": {
        "temp_range": (5, 20),
        "humidity_range": (60, 90),
        "weather_choices": ["Clouds", "Rain", "Drizzle", "Clear"],
        "desc_choices": ["overcast clouds", "light rain", "drizzle", "clear sky"],
    },
    "New York": {
        "temp_range": (-5, 35),
        "humidity_range": (40, 80),
        "weather_choices": ["Clear", "Clouds", "Rain", "Snow"],
        "desc_choices": ["clear sky", "few clouds", "moderate rain", "light snow"],
    },
    "Tokyo": {
        "temp_range": (2, 38),
        "humidity_range": (50, 85),
        "weather_choices": ["Clear", "Clouds", "Rain", "Thunderstorm"],
        "desc_choices": ["clear sky", "scattered clouds", "light rain", "thunderstorm"],
    },
    "Sydney": {
        "temp_range": (10, 40),
        "humidity_range": (40, 75),
        "weather_choices": ["Clear", "Clouds", "Rain"],
        "desc_choices": ["clear sky", "partly cloudy", "light rain"],
    },
    "Mumbai": {
        "temp_range": (22, 42),
        "humidity_range": (60, 95),
        "weather_choices": ["Clear", "Clouds", "Rain", "Thunderstorm"],
        "desc_choices": ["clear sky", "humid", "heavy rain", "thunderstorm with rain"],
    },
    "Dubai": {
        "temp_range": (18, 48),
        "humidity_range": (20, 60),
        "weather_choices": ["Clear", "Clouds", "Dust"],
        "desc_choices": ["clear sky", "few clouds", "haze", "blowing dust"],
    },
    "Paris": {
        "temp_range": (3, 28),
        "humidity_range": (55, 85),
        "weather_choices": ["Clouds", "Clear", "Rain", "Drizzle"],
        "desc_choices": ["overcast clouds", "clear sky", "light rain", "drizzle"],
    },
    "New Delhi": {
        "temp_range": (5, 48),
        "humidity_range": (20, 90),
        "weather_choices": ["Clear", "Dust", "Haze", "Clouds"],
        "desc_choices": ["clear sky", "dust", "haze", "mist"],
    },
}

def generate_demo_weather(city_name: str) -> Dict:
    """
    Generates realistic-looking fake weather data.
    Used when no real API key is available.

    BEGINNER TIP: This lets you develop and test your pipeline
    without spending API quota or waiting for real data.
    """
    profile = CITY_WEATHER_PROFILES.get(city_name, {
        "temp_range": (10, 30),
        "humidity_range": (40, 80),
        "weather_choices": ["Clear", "Clouds"],
        "desc_choices": ["clear sky", "few clouds"],
    })

    # Generate values
    temp = round(random.uniform(*profile["temp_range"]), 2)
    humidity = random.randint(*profile["humidity_range"])
    weather_idx = random.randint(0, len(profile["weather_choices"]) - 1)

    # Add realistic variation
    is_rainy = profile["weather_choices"][weather_idx] in ["Rain", "Drizzle", "Thunderstorm"]
    rain_1h = round(random.uniform(0.5, 20.0), 2) if is_rainy else 0.0

    now = datetime.now()

    return {
        "temperature":      temp,
        "feels_like":       round(temp + random.uniform(-4, 4), 2),
        "temp_min":         round(temp - random.uniform(1, 5), 2),
        "temp_max":         round(temp + random.uniform(1, 5), 2),
        "humidity":         humidity,
        "pressure":         random.randint(990, 1030),
        "wind_speed":       round(random.uniform(0, 15), 2),
        "wind_direction":   random.randint(0, 359),
        "wind_gust":        round(random.uniform(0, 20), 2),
        "visibility":       random.randint(3000, 10000),
        "cloudiness":       random.randint(0, 100),
        "weather_main":     profile["weather_choices"][weather_idx],
        "weather_desc":     profile["desc_choices"][weather_idx],
        "weather_icon":     "04d",
        "rain_1h":          rain_1h,
        "snow_1h":          0.0,
        "uv_index":         round(random.uniform(0, 11), 1),
        "sunrise":          now.replace(hour=6, minute=30).isoformat(),
        "sunset":           now.replace(hour=19, minute=30).isoformat(),
        "collected_at":     now.isoformat(),
        "data_source":      "demo",
    }


# ═══════════════════════════════════════════════════════════
# PART 2: WeatherAPIClient Class (Real API)
# ═══════════════════════════════════════════════════════════

class WeatherAPIClient:
    """
    Communicates with the OpenWeatherMap API.

    KEY METHODS:
    - get_current_weather(city, country) → Raw API data
    - get_city_coordinates(city, country) → Lat/Lon for a city
    - fetch_and_parse(city, country) → Clean, processed weather dict

    RATE LIMITING STRATEGY:
    We track calls per minute and automatically pause if we're
    getting close to the limit (60 calls/minute on free tier).
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or API_KEY
        self.session = None
        self.call_count = 0
        self.call_window_start = time.time()
        self.is_demo_mode = (
            self.api_key in ["demo_key", "", None]
            or ETL_CONFIG.get("enable_demo_mode", False)
        )

        if self.is_demo_mode:
            logger.info("🎭 API Client running in DEMO MODE (no real API calls)")
        else:
            logger.info(f"🌐 API Client ready | Key: {self.api_key[:6]}...")

        # Initialize HTTP session for real API calls
        if REQUESTS_AVAILABLE and not self.is_demo_mode:
            self.session = requests.Session()
            self.session.headers.update({
                "Accept": "application/json",
                "User-Agent": "WeatherPipeline/1.0"
            })

    def _rate_limit_check(self):
        """
        Enforces API rate limits.
        Free tier: 60 calls per minute.
        Automatically pauses if we're going too fast.
        """
        now = time.time()
        elapsed = now - self.call_window_start

        # Reset counter every minute
        if elapsed >= 60:
            self.call_count = 0
            self.call_window_start = now
            return

        # If we've hit 55 calls (buffer before limit), pause
        if self.call_count >= 55:
            wait_time = 60 - elapsed + 1
            logger.warning(f"⏳ Rate limit approached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            self.call_count = 0
            self.call_window_start = time.time()

    def _make_request(self, url: str, params: Dict) -> Optional[Dict]:
        """
        Makes a single HTTP GET request with retry logic.

        RETRY LOGIC EXPLAINED:
        1. Try the request
        2. If it fails, wait API_RETRY_DELAY seconds
        3. Try again, up to API_RETRY_ATTEMPTS times
        4. If all attempts fail, return None

        Args:
            url: The API endpoint URL
            params: Query parameters (like api key, city name)

        Returns:
            Parsed JSON response as a dict, or None on failure
        """
        if not REQUESTS_AVAILABLE:
            logger.error("requests library not available")
            return None

        self._rate_limit_check()

        for attempt in range(1, API_RETRY_ATTEMPTS + 1):
            start_time = time.time()
            try:
                response = self.session.get(url, params=params, timeout=API_TIMEOUT)
                elapsed_ms = int((time.time() - start_time) * 1000)
                self.call_count += 1

                if response.status_code == 200:
                    logger.debug(f"  API call OK ({elapsed_ms}ms) | {url}")
                    return response.json()

                elif response.status_code == 401:
                    logger.error(f"❌ Invalid API key. Check your .env file.")
                    return None

                elif response.status_code == 429:
                    wait_time = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"⏳ Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)

                else:
                    logger.warning(f"  Attempt {attempt}/{API_RETRY_ATTEMPTS}: "
                                   f"HTTP {response.status_code}")
                    time.sleep(API_RETRY_DELAY)

            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.warning(f"  Attempt {attempt}/{API_RETRY_ATTEMPTS}: {e}")
                if attempt < API_RETRY_ATTEMPTS:
                    time.sleep(API_RETRY_DELAY * attempt)  # Exponential backoff

        logger.error(f"❌ All {API_RETRY_ATTEMPTS} attempts failed for {url}")
        return None

    def get_city_coordinates(self, city: str, country: str = None) -> Optional[Dict]:
        """
        Uses the Geocoding API to get latitude/longitude for a city.

        Why do we need coordinates?
        The 'current weather' endpoint works better with lat/lon
        than with city names (avoids ambiguity like "London, UK" vs "London, Ontario").

        Args:
            city: City name, e.g. "Mumbai"
            country: ISO country code, e.g. "IN"

        Returns:
            Dict with lat, lon, name, country
        """
        if self.is_demo_mode:
            # Return fake coordinates for demo
            coords = {
                "London":    {"lat": 51.5074, "lon": -0.1278},
                "New York":  {"lat": 40.7128, "lon": -74.0060},
                "Tokyo":     {"lat": 35.6762, "lon": 139.6503},
                "Sydney":    {"lat": -33.8688, "lon": 151.2093},
                "Mumbai":    {"lat": 19.0760, "lon": 72.8777},
                "Dubai":     {"lat": 25.2048, "lon": 55.2708},
                "Paris":     {"lat": 48.8566, "lon": 2.3522},
                "New Delhi": {"lat": 28.6139, "lon": 77.2090},
            }
            return coords.get(city, {"lat": 0.0, "lon": 0.0})

        query = f"{city},{country}" if country else city
        params = {
            "q":     query,
            "limit": 1,
            "appid": self.api_key
        }
        data = self._make_request(f"{GEOCODING_URL}/direct", params)
        if data and len(data) > 0:
            return {
                "lat":     data[0]["lat"],
                "lon":     data[0]["lon"],
                "name":    data[0].get("name", city),
                "country": data[0].get("country", country or ""),
            }
        return None

    def get_current_weather(self, city: str, country: str = None,
                            lat: float = None, lon: float = None) -> Optional[Dict]:
        """
        Fetches current weather data from OpenWeatherMap.

        You can provide either:
        - city name + country code
        - latitude + longitude (more accurate)

        Args:
            city:    City name
            country: ISO country code (e.g., "IN", "US", "GB")
            lat:     Latitude (optional — used instead of city name)
            lon:     Longitude (optional — used instead of city name)

        Returns:
            Raw JSON response from the API
        """
        # Demo mode — return fake data immediately
        if self.is_demo_mode:
            logger.debug(f"  [DEMO] Generating fake data for {city}")
            time.sleep(0.1)  # Simulate network delay
            return {"_demo": True, "_city": city, **generate_demo_weather(city)}

        # Real API call
        params = {
            "appid": self.api_key,
            "units": "metric",      # Celsius temperatures
            "lang":  "en",
        }

        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
        else:
            query = f"{city},{country}" if country else city
            params["q"] = query

        return self._make_request(f"{BASE_URL}/weather", params)

    def get_forecast(self, city: str, country: str = None,
                     days: int = 5) -> Optional[Dict]:
        """
        Gets 5-day / 3-hour weather forecast.
        Only available on paid tiers for more than 5 days.
        """
        if self.is_demo_mode:
            # Generate hourly forecast data for demo
            forecast_list = []
            now = datetime.now()
            for i in range(40):  # 5 days × 8 readings per day
                hours_ahead = i * 3
                temp = round(random.uniform(15, 30) + random.uniform(-5, 5), 2)
                forecast_list.append({
                    "dt": int(now.timestamp()) + (hours_ahead * 3600),
                    "main": {
                        "temp": temp,
                        "humidity": random.randint(40, 90),
                        "pressure": random.randint(995, 1025),
                    },
                    "weather": [{"main": "Clouds", "description": "overcast clouds"}],
                    "wind": {"speed": round(random.uniform(0, 12), 1), "deg": random.randint(0, 359)},
                    "dt_txt": (now.replace(hour=0, minute=0, second=0)).isoformat(),
                })
            return {"list": forecast_list, "city": {"name": city}}

        params = {
            "appid": self.api_key,
            "units": "metric",
            "cnt":   days * 8,  # 8 readings per day (every 3 hours)
        }
        query = f"{city},{country}" if country else city
        params["q"] = query
        return self._make_request(f"{BASE_URL}/forecast", params)

    def parse_current_weather(self, raw_data: Dict, city_name: str = "") -> Optional[Dict]:
        """
        Converts raw API JSON into a clean, flat dictionary
        that matches our database schema.

        RAW API FORMAT (nested):
        {
            "main": {"temp": 22.5, "humidity": 65},
            "wind": {"speed": 5.2},
            "weather": [{"main": "Clear", "description": "clear sky"}]
        }

        CLEAN OUTPUT FORMAT (flat):
        {
            "temperature": 22.5,
            "humidity": 65,
            "wind_speed": 5.2,
            ...
        }
        """
        if not raw_data:
            return None

        # Handle demo mode data (already flat)
        if raw_data.get("_demo"):
            data = dict(raw_data)
            data.pop("_demo", None)
            data.pop("_city", None)
            return data

        try:
            main      = raw_data.get("main", {})
            wind      = raw_data.get("wind", {})
            weather   = raw_data.get("weather", [{}])[0]
            rain      = raw_data.get("rain", {})
            snow      = raw_data.get("snow", {})
            sys_data  = raw_data.get("sys", {})

            # Convert Unix timestamps to readable time strings
            sunrise_ts = sys_data.get("sunrise")
            sunset_ts  = sys_data.get("sunset")

            return {
                "temperature":      main.get("temp"),
                "feels_like":       main.get("feels_like"),
                "temp_min":         main.get("temp_min"),
                "temp_max":         main.get("temp_max"),
                "humidity":         main.get("humidity"),
                "pressure":         main.get("pressure"),
                "wind_speed":       wind.get("speed"),
                "wind_direction":   wind.get("deg"),
                "wind_gust":        wind.get("gust"),
                "visibility":       raw_data.get("visibility"),
                "cloudiness":       raw_data.get("clouds", {}).get("all"),
                "weather_main":     weather.get("main"),
                "weather_desc":     weather.get("description"),
                "weather_icon":     weather.get("icon"),
                "rain_1h":          rain.get("1h", 0.0),
                "snow_1h":          snow.get("1h", 0.0),
                "uv_index":         None,   # Needs separate endpoint
                "sunrise":          datetime.fromtimestamp(sunrise_ts).isoformat() if sunrise_ts else None,
                "sunset":           datetime.fromtimestamp(sunset_ts).isoformat() if sunset_ts else None,
                "collected_at":     datetime.now().isoformat(),
                "data_source":      "openweathermap",
            }
        except Exception as e:
            logger.error(f"Failed to parse weather data for {city_name}: {e}")
            logger.debug(f"Raw data was: {raw_data}")
            return None

    def fetch_weather_for_city(self, city_name: str, country: str,
                               lat: float = None, lon: float = None) -> Optional[Dict]:
        """
        HIGH-LEVEL METHOD: Fetches + parses weather for one city.
        This is the main method called by the ETL pipeline.

        Returns:
            Clean weather dict ready to insert into the database
        """
        logger.info(f"  🌤  Fetching weather: {city_name}, {country}")
        raw = self.get_current_weather(city_name, country, lat, lon)
        if not raw:
            logger.error(f"  ❌ No data received for {city_name}")
            return None

        parsed = self.parse_current_weather(raw, city_name)
        if parsed:
            logger.info(f"  ✅ {city_name}: {parsed.get('temperature')}°C, "
                        f"{parsed.get('weather_desc')}")
        return parsed

    def test_connection(self) -> bool:
        """Tests if the API is reachable and key is valid."""
        if self.is_demo_mode:
            logger.info("✅ Demo mode — no connection test needed")
            return True

        test_data = self.get_current_weather("London", "GB")
        if test_data:
            logger.info("✅ API connection successful!")
            return True
        else:
            logger.error("❌ API connection failed. Check your API key.")
            return False


# ═══════════════════════════════════════════════════════════
# QUICK TEST — run this file directly
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*50)
    print("  API CLIENT TEST")
    print("="*50)

    client = WeatherAPIClient()

    # Test fetching weather for a few cities
    test_cities = [
        ("London",   "GB"),
        ("Mumbai",   "IN"),
        ("New York", "US"),
    ]

    for city_name, country in test_cities:
        data = client.fetch_weather_for_city(city_name, country)
        if data:
            print(f"\n📍 {city_name}, {country}")
            print(f"   Temperature : {data.get('temperature')}°C")
            print(f"   Humidity    : {data.get('humidity')}%")
            print(f"   Condition   : {data.get('weather_desc')}")
            print(f"   Wind        : {data.get('wind_speed')} m/s")
        else:
            print(f"\n❌ Failed to get data for {city_name}")
