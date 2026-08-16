from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DataSource,
    Location,
    NormalizedWeatherMetric,
    Prediction,
    PredictionEvaluation,
    PredictionFactor,
    PredictionInput,
    RawWeatherRecord,
    UpdateHistory,
)
from app.services.prediction import (
    ALGORITHM_VERSION,
    DECISION_THRESHOLD_PCT,
    MetricInput,
    calculate_prediction,
)
from app.services.weather.common import FetchResult, LocationSnapshot, NormalizedMetrics
from app.services.weather.met_norway import MET_URL, MetNorwayClient
from app.services.weather.normalize import normalize_met_norway, normalize_open_meteo
from app.services.weather.open_meteo import ARCHIVE_URL, GFS_URL, OpenMeteoClient


SOURCE_DEFINITIONS = [
    {
        "code": "open_meteo_gfs",
        "name": "Open-Meteo NOAA GFS",
        "provider": "Open-Meteo / NOAA",
        "kind": "forecast",
        "endpoint": GFS_URL,
        "description": "Global NOAA GFS forecast exposed by Open-Meteo.",
    },
    {
        "code": "met_norway",
        "name": "MET Norway Locationforecast",
        "provider": "MET Norway",
        "kind": "forecast",
        "endpoint": MET_URL,
        "description": "MET Norway Locationforecast 2.0 compact endpoint.",
    },
    {
        "code": "open_meteo_actual",
        "name": "Open-Meteo ECMWF historical weather",
        "provider": "Open-Meteo / ECMWF",
        "kind": "actual",
        "endpoint": ARCHIVE_URL,
        "description": "Historical/reanalysis weather used as the evaluation ground-truth proxy.",
    },
]


def ensure_data_sources(db: Session) -> None:
    existing = {row.code for row in db.scalars(select(DataSource)).all()}
    changed = False
    for definition in SOURCE_DEFINITIONS:
        if definition["code"] not in existing:
            db.add(DataSource(**definition))
            changed = True
    if changed:
        db.commit()


def _location_snapshot(location: Location) -> LocationSnapshot:
    return LocationSnapshot(
        id=location.id,
        name=location.name,
        latitude=location.latitude,
        longitude=location.longitude,
        timezone=location.timezone,
    )


def _persist_fetch(
    db: Session,
    location_id: int,
    source: DataSource,
    result: FetchResult,
    normalizer,
) -> NormalizedWeatherMetric | None:
    raw = RawWeatherRecord(
        location_id=location_id,
        source_id=source.id,
        target_date=result.target_date,
        fetched_at=result.fetched_at,
        http_status=result.http_status,
        is_success=result.is_success,
        payload=result.payload,
        error_message=result.error_message,
        response_last_modified=result.last_modified,
        response_expires=result.expires,
    )
    db.add(raw)
    db.flush()

    if not result.is_success or result.payload is None:
        return None

    try:
        normalized: NormalizedMetrics = normalizer(result.payload)
    except (ValueError, TypeError, KeyError) as exc:
        raw.is_success = False
        raw.error_message = f"NormalizationError: {exc}"
        return None

    metric = NormalizedWeatherMetric(
        raw_record_id=raw.id,
        target_date=result.target_date,
        precipitation_probability_pct=normalized.precipitation_probability_pct,
        rain_amount_mm=normalized.rain_amount_mm,
        humidity_pct=normalized.humidity_pct,
        cloud_cover_pct=normalized.cloud_cover_pct,
        pressure_hpa=normalized.pressure_hpa,
        temperature_c=normalized.temperature_c,
        wind_speed_kmh=normalized.wind_speed_kmh,
        rain_hours=normalized.rain_hours,
        completeness=normalized.completeness,
    )
    db.add(metric)
    db.flush()
    return metric


def refresh_location(db: Session, location_id: int) -> tuple[Prediction | None, dict[str, str]]:
    started = datetime.now(timezone.utc)
    location = db.get(Location, location_id)
    if location is None:
        raise LookupError("Location not found")

    snapshot = _location_snapshot(location)
    local_today = datetime.now(timezone.utc).astimezone(ZoneInfo(snapshot.timezone)).date()
    target_date = local_today.fromordinal(local_today.toordinal() + 1)

    # Finish the read transaction before external network calls.
    db.rollback()

    open_result = OpenMeteoClient().fetch_forecast(snapshot, target_date)
    met_result = MetNorwayClient().fetch_forecast(snapshot, target_date)

    ensure_data_sources(db)
    sources = {row.code: row for row in db.scalars(select(DataSource)).all()}

    open_metric = _persist_fetch(
        db,
        snapshot.id,
        sources["open_meteo_gfs"],
        open_result,
        lambda payload: normalize_open_meteo(payload, target_date),
    )
    met_metric = _persist_fetch(
        db,
        snapshot.id,
        sources["met_norway"],
        met_result,
        lambda payload: normalize_met_norway(payload, target_date, snapshot.timezone),
    )
    db.commit()

    source_errors: dict[str, str] = {}
    if open_metric is None:
        source_errors["open_meteo_gfs"] = open_result.error_message or "response could not be normalized"
    if met_metric is None:
        source_errors["met_norway"] = met_result.error_message or "response could not be normalized"

    metrics_with_codes = [
        ("open_meteo_gfs", open_metric),
        ("met_norway", met_metric),
    ]
    available = [(code, metric) for code, metric in metrics_with_codes if metric is not None]

    prediction: Prediction | None = None
    status = "failed"
    details: dict = {"target_date": target_date.isoformat(), "source_errors": source_errors}

    if available:
        inputs = [
            MetricInput(
                source_code=code,
                metric_id=metric.id,
                fetched_at=metric.raw_record.fetched_at,
                precipitation_probability_pct=metric.precipitation_probability_pct,
                rain_amount_mm=metric.rain_amount_mm,
                humidity_pct=metric.humidity_pct,
                cloud_cover_pct=metric.cloud_cover_pct,
                rain_hours=metric.rain_hours,
            )
            for code, metric in available
        ]
        try:
            calculation = calculate_prediction(inputs)
            prediction = Prediction(
                location_id=snapshot.id,
                target_date=target_date,
                rain_probability_pct=calculation.rain_probability_pct,
                prediction_class=calculation.prediction_class,
                confidence_pct=calculation.confidence_pct,
                risk_score=calculation.risk_score,
                risk_level=calculation.risk_level,
                decision_threshold_pct=DECISION_THRESHOLD_PCT,
                algorithm_version=ALGORITHM_VERSION,
                explanation=calculation.explanation,
            )
            db.add(prediction)
            db.flush()
            for _, metric in available:
                db.add(PredictionInput(prediction_id=prediction.id, normalized_metric_id=metric.id))
            for factor in calculation.factors:
                db.add(
                    PredictionFactor(
                        prediction_id=prediction.id,
                        code=factor.code,
                        label=factor.label,
                        raw_value=factor.raw_value,
                        normalized_value=factor.normalized_value,
                        base_weight=factor.base_weight,
                        effective_weight=factor.effective_weight,
                        contribution=factor.contribution,
                        details=factor.details,
                    )
                )
            db.add(PredictionEvaluation(prediction_id=prediction.id, status="pending"))
            status = "success" if not source_errors else "partial"
            details["diagnostics"] = calculation.diagnostics
        except ValueError as exc:
            details["prediction_error"] = str(exc)
            status = "failed"

    history = UpdateHistory(
        location_id=snapshot.id,
        prediction_id=prediction.id if prediction else None,
        job_type="forecast_refresh",
        status=status,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        details=details,
    )
    db.add(history)
    db.commit()
    if prediction:
        db.refresh(prediction)
    return prediction, source_errors
