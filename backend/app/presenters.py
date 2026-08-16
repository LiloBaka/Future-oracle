from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import NormalizedWeatherMetric, Prediction, PredictionInput, RawWeatherRecord
from app.schemas import EvaluationRead, FactorRead, LocationRead, PredictionRead, SourceMetricRead


def prediction_query():
    return select(Prediction).options(
        joinedload(Prediction.location),
        selectinload(Prediction.factors),
        joinedload(Prediction.evaluation),
        selectinload(Prediction.inputs)
        .joinedload(PredictionInput.metric)
        .joinedload(NormalizedWeatherMetric.raw_record)
        .joinedload(RawWeatherRecord.source),
    )


def load_prediction(db: Session, prediction_id: int) -> Prediction | None:
    return db.scalar(prediction_query().where(Prediction.id == prediction_id))


def to_prediction_read(prediction: Prediction) -> PredictionRead:
    sources = []
    for item in prediction.inputs:
        metric = item.metric
        raw = metric.raw_record
        sources.append(
            SourceMetricRead(
                source_code=raw.source.code,
                raw_record_id=raw.id,
                normalized_metric_id=metric.id,
                fetched_at=raw.fetched_at,
                precipitation_probability_pct=metric.precipitation_probability_pct,
                rain_amount_mm=metric.rain_amount_mm,
                humidity_pct=metric.humidity_pct,
                cloud_cover_pct=metric.cloud_cover_pct,
                pressure_hpa=metric.pressure_hpa,
                temperature_c=metric.temperature_c,
                wind_speed_kmh=metric.wind_speed_kmh,
                rain_hours=metric.rain_hours,
                completeness=metric.completeness,
            )
        )

    evaluation = None
    if prediction.evaluation is not None:
        evaluation = EvaluationRead.model_validate(prediction.evaluation, from_attributes=True)

    return PredictionRead(
        id=prediction.id,
        location=LocationRead.model_validate(prediction.location),
        target_date=prediction.target_date,
        rain_probability_pct=prediction.rain_probability_pct,
        prediction_class=prediction.prediction_class,
        confidence_pct=prediction.confidence_pct,
        risk_score=prediction.risk_score,
        risk_level=prediction.risk_level,
        decision_threshold_pct=prediction.decision_threshold_pct,
        algorithm_version=prediction.algorithm_version,
        explanation=prediction.explanation,
        created_at=prediction.created_at,
        factors=[FactorRead.model_validate(item) for item in prediction.factors],
        sources=sources,
        evaluation=evaluation,
    )
