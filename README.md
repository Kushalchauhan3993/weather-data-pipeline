# 🌤 Weather Data Pipeline System — Enterprise Edition

A complete, production-ready **ETL (Extract, Transform, Load) pipeline** that collects weather data from OpenWeatherMap API, processes and validates it, stores it in a database, and generates automated reports.

---

## 📋 Table of Contents

1. [Project Overview](#-project-overview)
2. [Architecture](#-architecture)
3. [Project Structure](#-project-structure)
4. [Quick Start (5 Minutes)](#-quick-start-5-minutes)
5. [Week-by-Week Guide](#-week-by-week-guide)
6. [Module Documentation](#-module-documentation)
7. [Database Schema](#-database-schema)
8. [Analysis Questions & Queries](#-analysis-questions--queries)
9. [Enterprise Features (Option 4)](#-enterprise-features-option-4)
10. [Testing](#-testing)
11. [Deployment](#-deployment)
12. [Troubleshooting](#-troubleshooting)

---

## 🎯 Project Overview

This pipeline tracks weather data for **8 cities worldwide** every 30 minutes, validates the data quality, stores it in a normalized database, and generates:

- 📊 Daily weather reports (TXT, JSON, HTML)
- 📈 Analytics reports answering 5 key questions
- 🚨 Real-time weather alerts
- 📡 System health monitoring dashboard

**Cities Tracked:** London, New York, Tokyo, Sydney, Mumbai, Dubai, Paris, New Delhi

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    WEATHER PIPELINE SYSTEM                       │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────────┐ │
│  │  SCHEDULER  │───▶│  ETL CORE   │───▶│     DATABASE         │ │
│  │ (scheduler) │    │             │    │  ┌────────────────┐  │ │
│  │             │    │ 1. EXTRACT  │    │  │ cities          │  │ │
│  │ Every 30min │    │    api_client│    │  │ weather_readings│  │ │
│  │ 8AM daily   │    │             │    │  │ daily_summaries │  │ │
│  │ Mon weekly  │    │ 2. TRANSFORM│    │  │ api_logs        │  │ │
│  └─────────────┘    │   validators│    │  │ pipeline_runs   │  │ │
│                     │             │    │  │ weather_alerts  │  │ │
│  ┌─────────────┐    │ 3. LOAD     │    │  └────────────────┘  │ │
│  │  MONITOR    │    │   database  │    └──────────────────────┘ │
│  │  (monitor)  │    └─────────────┘                            │ │
│  │ Health Check│                        ┌──────────────────────┐│ │
│  │ Dashboards  │    ┌─────────────┐    │     REPORTS          ││ │
│  └─────────────┘    │  REPORTER   │───▶│  daily_YYYY-MM-DD.txt││ │
│                     │  (reporter) │    │  daily_YYYY-MM-DD.html│ │
│                     │ Daily report│    │  analytics_report.txt │ │
│                     │ Analytics   │    └──────────────────────┘ │
│                     └─────────────┘                             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
weather_pipeline/
│
├── main.py                   ← ENTRY POINT — run this!
├── requirements.txt          ← Python dependencies
├── .env.example              ← Template for your settings
├── .env                      ← Your actual settings (create from .env.example)
├── .gitignore                ← Files Git should ignore
│
├── src/                      ← All Python source code
│   ├── config.py             ← All configuration settings
│   ├── database.py           ← Database operations (SQLite + PostgreSQL)
│   ├── api_client.py         ← OpenWeatherMap API communication
│   ├── etl_pipeline.py       ← Main ETL workflow
│   ├── validators.py         ← Data quality & validation
│   ├── reporter.py           ← Report generation
│   ├── scheduler.py          ← Automated job scheduling
│   └── monitor.py            ← System monitoring
│
├── database/
│   └── weather_data.db       ← SQLite database (auto-created)
│
├── logs/
│   ├── pipeline.log          ← All pipeline events
│   └── errors.log            ← Error-only log
│
├── reports/
│   ├── daily_YYYY-MM-DD.txt  ← Daily reports
│   ├── daily_YYYY-MM-DD.html ← HTML daily reports
│   └── analytics_report.txt  ← Analytics answers
│
├── tests/
│   └── test_pipeline.py      ← Unit & integration tests
│
├── docs/
│   └── technical_guide.md    ← Detailed technical documentation
│
└── scripts/
    └── setup.sh              ← Easy setup script
```

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Install Python (if not already installed)
```bash
# Check if Python is installed
python --version    # Should show Python 3.8+

# If not, download from: https://python.org
```

### Step 2: Clone / Download the Project
```bash
# Navigate to where you want the project
cd ~/Documents

# If using Git:
git clone <your-repo-url>
cd weather_pipeline

# OR just download and extract the ZIP
```

### Step 3: Create a Virtual Environment
```bash
# A virtual environment isolates this project's packages
# Think of it like a "separate room" for this project's tools

# Create the virtual environment
python -m venv venv

# Activate it (Windows):
venv\Scripts\activate

# Activate it (Mac/Linux):
source venv/bin/activate

# You'll see (venv) in your terminal — that means it's active!
```

### Step 4: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 5: Set Up Configuration
```bash
# Copy the example .env file
cp .env.example .env

# (Optional) Edit .env with your real OpenWeatherMap API key
# Without a key, it runs in DEMO MODE with realistic fake data
# Get a free key at: https://openweathermap.org/api
```

### Step 6: Run the Full Demo!
```bash
python main.py full
```

This one command will:
1. ✅ Create the database with all 6 tables
2. 📥 Seed 8 cities
3. 🔄 Generate 100 historical weather readings per city (demo data)
4. 🌐 Run a live pipeline collection
5. 📋 Generate TXT, JSON, and HTML reports
6. 📊 Display the monitoring dashboard
7. 📈 Print all 5 analytics results

---

## 📅 Week-by-Week Guide

### Week 1: Database Design & SQL Fundamentals

**What you'll learn:** SQL, relational databases, normalization, indexes

```bash
# Set up the database
python main.py setup

# Look at the database file
ls -la database/

# Explore with SQLite browser (optional GUI tool):
# Download DB Browser for SQLite: https://sqlitebrowser.org/
```

**Key SQL concepts in this project:**
- `CREATE TABLE` — defines table structure
- `INSERT INTO` — adds new records
- `SELECT ... FROM ... WHERE` — retrieves data
- `JOIN` — combines data from multiple tables
- `GROUP BY` — aggregates data for statistics

**Explore the database manually:**
```bash
sqlite3 database/weather_data.db
.tables
SELECT * FROM cities;
SELECT COUNT(*) FROM weather_readings;
.quit
```

---

### Week 2: API Integration

**What you'll learn:** HTTP requests, JSON parsing, error handling, rate limiting

```bash
# Test the API client
python src/api_client.py

# To use a real API:
# 1. Register at https://openweathermap.org
# 2. Get your free API key
# 3. Edit .env: OPENWEATHER_API_KEY=your_key_here
```

**Key concepts:**
- APIs communicate via HTTP (GET, POST, etc.)
- JSON is the standard data format for APIs
- Rate limiting protects API servers from overload
- Retry logic handles temporary network issues

---

### Week 3: ETL Pipeline Development

**What you'll learn:** Data engineering, pipeline design, parallel processing

```bash
# Run the ETL pipeline
python main.py run

# Generate historical data for testing
python main.py backfill 200    # 200 readings per city
```

**ETL explained:**
- **E**xtract → Call the weather API
- **T**ransform → Clean, validate, standardize
- **L**oad → Insert into the database

---

### Week 4: Data Quality & Automation

**What you'll learn:** Validation, error handling, scheduling

```bash
# Run validation tests directly
python src/validators.py

# Run unit tests
pytest tests/ -v

# Run tests with coverage report
pytest tests/ -v --cov=src
```

**Validation rules:**
- Temperature: -90°C to +60°C (physical limits)
- Humidity: 0% to 100%
- Pressure: 870 to 1085 hPa
- Wind: 0 to 113 m/s

---

### Week 5: Analytics & Reporting

**What you'll learn:** SQL analytics, report generation, data storytelling

```bash
# Generate all reports
python main.py report

# View analytics in terminal
python main.py analyze

# Reports are in the reports/ folder
ls reports/
```

---

### Week 6: Deployment & Monitoring

**What you'll learn:** System monitoring, health checks, scheduling

```bash
# View monitoring dashboard
python main.py monitor

# Start the automated scheduler
python main.py schedule
# Press Ctrl+C to stop

# Check the logs
tail -f logs/pipeline.log
```

---

## 📚 Module Documentation

### config.py
Central configuration file. Change settings here, not in individual files.

| Setting | Default | Description |
|---------|---------|-------------|
| `CITIES` | 8 cities | Cities to track |
| `ACTIVE_DB` | `sqlite` | Database type |
| `collection_interval` | 30 min | How often to collect |
| `data_retention_days` | 365 | How long to keep data |

### database.py
Handles all database operations. Supports both SQLite and PostgreSQL.

| Method | Description |
|--------|-------------|
| `initialize_database()` | Creates all tables |
| `seed_cities(cities)` | Adds cities to the database |
| `insert_weather_reading(city_id, data)` | Saves one weather reading |
| `get_temperature_stats(days)` | Analytics: avg/max/min temp per city |
| `get_temperature_trends(city_id, days)` | Day-by-day temperature trend |
| `health_check()` | Tests database connectivity |

### api_client.py
Communicates with OpenWeatherMap. Has a demo mode for testing.

| Method | Description |
|--------|-------------|
| `fetch_weather_for_city(city, country)` | Main method — fetch + parse |
| `get_current_weather(city, country)` | Raw API call |
| `test_connection()` | Tests if API key is valid |

### etl_pipeline.py
Orchestrates the full ETL flow.

| Method | Description |
|--------|-------------|
| `run(cities, parallel)` | Run full pipeline for all cities |
| `run_backfill(num_readings)` | Generate historical demo data |
| `process_one_city(city)` | ETL for a single city |

---

## 🗄 Database Schema

### cities
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment primary key |
| name | TEXT | City name (e.g., "London") |
| country | TEXT | ISO country code (e.g., "GB") |
| latitude | REAL | GPS latitude |
| longitude | REAL | GPS longitude |
| timezone | TEXT | Timezone string |
| is_active | INTEGER | 1=active, 0=disabled |

### weather_readings
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| city_id | INTEGER FK | Links to cities.id |
| temperature | REAL | °C |
| humidity | INTEGER | % |
| pressure | INTEGER | hPa |
| wind_speed | REAL | m/s |
| weather_desc | TEXT | "clear sky", "light rain", etc. |
| data_quality | TEXT | GOOD / WARNING / BAD |
| collected_at | TEXT | ISO timestamp |

### daily_summaries, api_logs, pipeline_runs, weather_alerts
See `src/database.py` for full schema details.

---

## 📊 Analysis Questions & Queries

Run `python main.py analyze` to see all answers printed.

**Q1: Which city has the highest average temperature?**
```sql
SELECT c.name, ROUND(AVG(wr.temperature), 2) AS avg_temp
FROM weather_readings wr
JOIN cities c ON c.id = wr.city_id
WHERE wr.collected_at >= datetime('now', '-30 days')
GROUP BY c.id ORDER BY avg_temp DESC;
```

**Q2: Temperature trends over 30 days**
```sql
SELECT DATE(collected_at) AS date,
       ROUND(AVG(temperature), 2) AS avg_temp
FROM weather_readings WHERE city_id = ?
GROUP BY DATE(collected_at) ORDER BY date;
```

**Q3: Humidity vs Rainfall correlation**
```sql
SELECT c.name, AVG(humidity) AS avg_humidity, SUM(rain_1h) AS total_rain
FROM weather_readings wr JOIN cities c ON c.id = wr.city_id
GROUP BY c.id ORDER BY avg_humidity DESC;
```

**Q4: Seasonal extremes**
```sql
SELECT CASE WHEN strftime('%m', collected_at) IN ('12','01','02') THEN 'Winter'
            WHEN strftime('%m', collected_at) IN ('03','04','05') THEN 'Spring'
            WHEN strftime('%m', collected_at) IN ('06','07','08') THEN 'Summer'
            ELSE 'Autumn' END AS season,
       MAX(temperature) AS max_temp
FROM weather_readings GROUP BY season;
```

**Q5: Peak temperature hours**
```sql
SELECT strftime('%H', collected_at) AS hour,
       ROUND(AVG(temperature), 2) AS avg_temp
FROM weather_readings WHERE city_id = ?
GROUP BY hour ORDER BY avg_temp DESC;
```

---

## 🏢 Enterprise Features (Option 4)

This project is built for **Option 4: Enterprise Version**.

### Multi-Database Support
- **SQLite** (default): Perfect for local development, no server needed
- **PostgreSQL** (production): For cloud deployment, multiple users, high volume

To switch to PostgreSQL:
```bash
# Install PostgreSQL locally or use a cloud service (ElephantSQL - free tier)
pip install psycopg2-binary

# Update .env:
ACTIVE_DB=postgresql
PG_HOST=your-db-host.com
PG_DATABASE=weather_db
PG_USER=weather_user
PG_PASSWORD=your_secure_password
```

### Cloud Deployment Options

**Option A: Heroku (Free tier)**
```bash
pip install gunicorn
echo "worker: python main.py schedule" > Procfile
heroku create your-weather-pipeline
heroku config:set OPENWEATHER_API_KEY=your_key
git push heroku main
```

**Option B: AWS EC2**
```bash
# SSH into your EC2 instance
ssh -i key.pem ubuntu@your-ec2-ip

# Install dependencies
sudo apt-get install python3-pip
pip install -r requirements.txt

# Run as a background service
nohup python main.py schedule &
```

**Option C: Raspberry Pi (always-on home server)**
```bash
# Perfect for running the pipeline 24/7 at home
# Same setup as Linux above
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=src --cov-report=term-missing

# Run a specific test class
pytest tests/test_pipeline.py::TestValidator -v

# Run a specific test
pytest tests/test_pipeline.py::TestDatabase::test_insert_weather_reading -v
```

**Test Coverage Areas:**
- ✅ Database operations (insert, query, health check)
- ✅ Data validation (valid data, invalid ranges, alerts)
- ✅ API client (demo mode, data parsing)
- ✅ ETL pipeline (full run, backfill)
- ✅ Monitor (health check, metrics)

---

## 🚀 Deployment

### Local Automated Scheduling
```bash
# Option 1: Python scheduler (keeps running)
python main.py schedule

# Option 2: System cron job (Linux/Mac)
crontab -e
# Add: */30 * * * * cd /path/to/weather_pipeline && python main.py run
# Add: 0 8 * * * cd /path/to/weather_pipeline && python main.py report
```

### GitHub Actions (CI/CD)
Create `.github/workflows/pipeline.yml` to run on a schedule:
```yaml
on:
  schedule:
    - cron: '*/30 * * * *'   # Every 30 minutes
jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install -r requirements.txt
      - run: python main.py run
        env:
          OPENWEATHER_API_KEY: ${{ secrets.OPENWEATHER_API_KEY }}
```

---

## 🔧 Troubleshooting

### "ModuleNotFoundError: No module named 'requests'"
```bash
pip install -r requirements.txt
```

### "Invalid API Key"
```bash
# Check your .env file
cat .env
# Make sure: OPENWEATHER_API_KEY=your_actual_key
# Or just use demo mode (no key needed)
```

### "Database is locked"
```bash
# Another process is using the database
# Wait a moment and retry, or restart your terminal
```

### Pipeline runs but no data in database
```bash
# Run in verbose mode and check logs
python main.py run
cat logs/pipeline.log
cat logs/errors.log
```

### Tests failing
```bash
# Install test dependencies
pip install pytest pytest-cov

# Make sure you're in the project root directory
cd weather_pipeline
pytest tests/ -v
```

---

## 👨‍💻 Author Notes

This project is designed for **beginners learning data engineering**.
Every file is heavily commented to explain:
- **What** the code does
- **Why** it's structured this way
- **How** to modify it for your needs

**Next steps after completing this project:**
1. Add a web dashboard (Flask or FastAPI)
2. Add more data sources (air quality, UV index)
3. Implement machine learning temperature predictions
4. Deploy to the cloud
5. Add a mobile app notification system

---

*Built with Python 3.8+ | SQLite & PostgreSQL | OpenWeatherMap API*
