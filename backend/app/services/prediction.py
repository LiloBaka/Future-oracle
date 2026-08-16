from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


ALGORITHM_VERSION = "1.0"
DECISION_THRESHOLD_PCT = 50.0


@dataclass(frozen=True)
class MetricInput:
    source_code: str
    metric_id: int
    fetched_at: datetime
    precipitation_probability_pct: float | None
    rain_amount_mm: float | None
    humidity_pct: float | None
    cloud_cover_pct: float | None
    rain_hours: float | None


@dataclass(frozen=True)
class FactorCalculation:
    code: str
    label: str
    raw_value: float | None
    normalized_value: float
    base_weight: float
    effective_weight: float
    contribution: float
    details: dict


@dataclass(frozen=True)
class PredictionCalculation:
    rain_probability_pct: float
    prediction_class: str
    confidence_pct: float
    risk_score: float
    risk_level: str
    explanation: str
    factors: list[FactorCalculation]
    diagnostics: dict[str, float]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(value, high))


def normalize_probability(value_pct: float) -> float:
    return clamp(value_pct / 100.0)


def normalize_rain_amount(value_mm: float) -> float:
    # 0 mm -> 0; 5+ mm/day -> maximum rain signal.
    return clamp(value_mm / 5.0)


def normalize_humidity(value_pct: float) -> float:
    # Below 60% is a weak rain signal; 100% maps to 1.
    return clamp((value_pct - 60.0) / 40.0)


def normalize_cloud_cover(value_pct: float) -> float:
    return clamp(value_pct / 100.0)


def normalize_rain_hours(value_hours: float) -> float:
    # Six or more rainy hours are enough to saturate this supporting factor.
    return clamp(value_hours / 6.0)


def _find(inputs: list[MetricInput], source_code: str) -> MetricInput | None:
    return next((item for item in inputs if item.source_code == source_code), None)


def _average_available(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _source_score_open(metric: MetricInput | None) -> float | None:
    if metric is None:
        return None
    probability = (
        normalize_probability(metric.precipitation_probability_pct)
        if metric.precipitation_probability_pct is not None
        else None
    )
    amount = normalize_rain_amount(metric.rain_amount_mm) if metric.rain_amount_mm is not None else None
    if probability is not None and amount is not None:
        return 0.70 * probability + 0.30 * amount
    return probability if probability is not None else amount


def _source_score_met(metric: MetricInput | None) -> float | None:
    if metric is None:
        return None
    amount = normalize_rain_amount(metric.rain_amount_mm) if metric.rain_amount_mm is not None else None
    hours = normalize_rain_hours(metric.rain_hours) if metric.rain_hours is not None else None
    if amount is not None and hours is not None:
        return 0.70 * amount + 0.30 * hours
    return amount if amount is not None else hours


def calculate_prediction(inputs: list[MetricInput], now: datetime | None = None) -> PredictionCalculation:
    now = now or datetime.now(timezone.utc)
    open_meteo = _find(inputs, "open_meteo_gfs")
    met = _find(inputs, "met_norway")

    humidity_mean = _average_available(
        [
            open_meteo.humidity_pct if open_meteo else None,
            met.humidity_pct if met else None,
        ]
    )
    cloud_mean = _average_available(
        [
            open_meteo.cloud_cover_pct if open_meteo else None,
            met.cloud_cover_pct if met else None,
        ]
    )

    candidates: list[tuple[str, str, float | None, float, float | None, dict]] = [
        (
            "open_probability",
            "Open-Meteo precipitation probability",
            open_meteo.precipitation_probability_pct if open_meteo else None,
            0.35,
            normalize_probability(open_meteo.precipitation_probability_pct)
            if open_meteo and open_meteo.precipitation_probability_pct is not None
            else None,
            {"source_metric_id": open_meteo.metric_id if open_meteo else None, "unit": "%"},
        ),
        (
            "open_rain_amount",
            "Open-Meteo expected rain amount",
            open_meteo.rain_amount_mm if open_meteo else None,
            0.15,
            normalize_rain_amount(open_meteo.rain_amount_mm)
            if open_meteo and open_meteo.rain_amount_mm is not None
            else None,
            {"source_metric_id": open_meteo.metric_id if open_meteo else None, "unit": "mm", "cap_mm": 5.0},
        ),
        (
            "met_rain_amount",
            "MET Norway expected rain amount",
            met.rain_amount_mm if met else None,
            0.25,
            normalize_rain_amount(met.rain_amount_mm)
            if met and met.rain_amount_mm is not None
            else None,
            {"source_metric_id": met.metric_id if met else None, "unit": "mm", "cap_mm": 5.0},
        ),
        (
            "met_rain_hours",
            "MET Norway rainy hours",
            met.rain_hours if met else None,
            0.10,
            normalize_rain_hours(met.rain_hours)
            if met and met.rain_hours is not None
            else None,
            {"source_metric_id": met.metric_id if met else None, "unit": "hours", "cap_hours": 6.0},
        ),
        (
            "humidity_support",
            "Average relative humidity",
            humidity_mean,
            0.08,
            normalize_humidity(humidity_mean) if humidity_mean is not None else None,
            {
                "source_metric_ids": [item.metric_id for item in inputs if item.humidity_pct is not None],
                "unit": "%",
                "normalization": "clamp((humidity-60)/40, 0, 1)",
            },
        ),
        (
            "cloud_support",
            "Average cloud cover",
            cloud_mean,
            0.07,
            normalize_cloud_cover(cloud_mean) if cloud_mean is not None else None,
            {
                "source_metric_ids": [item.metric_id for item in inputs if item.cloud_cover_pct is not None],
                "unit": "%",
            },
        ),
    ]

    available = [item for item in candidates if item[4] is not None]
    coverage = sum(item[3] for item in available)
    if coverage < 0.35:
        raise ValueError(f"Insufficient prediction data: only {coverage:.2f} of factor weight is available")

    factors: list[FactorCalculation] = []
    score = 0.0
    for code, label, raw_value, base_weight, normalized_value, details in available:
        assert normalized_value is not None
        effective_weight = base_weight / coverage
        contribution = normalized_value * effective_weight
        score += contribution
        factors.append(
            FactorCalculation(
                code=code,
                label=label,
                raw_value=round(raw_value, 3) if raw_value is not None else None,
                normalized_value=round(normalized_value, 4),
                base_weight=base_weight,
                effective_weight=round(effective_weight, 4),
                contribution=round(contribution, 4),
                details=details,
            )
        )

    probability_pct = round(score * 100.0, 1)
    prediction_class = "rain" if probability_pct >= DECISION_THRESHOLD_PCT else "no_rain"

    open_score = _source_score_open(open_meteo)
    met_score = _source_score_met(met)
    if open_score is not None and met_score is not None:
        agreement = clamp(1.0 - abs(open_score - met_score))
    else:
        # We can still degrade gracefully with one source, but confidence must reflect it.
        agreement = 0.35

    freshness_values: list[float] = []
    for item in inputs:
        fetched = item.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now - fetched.astimezone(timezone.utc)).total_seconds() / 3600.0)
        freshness_values.append(clamp(1.0 - age_hours / 12.0))
    freshness = sum(freshness_values) / len(freshness_values) if freshness_values else 0.0

    confidence = clamp(0.45 * agreement + 0.35 * coverage + 0.20 * freshness)
    confidence_pct = round(confidence * 100.0, 1)

    borderline = 1.0 - clamp(abs(probability_pct - 50.0) / 25.0)
    risk_score = clamp(
        0.35 * (1.0 - agreement)
        + 0.25 * (1.0 - coverage)
        + 0.20 * (1.0 - freshness)
        + 0.20 * borderline
    )
    risk_score = round(risk_score, 3)
    risk_level = "low" if risk_score < 0.30 else "medium" if risk_score < 0.60 else "high"

    explanation = (
        f"Weighted factor score is {probability_pct:.1f}%. "
        f"Source agreement={agreement:.2f}, factor coverage={coverage:.2f}, freshness={freshness:.2f}. "
        f"Decision threshold is {DECISION_THRESHOLD_PCT:.0f}%."
    )

    return PredictionCalculation(
        rain_probability_pct=probability_pct,
        prediction_class=prediction_class,
        confidence_pct=confidence_pct,
        risk_score=risk_score,
        risk_level=risk_level,
        explanation=explanation,
        factors=factors,
        diagnostics={
            "agreement": round(agreement, 4),
            "coverage": round(coverage, 4),
            "freshness": round(freshness, 4),
            "borderline": round(borderline, 4),
        },
    )
