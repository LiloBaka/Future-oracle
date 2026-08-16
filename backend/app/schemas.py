from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    query: str = Field(min_length=2, max_length=120)


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country_code: str | None
    latitude: float
    longitude: float
    timezone: str
    is_active: bool


class FactorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    raw_value: float | None
    normalized_value: float
    base_weight: float
    effective_weight: float
    contribution: float
    details: dict | None


class SourceMetricRead(BaseModel):
    source_code: str
    raw_record_id: int
    normalized_metric_id: int
    fetched_at: datetime
    precipitation_probability_pct: float | None
    rain_amount_mm: float | None
    humidity_pct: float | None
    cloud_cover_pct: float | None
    pressure_hpa: float | None
    temperature_c: float | None
    wind_speed_kmh: float | None
    rain_hours: float | None
    completeness: float


class EvaluationRead(BaseModel):
    status: str
    actual_rain: bool | None
    actual_rain_mm: float | None
    absolute_probability_error: float | None
    brier_score: float | None
    evaluated_at: datetime | None
    error_message: str | None


class PredictionRead(BaseModel):
    id: int
    location: LocationRead
    target_date: date
    rain_probability_pct: float
    prediction_class: str
    confidence_pct: float
    risk_score: float
    risk_level: str
    decision_threshold_pct: float
    algorithm_version: str
    explanation: str
    created_at: datetime
    factors: list[FactorRead] = Field(default_factory=list)
    sources: list[SourceMetricRead] = Field(default_factory=list)
    evaluation: EvaluationRead | None = None


class RefreshRead(BaseModel):
    status: str
    prediction: PredictionRead | None
    source_errors: dict[str, str]
