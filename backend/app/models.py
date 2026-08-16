from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SourceKind(StrEnum):
    FORECAST = "forecast"
    ACTUAL = "actual"


class RefreshStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class PredictionClass(StrEnum):
    RAIN = "rain"
    NO_RAIN = "no_rain"


class EvaluationStatus(StrEnum):
    PENDING = "pending"
    CORRECT = "correct"
    INCORRECT = "incorrect"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    raw_records: Mapped[list[RawWeatherRecord]] = relationship(back_populates="location")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="location")

    __table_args__ = (
        UniqueConstraint("name", "country_code", "latitude", "longitude", name="uq_location_identity"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_location_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_location_longitude"),
        Index("ix_locations_active", "is_active"),
    )


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    raw_records: Mapped[list[RawWeatherRecord]] = relationship(back_populates="source")


class RawWeatherRecord(Base):
    __tablename__ = "raw_weather_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    response_last_modified: Mapped[str | None] = mapped_column(String(128))
    response_expires: Mapped[str | None] = mapped_column(String(128))

    location: Mapped[Location] = relationship(back_populates="raw_records")
    source: Mapped[DataSource] = relationship(back_populates="raw_records")
    normalized_metric: Mapped[NormalizedWeatherMetric | None] = relationship(
        back_populates="raw_record", uselist=False
    )

    __table_args__ = (
        Index("ix_raw_location_target", "location_id", "target_date"),
        Index("ix_raw_source_fetched", "source_id", "fetched_at"),
    )


class NormalizedWeatherMetric(Base):
    __tablename__ = "normalized_weather_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_record_id: Mapped[int] = mapped_column(
        ForeignKey("raw_weather_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    precipitation_probability_pct: Mapped[float | None] = mapped_column(Float)
    rain_amount_mm: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float)
    pressure_hpa: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float)
    rain_hours: Mapped[float | None] = mapped_column(Float)
    completeness: Mapped[float] = mapped_column(Float, nullable=False)
    normalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    raw_record: Mapped[RawWeatherRecord] = relationship(back_populates="normalized_metric")
    prediction_inputs: Mapped[list[PredictionInput]] = relationship(back_populates="metric")

    __table_args__ = (
        CheckConstraint("completeness BETWEEN 0 AND 1", name="ck_metric_completeness"),
        Index("ix_metric_target_date", "target_date"),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    rain_probability_pct: Mapped[float] = mapped_column(Float, nullable=False)
    prediction_class: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_pct: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_threshold_pct: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    location: Mapped[Location] = relationship(back_populates="predictions")
    inputs: Mapped[list[PredictionInput]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )
    factors: Mapped[list[PredictionFactor]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )
    evaluation: Mapped[PredictionEvaluation | None] = relationship(
        back_populates="prediction", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("rain_probability_pct BETWEEN 0 AND 100", name="ck_prediction_probability"),
        CheckConstraint("confidence_pct BETWEEN 0 AND 100", name="ck_prediction_confidence"),
        CheckConstraint("risk_score BETWEEN 0 AND 1", name="ck_prediction_risk_score"),
        CheckConstraint("decision_threshold_pct BETWEEN 0 AND 100", name="ck_prediction_threshold"),
        CheckConstraint("prediction_class IN ('rain', 'no_rain')", name="ck_prediction_class"),
        CheckConstraint("risk_level IN ('low', 'medium', 'high')", name="ck_prediction_risk_level"),
        Index("ix_prediction_location_date_created", "location_id", "target_date", "created_at"),
    )


class PredictionInput(Base):
    __tablename__ = "prediction_inputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False)
    normalized_metric_id: Mapped[int] = mapped_column(
        ForeignKey("normalized_weather_metrics.id", ondelete="RESTRICT"), nullable=False
    )

    prediction: Mapped[Prediction] = relationship(back_populates="inputs")
    metric: Mapped[NormalizedWeatherMetric] = relationship(back_populates="prediction_inputs")

    __table_args__ = (
        UniqueConstraint("prediction_id", "normalized_metric_id", name="uq_prediction_input"),
    )


class PredictionFactor(Base):
    __tablename__ = "prediction_factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    raw_value: Mapped[float | None] = mapped_column(Float)
    normalized_value: Mapped[float] = mapped_column(Float, nullable=False)
    base_weight: Mapped[float] = mapped_column(Float, nullable=False)
    effective_weight: Mapped[float] = mapped_column(Float, nullable=False)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)

    prediction: Mapped[Prediction] = relationship(back_populates="factors")

    __table_args__ = (Index("ix_factor_prediction", "prediction_id"),)


class PredictionEvaluation(Base):
    __tablename__ = "prediction_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    actual_metric_id: Mapped[int | None] = mapped_column(
        ForeignKey("normalized_weather_metrics.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=EvaluationStatus.PENDING)
    actual_rain: Mapped[bool | None] = mapped_column(Boolean)
    actual_rain_mm: Mapped[float | None] = mapped_column(Float)
    absolute_probability_error: Mapped[float | None] = mapped_column(Float)
    brier_score: Mapped[float | None] = mapped_column(Float)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    prediction: Mapped[Prediction] = relationship(back_populates="evaluation")
    actual_metric: Mapped[NormalizedWeatherMetric | None] = relationship()

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'correct', 'incorrect')", name="ck_evaluation_status"),
    )


class UpdateHistory(Base):
    __tablename__ = "update_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id", ondelete="SET NULL"))
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        CheckConstraint("status IN ('success', 'partial', 'failed')", name="ck_update_status"),
        Index("ix_update_history_location_started", "location_id", "started_at"),
    )
