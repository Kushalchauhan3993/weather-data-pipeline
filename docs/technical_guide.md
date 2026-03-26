# Weather Pipeline — Technical Documentation

## Architecture Overview
The system follows a layered ETL architecture:
- **Extraction Layer**: api_client.py fetches from OpenWeatherMap
- **Transform Layer**: validators.py cleans and validates data
- **Load Layer**: database.py persists to SQLite/PostgreSQL
- **Orchestration**: etl_pipeline.py coordinates all layers
- **Scheduling**: scheduler.py automates pipeline execution
- **Monitoring**: monitor.py tracks system health

## System Architecture Diagram
```
┌──────────────────────────────────────────────────────────┐
│                  WEATHER PIPELINE SYSTEM                  │
│                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐ │
│  │  SCHEDULER  │───▶│  ETL CORE   │───▶│   DATABASE   │ │
│  │             │    │             │    │              │ │
│  │ Every 30min │    │ 1. EXTRACT  │    │ cities       │ │
│  │ 8AM daily   │    │ 2. TRANSFORM│    │ readings     │ │
│  │ Mon weekly  │    │ 3. LOAD     │    │ alerts       │ │
│  └─────────────┘    └─────────────┘    └──────────────┘ │
│                                                          │
│  ┌─────────────┐    ┌─────────────┐                     │
│  │   MONITOR   │    │  REPORTER   │                     │
│  │ Health check│    │ TXT/JSON    │                     │
│  │ Dashboard   │    │ HTML reports│                     │
│  └─────────────┘    └─────────────┘                     │
└──────────────────────────────────────────────────────────┘
```

## Database Schema

### ER Diagram
```
┌──────────────┐         ┌─────────────────────┐
│    cities    │         │   weather_readings   │
│──────────────│         │─────────────────────│
│ PK id        │────┐    │ PK id               │
│    name      │    └───▶│ FK city_id          │
│    country   │         │    temperature      │
│    latitude  │         │    humidity         │
│    longitude │         │    pressure         │
│    timezone  │         │    wind_speed       │
│    is_active │         │    weather_desc     │
└──────────────┘         │    data_quality     │
        │                │    collected_at     │
        │                └─────────────────────┘
        │
        ├───────────────▶ daily_summaries (FK city_id)
        ├───────────────▶ weather_alerts  (FK city_id)
        └───────────────▶ api_logs        (FK city_id)

pipeline_runs (standalone — no FK)
```

### Table Details
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| cities | City metadata | name, country, lat, lon |
| weather_readings | Raw weather data | temperature, humidity, pressure |
| daily_summaries | Pre-computed stats | avg_temp, max_temp, min_temp |
| api_logs | API call tracking | status_code, response_time_ms |
| pipeline_runs | ETL execution history | status, duration_seconds |
| weather_alerts | Extreme weather | alert_type, severity, value |

## ETL Workflow
```
1. Scheduler triggers every 30 minutes
2. ETLPipeline.run() starts with unique run_id
3. ThreadPoolExecutor spawns 4 parallel workers
4. Each worker runs process_one_city():
   a. EXTRACT  → api_client.fetch_weather_for_city()
   b. TRANSFORM → cleaner.clean() + validator.validate()
   c. LOAD     → db.insert_weather_reading()
5. Results logged to pipeline_runs table
6. Alerts saved to weather_alerts table
```

## API Integration
| Setting | Value |
|---------|-------|
| Provider | OpenWeatherMap |
| Endpoint | GET /data/2.5/weather |
| Auth | API key (query param) |
| Rate limit | 60 calls/minute (free tier) |
| Retry attempts | 3 |
| Timeout | 30 seconds |

## Validation Rules
| Field | Min | Max | Action |
|-------|-----|-----|--------|
| temperature | -90°C | +60°C | Mark BAD |
| humidity | 0% | 100% | Mark BAD |
| pressure | 870hPa | 1085hPa | Mark BAD |
| wind_speed | 0 m/s | 113 m/s | Mark BAD |
| visibility | 0m | 10000m | Warning |

## Alert Thresholds
| Alert | Threshold | Severity |
|-------|-----------|----------|
| EXTREME_HEAT | > 40°C | HIGH |
| EXTREME_COLD | < -20°C | HIGH |
| HIGH_WIND | > 20 m/s | MEDIUM |
| LOW_VISIBILITY | < 1000m | MEDIUM |
| HEAVY_RAIN | > 50mm/hr | HIGH |

## Troubleshooting
| Problem | Cause | Fix |
|---------|-------|-----|
| 401 API error | Invalid key | Check .env file |
| UNHEALTHY status | Pipeline not running | python main.py run |
| Module not found | Wrong directory | cd into weather_pipeline |
| Demo mode stuck | enable_demo_mode=True | Set False in config.py |
| New key not working | Key not activated | Wait 10 minutes |

## Deployment Options
- **Local**: `python main.py schedule`
- **Heroku**: Push with Procfile
- **AWS EC2**: `nohup python main.py schedule &`
- **PostgreSQL**: Set `ACTIVE_DB=postgresql` in .env
