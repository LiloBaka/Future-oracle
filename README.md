# Future Oracle

A small full-stack service that answers one question:

> **Will it rain tomorrow in the selected city?**

The project is intentionally deterministic. It does not ask an LLM to predict weather. Every result is calculated from stored numeric weather data and can be traced through the database:

```text
External API
  -> raw_weather_records
  -> normalized_weather_metrics
  -> prediction_inputs
  -> prediction_factors
  -> predictions
  -> prediction_evaluations
```

The goal is not meteorological perfection. The goal is a clear, testable integration/backend prototype that demonstrates REST API design, SQL modelling, external APIs, error handling, business rules, automation and post-factum evaluation.

## Stack

- Python 3.13
- FastAPI
- PostgreSQL 16
- SQLAlchemy 2
- Alembic
- Pydantic
- httpx
- APScheduler
- pytest
- React + TypeScript + Vite
- Docker Compose

## Weather sources

### 1. Open-Meteo NOAA GFS

Forecast endpoint:

```text
https://api.open-meteo.com/v1/gfs
```

The service requests hourly:

- `precipitation_probability`
- `rain`
- `relative_humidity_2m`
- `cloud_cover`
- `pressure_msl`
- `temperature_2m`
- `wind_speed_10m`

Official docs: https://open-meteo.com/en/docs/gfs-api

Open-Meteo is used specifically through its GFS endpoint instead of the automatic "Best Match" endpoint. That keeps this source tied to NOAA GFS rather than silently blending different providers.

### 2. MET Norway Locationforecast 2.0

Endpoint:

```text
https://api.met.no/weatherapi/locationforecast/2.0/compact
```

The adapter uses:

- `precipitation_amount`
- `symbol_code`
- `relative_humidity`
- `cloud_area_fraction`
- `air_pressure_at_sea_level`
- `air_temperature`
- `wind_speed`

Official docs:

- https://docs.api.met.no/doc/locationforecast/HowTO.html
- https://docs.api.met.no/doc/locationforecast/datamodel.html

MET Norway requires a meaningful identifying `User-Agent`. Set `MET_USER_AGENT` in `.env` to a real project/contact value before using the service.

### Geocoding

City names are converted to latitude/longitude/timezone through Open-Meteo Geocoding API. Geocoding is a supporting integration, not one of the two forecast sources.

### Evaluation data

Past weather is fetched through Open-Meteo Historical Weather API using ECMWF IFS data.

This is explicitly treated as a **historical/reanalysis ground-truth proxy**, not a direct weather-station observation. For a production system I would prefer a station/radar observation source where global coverage and licensing are acceptable.

## Definition of “rain”

A forecast class is:

```text
RAIN     if final_probability >= 50%
NO_RAIN  otherwise
```

For evaluation, the actual event is:

```text
actual_rain = historical rain amount >= 0.1 mm/day
```

The 0.1 mm threshold avoids treating tiny numerical traces as a meaningful rain event.

## Database schema

### `locations`

Cities being tracked.

Important fields:

- `id` PK
- `name`
- `country_code`
- `latitude`
- `longitude`
- `timezone`
- `is_active`
- timestamps

DB checks protect valid coordinate ranges.

### `data_sources`

Metadata for weather providers/endpoints.

Important fields:

- `id` PK
- `code` unique
- `provider`
- `kind` (`forecast` / `actual`)
- `endpoint`

### `raw_weather_records`

The exact external response before business normalization.

Important fields:

- `location_id` FK
- `source_id` FK
- `target_date`
- `fetched_at`
- HTTP status
- success flag
- JSON payload
- error message
- `Last-Modified` / `Expires` when supplied

Failed responses are recorded too, so refresh history is auditable.

### `normalized_weather_metrics`

One normalized daily metric row per successful raw record.

Fields include:

- precipitation probability
- rain amount
- humidity
- cloud cover
- pressure
- temperature
- wind speed
- rainy hours
- completeness

The row has a one-to-one FK to the raw record.

### `predictions`

Immutable forecast result.

Each refresh creates a new prediction instead of modifying the previous prediction. That gives a real history of what the system predicted at each point in time.

Fields include:

- final rain probability
- rain/no-rain class
- confidence
- risk score + risk level
- algorithm version
- explanation
- target date

### `prediction_inputs`

Relational link:

```text
prediction -> normalized metric -> raw record -> data source
```

This table is central to traceability.

### `prediction_factors`

Stores every factor used in the score:

- raw value
- normalized value
- configured/base weight
- effective weight after missing-data reweighting
- contribution to final score
- related metric IDs/details

### `prediction_evaluations`

One-to-one evaluation row for each prediction.

Status:

- `pending`
- `correct`
- `incorrect`

Also stores actual rain amount, absolute probability error and Brier score.

### `update_history`

Audit trail for automatic/manual refreshes and evaluations.

Statuses:

- `success`
- `partial`
- `failed`

## Prediction algorithm

Algorithm version: `1.0`.

The factors and base weights are:

| Factor | Weight | Normalization |
|---|---:|---|
| Open-Meteo precipitation probability | 0.35 | `p / 100` |
| Open-Meteo expected rain amount | 0.15 | `min(mm / 5, 1)` |
| MET Norway expected rain amount | 0.25 | `min(mm / 5, 1)` |
| MET Norway rainy hours | 0.10 | `min(hours / 6, 1)` |
| Mean relative humidity | 0.08 | `clamp((humidity - 60) / 40, 0, 1)` |
| Mean cloud cover | 0.07 | `cloud / 100` |

Base weights sum to `1.00`.

The main signals are provider precipitation/rain data. Humidity and cloud cover are intentionally only supporting signals so they cannot dominate the forecast.

### Missing fields / graceful degradation

Only available factors are used. Their weights are renormalized:

```text
effective_weight_i = base_weight_i / sum(available_base_weights)
```

Prediction is refused if less than `0.35` of the configured factor weight is available.

This means one source may still produce a degraded forecast, but missing source data is reflected in confidence and risk.

## Fully worked example

Assume the stored normalized values are:

```text
Open-Meteo precipitation probability = 70%
Open-Meteo rain amount              = 3.0 mm
MET Norway rain amount               = 2.0 mm
MET Norway rainy hours               = 3 h
Average humidity                     = 80%
Average cloud cover                  = 70%
```

Normalize:

```text
Open probability = 70 / 100 = 0.70
Open rain amount = 3 / 5    = 0.60
MET rain amount  = 2 / 5    = 0.40
MET rain hours   = 3 / 6    = 0.50
Humidity         = (80-60)/40 = 0.50
Cloud cover      = 70/100     = 0.70
```

Apply weights:

```text
0.70 * 0.35 = 0.245
0.60 * 0.15 = 0.090
0.40 * 0.25 = 0.100
0.50 * 0.10 = 0.050
0.50 * 0.08 = 0.040
0.70 * 0.07 = 0.049
--------------------
Total           = 0.574
```

Final probability:

```text
57.4%
```

Therefore:

```text
Prediction = RAIN
```

because `57.4 >= 50`.

The exact same example is covered by `tests/test_prediction.py`.

## Confidence

Confidence is deliberately not the same as rain probability.

```text
confidence =
    0.45 * source_agreement
  + 0.35 * factor_coverage
  + 0.20 * freshness
```

### Source agreement

A diagnostic rain score is calculated per forecast source.

Open-Meteo:

```text
0.70 * probability_factor + 0.30 * rain_amount_factor
```

MET Norway:

```text
0.70 * rain_amount_factor + 0.30 * rain_hours_factor
```

Then:

```text
agreement = 1 - abs(open_score - met_score)
```

If only one source is available, agreement is deliberately degraded to `0.35`.

### Coverage

```text
coverage = sum(base weights of factors that were actually available)
```

### Freshness

Each source decays linearly over 12 hours:

```text
freshness = clamp(1 - age_hours / 12, 0, 1)
```

The mean is used for available inputs.

### Example confidence

From the worked example:

```text
Open score = 0.70*0.70 + 0.30*0.60 = 0.67
MET score  = 0.70*0.40 + 0.30*0.50 = 0.43
Agreement  = 1 - |0.67 - 0.43|     = 0.76
Coverage   = 1.00
Freshness  = 1.00
```

```text
confidence = 0.45*0.76 + 0.35*1 + 0.20*1
           = 0.892
           = 89.2%
```

## Risk

Risk is the estimated structural risk that the binary forecast is unreliable.

```text
risk =
    0.35 * disagreement
  + 0.25 * missing_factor_weight
  + 0.20 * staleness
  + 0.20 * borderline_result
```

Where:

```text
disagreement         = 1 - agreement
missing_factor_weight = 1 - coverage
staleness             = 1 - freshness
borderline_result     = 1 - clamp(abs(probability - 50) / 25, 0, 1)
```

Risk level:

```text
0.00 <= risk < 0.30  -> LOW
0.30 <= risk < 0.60  -> MEDIUM
0.60 <= risk <= 1.00 -> HIGH
```

For the worked example:

```text
borderline = 1 - |57.4 - 50|/25 = 0.704
risk = 0.35*0.24 + 0.25*0 + 0.20*0 + 0.20*0.704
     = 0.2248
     ~= 0.225
Risk = LOW
```

## Evaluation

When the forecast date has passed, the scheduler or manual endpoint obtains historical weather data.

```text
actual_rain = actual_rain_mm >= 0.1
```

The stored predicted class is compared with the actual class:

```text
pending -> correct / incorrect
```

Two probability metrics are saved:

```text
absolute_probability_error = |predicted_probability - actual_binary|
Brier score                = (predicted_probability - actual_binary)^2
```

Example:

```text
prediction = 72% RAIN
actual = rain
absolute error = |0.72 - 1| = 0.28
Brier score = (0.72 - 1)^2 = 0.0784
```

## REST API

Base URL:

```text
http://localhost:8000/api
```

### Locations

```text
GET  /locations
POST /locations
POST /locations/{id}/refresh
GET  /locations/{id}/forecast
```

Create location request:

```json
{
  "query": "Berlin"
}
```

`POST /locations/{id}/refresh` fetches both providers, saves raw responses, normalizes successful inputs and creates a prediction.

If one source fails, a partial/degraded prediction may still be returned. If usable factor coverage is too low, the endpoint returns `503`.

### Predictions

```text
GET  /predictions
GET  /predictions/{id}
GET  /predictions/{id}/factors
GET  /predictions/{id}/evaluation
POST /predictions/{id}/evaluate
GET  /updates
```

FastAPI Swagger UI:

```text
http://localhost:8000/docs
```

## Error handling

### One forecast API fails

- failed raw record is saved with HTTP/error information;
- successful source is normalized;
- prediction may be calculated if factor coverage is sufficient;
- confidence decreases;
- risk increases;
- update status becomes `partial`.

### Both forecast APIs fail

- both failures are persisted;
- no fabricated prediction is created;
- refresh returns HTTP `503`.

### Timeout / network failure

`httpx` timeout/network errors are converted to failed raw records rather than silently swallowed.

### Invalid JSON / missing fields

Raw payload remains stored. Normalization failure is attached to the raw record as `NormalizationError`.

### Rate limit / HTTP error

Status code and a bounded error body are persisted. MET Norway 403/429 therefore remains visible in the trace.

### Database failure

Global SQLAlchemy errors are exposed as HTTP `503` with a generic message; full exceptions go to application logs.

### Strong disagreement

A large gap between provider diagnostic scores directly lowers `source_agreement`, lowering confidence and raising risk.

## Automation

APScheduler runs inside the single demo backend process:

```text
every 3 hours -> refresh active locations
every 6 hours -> evaluate due predictions
```

This is intentionally simple for a test assignment.

Important production trade-off: an in-process scheduler must not be started independently in several web workers. A production deployment would move these jobs to a dedicated scheduler/worker or platform cron.

## Frontend

The React dashboard intentionally focuses on explaining backend behavior:

1. city selector / add city;
2. current prediction card;
3. source metrics and scoring factor traceability;
4. prediction/evaluation history.

The main card shows:

- City
- target date
- Rain / No Rain
- probability
- confidence
- risk
- last update
- algorithm version

The trace section shows raw record IDs, normalized metric IDs and each factor contribution.

## Run with Docker

### 1. Configure environment

Linux/macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit:

```text
MET_USER_AGENT=FutureOracle/1.0 <your real GitHub URL or contact>
```

### 2. Start

```bash
docker compose up --build
```

Open:

```text
Frontend: http://localhost:5173
API docs: http://localhost:8000/docs
Health:   http://localhost:8000/health
```

Alembic migrations run automatically before the backend starts.

Stop:

```bash
docker compose down
```

Remove DB volume too:

```bash
docker compose down -v
```

## Local backend without Docker

A local PostgreSQL instance is required.

```bash
cd backend
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then:

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## Tests

Backend:

```bash
cd backend
pytest -q
```

Current repository test set covers:

- Open-Meteo normalization;
- MET Norway normalization;
- exact deterministic scoring math;
- confidence/risk with one missing source;
- stale data behavior;
- evaluation math;
- basic locations API;
- prediction traceability API response.

The test suite intentionally does not chase 100% coverage.

## Repository structure

```text
future-oracle/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── services/weather/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── presenters.py
│   │   ├── schemas.py
│   │   ├── scheduler.py
│   │   └── main.py
│   └── tests/
├── frontend/
│   └── src/
├── docker-compose.yml
├── .env.example
└── README.md
```

## AI usage

AI-assisted development was used as an engineering aid, not as the forecasting engine.

Appropriate uses included:

- discussing architecture alternatives;
- producing/refining boilerplate;
- checking edge cases;
- reviewing scoring formulas;
- suggesting test cases;
- documentation assistance.

The forecast probability, confidence, risk and evaluation are deterministic Python code. They do not call an LLM.

Architectural choices, manual review, test execution, integration decisions and final responsibility remain with the developer.

## Trade-offs

### Why no ML?

There is no training dataset or calibration work in the assignment. A transparent weighted score is easier to defend and audit. If enough evaluation history accumulated, the next step would be to calibrate coefficients from data rather than add a complex model immediately.

### Why no Redis/Celery/Kafka?

The workload is tiny and periodic. They would add operational complexity without demonstrating a necessary skill for this prototype.

### Why synchronous SQLAlchemy/httpx?

The service has low concurrency and very small traffic. Sync code is easier to review and avoids fake/incorrect async. External fetches are performed before short write transactions where practical.

### Why immutable predictions?

Overwriting a prediction would damage auditability. Keeping each refresh allows the reviewer to reproduce what inputs led to a particular historical result.

### Why not authentication?

Authentication is unrelated to the core assignment. Adding a full auth flow would increase scope without improving the weather prediction demonstration.

## What I would improve next

With additional time, in this order:

1. add an independent observation/station source for evaluation;
2. cache/reuse MET Norway responses using `Expires` / `Last-Modified` more aggressively;
3. add adapter-level HTTP tests with mocked responses;
4. add a dedicated scheduler process for multi-worker deployment;
5. collect evaluation history and calibrate the factor weights empirically;
6. add pagination to large prediction/update histories;
7. add CI for `pytest` + frontend build.

## Suggested Git history

A credible implementation sequence:

```text
chore: initialize future oracle project
feat: add postgres models and alembic migration
feat: integrate open meteo gfs forecast
feat: integrate met norway location forecast
feat: normalize provider weather data
feat: add deterministic prediction scoring
feat: calculate confidence and forecast risk
feat: persist prediction traceability factors
feat: add forecast refresh api
feat: evaluate historical predictions
feat: add scheduled refresh and evaluation jobs
test: cover normalization and prediction math
test: add api traceability coverage
feat: add react forecast dashboard
docs: document architecture and algorithm
```
