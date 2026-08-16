from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    DataSource,
    NormalizedWeatherMetric,
    Prediction,
    PredictionEvaluation,
    RawWeatherRecord,
    UpdateHistory,
)
from app.services.refresh import _location_snapshot, ensure_data_sources
from app.services.weather.normalize import normalize_open_meteo
from app.services.weather.open_meteo import OpenMeteoClient


RAIN_THRESHOLD_MM = 0.1


@dataclass(frozen=True)
class EvaluationCalculation:
    actual_rain: bool
    status: str
    absolute_probability_error: float
    brier_score: float


def calculate_evaluation(predicted_probability_pct: float, predicted_class: str, actual_rain_mm: float) -> EvaluationCalculation:
    actual_rain = actual_rain_mm >= RAIN_THRESHOLD_MM
    predicted_rain = predicted_class == "rain"
    observed = 1.0 if actual_rain else 0.0
    probability = predicted_probability_pct / 100.0
    return EvaluationCalculation(
        actual_rain=actual_rain,
        status="correct" if predicted_rain == actual_rain else "incorrect",
        absolute_probability_error=round(abs(probability - observed), 4),
        brier_score=round((probability - observed) ** 2, 4),
    )


def evaluate_prediction(db: Session, prediction_id: int) -> PredictionEvaluation:
    prediction = db.scalar(
        select(Prediction)
        .options(joinedload(Prediction.location), joinedload(Prediction.evaluation))
        .where(Prediction.id == prediction_id)
    )
    if prediction is None:
        raise LookupError("Prediction not found")

    evaluation = prediction.evaluation
    if evaluation is None:
        evaluation = PredictionEvaluation(prediction_id=prediction.id, status="pending")
        db.add(evaluation)
        db.flush()
    if evaluation.status in {"correct", "incorrect"}:
        return evaluation

    local_today = datetime.now(timezone.utc).astimezone(ZoneInfo(prediction.location.timezone)).date()
    if prediction.target_date >= local_today:
        return evaluation

    ensure_data_sources(db)
    actual_source = db.scalar(select(DataSource).where(DataSource.code == "open_meteo_actual"))
    assert actual_source is not None

    actual_metric = db.scalar(
        select(NormalizedWeatherMetric)
        .join(RawWeatherRecord)
        .where(
            RawWeatherRecord.location_id == prediction.location_id,
            RawWeatherRecord.source_id == actual_source.id,
            RawWeatherRecord.target_date == prediction.target_date,
            RawWeatherRecord.is_success.is_(True),
        )
        .order_by(RawWeatherRecord.fetched_at.desc())
        .limit(1)
    )

    started = datetime.now(timezone.utc)
    error: str | None = None
    if actual_metric is None:
        snapshot = _location_snapshot(prediction.location)
        db.rollback()
        result = OpenMeteoClient().fetch_actual(snapshot, prediction.target_date)
        ensure_data_sources(db)
        actual_source = db.scalar(select(DataSource).where(DataSource.code == "open_meteo_actual"))
        assert actual_source is not None
        raw = RawWeatherRecord(
            location_id=prediction.location_id,
            source_id=actual_source.id,
            target_date=prediction.target_date,
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
        if result.is_success and result.payload is not None:
            try:
                normalized = normalize_open_meteo(result.payload, prediction.target_date)
                actual_metric = NormalizedWeatherMetric(
                    raw_record_id=raw.id,
                    target_date=prediction.target_date,
                    precipitation_probability_pct=None,
                    rain_amount_mm=normalized.rain_amount_mm,
                    humidity_pct=normalized.humidity_pct,
                    cloud_cover_pct=normalized.cloud_cover_pct,
                    pressure_hpa=normalized.pressure_hpa,
                    temperature_c=normalized.temperature_c,
                    wind_speed_kmh=normalized.wind_speed_kmh,
                    rain_hours=normalized.rain_hours,
                    completeness=normalized.completeness,
                )
                db.add(actual_metric)
                db.flush()
            except (ValueError, TypeError, KeyError) as exc:
                raw.is_success = False
                raw.error_message = f"NormalizationError: {exc}"
                error = raw.error_message
        else:
            error = result.error_message or "Actual weather request failed"

    evaluation = db.scalar(select(PredictionEvaluation).where(PredictionEvaluation.prediction_id == prediction_id))
    if evaluation is None:
        evaluation = PredictionEvaluation(prediction_id=prediction_id, status="pending")
        db.add(evaluation)
        db.flush()

    if actual_metric is not None and actual_metric.rain_amount_mm is not None:
        calculated = calculate_evaluation(
            prediction.rain_probability_pct,
            prediction.prediction_class,
            actual_metric.rain_amount_mm,
        )
        evaluation.actual_metric_id = actual_metric.id
        evaluation.actual_rain = calculated.actual_rain
        evaluation.actual_rain_mm = actual_metric.rain_amount_mm
        evaluation.absolute_probability_error = calculated.absolute_probability_error
        evaluation.brier_score = calculated.brier_score
        evaluation.status = calculated.status
        evaluation.evaluated_at = datetime.now(timezone.utc)
        evaluation.error_message = None
    else:
        evaluation.error_message = error or "Actual rain amount is unavailable"

    db.add(
        UpdateHistory(
            location_id=prediction.location_id,
            prediction_id=prediction.id,
            job_type="prediction_evaluation",
            status="success" if evaluation.status in {"correct", "incorrect"} else "failed",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            details={"error": evaluation.error_message} if evaluation.error_message else None,
        )
    )
    db.commit()
    db.refresh(evaluation)
    return evaluation
