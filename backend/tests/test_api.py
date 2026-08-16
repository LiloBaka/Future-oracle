from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.locations import router as locations_router
from app.db import Base, get_db
from app.models import Location


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)


def override_db():
    with Session(engine) as db:
        yield db


app = FastAPI()
app.dependency_overrides[get_db] = override_db
app.include_router(locations_router, prefix="/api")
client = TestClient(app)


def test_list_locations_api():
    with Session(engine) as db:
        db.query(Location).delete()
        db.add(Location(name="Berlin", country_code="DE", latitude=52.52, longitude=13.405, timezone="Europe/Berlin"))
        db.commit()

    response = client.get("/api/locations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Berlin"


def test_prediction_detail_api_traceability():
    from datetime import date, datetime, timezone

    from app.api.routes.predictions import router as predictions_router
    from app.models import (
        DataSource,
        NormalizedWeatherMetric,
        Prediction,
        PredictionEvaluation,
        PredictionFactor,
        PredictionInput,
        RawWeatherRecord,
    )

    if not any(getattr(route, "path", "").startswith("/predictions") for route in app.routes):
        app.include_router(predictions_router, prefix="/api")

    with Session(engine) as db:
        db.query(PredictionFactor).delete()
        db.query(PredictionInput).delete()
        db.query(PredictionEvaluation).delete()
        db.query(Prediction).delete()
        db.query(NormalizedWeatherMetric).delete()
        db.query(RawWeatherRecord).delete()
        db.query(DataSource).delete()
        db.query(Location).delete()
        location = Location(name="Berlin", country_code="DE", latitude=52.52, longitude=13.405, timezone="Europe/Berlin")
        source = DataSource(code="open_meteo_gfs", name="Open-Meteo", provider="Open-Meteo", kind="forecast", endpoint="https://example.test")
        db.add_all([location, source])
        db.flush()
        raw = RawWeatherRecord(
            location_id=location.id,
            source_id=source.id,
            target_date=date(2026, 8, 17),
            fetched_at=datetime(2026, 8, 16, 12, tzinfo=timezone.utc),
            http_status=200,
            is_success=True,
            payload={"sample": True},
        )
        db.add(raw)
        db.flush()
        metric = NormalizedWeatherMetric(
            raw_record_id=raw.id,
            target_date=date(2026, 8, 17),
            precipitation_probability_pct=70,
            rain_amount_mm=3,
            humidity_pct=80,
            cloud_cover_pct=70,
            pressure_hpa=1010,
            temperature_c=18,
            wind_speed_kmh=12,
            rain_hours=3,
            completeness=1.0,
        )
        db.add(metric)
        db.flush()
        prediction = Prediction(
            location_id=location.id,
            target_date=date(2026, 8, 17),
            rain_probability_pct=57.4,
            prediction_class="rain",
            confidence_pct=89.2,
            risk_score=0.225,
            risk_level="low",
            decision_threshold_pct=50,
            algorithm_version="1.0",
            explanation="traceable",
        )
        db.add(prediction)
        db.flush()
        db.add_all([
            PredictionInput(prediction_id=prediction.id, normalized_metric_id=metric.id),
            PredictionFactor(
                prediction_id=prediction.id,
                code="open_probability",
                label="Open probability",
                raw_value=70,
                normalized_value=0.7,
                base_weight=0.35,
                effective_weight=0.35,
                contribution=0.245,
                details={"source_metric_id": metric.id},
            ),
            PredictionEvaluation(prediction_id=prediction.id, status="pending"),
        ])
        db.commit()
        prediction_id = prediction.id
        raw_id = raw.id
        metric_id = metric.id

    response = client.get(f"/api/predictions/{prediction_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["sources"][0]["raw_record_id"] == raw_id
    assert body["sources"][0]["normalized_metric_id"] == metric_id
    assert body["factors"][0]["contribution"] == 0.245
    assert body["evaluation"]["status"] == "pending"
