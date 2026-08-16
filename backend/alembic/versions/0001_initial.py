"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("country_code", sa.String(2)),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", "country_code", "latitude", "longitude", name="uq_location_identity"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_location_latitude"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_location_longitude"),
    )
    op.create_index("ix_locations_active", "locations", ["is_active"])

    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "raw_weather_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("is_success", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("response_last_modified", sa.String(128)),
        sa.Column("response_expires", sa.String(128)),
    )
    op.create_index("ix_raw_location_target", "raw_weather_records", ["location_id", "target_date"])
    op.create_index("ix_raw_source_fetched", "raw_weather_records", ["source_id", "fetched_at"])

    op.create_table(
        "normalized_weather_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_record_id", sa.Integer(), sa.ForeignKey("raw_weather_records.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("precipitation_probability_pct", sa.Float()),
        sa.Column("rain_amount_mm", sa.Float()),
        sa.Column("humidity_pct", sa.Float()),
        sa.Column("cloud_cover_pct", sa.Float()),
        sa.Column("pressure_hpa", sa.Float()),
        sa.Column("temperature_c", sa.Float()),
        sa.Column("wind_speed_kmh", sa.Float()),
        sa.Column("rain_hours", sa.Float()),
        sa.Column("completeness", sa.Float(), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("completeness BETWEEN 0 AND 1", name="ck_metric_completeness"),
    )
    op.create_index("ix_metric_target_date", "normalized_weather_metrics", ["target_date"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("rain_probability_pct", sa.Float(), nullable=False),
        sa.Column("prediction_class", sa.String(20), nullable=False),
        sa.Column("confidence_pct", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("decision_threshold_pct", sa.Float(), nullable=False, server_default="50"),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rain_probability_pct BETWEEN 0 AND 100", name="ck_prediction_probability"),
        sa.CheckConstraint("confidence_pct BETWEEN 0 AND 100", name="ck_prediction_confidence"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 1", name="ck_prediction_risk_score"),
        sa.CheckConstraint("decision_threshold_pct BETWEEN 0 AND 100", name="ck_prediction_threshold"),
        sa.CheckConstraint("prediction_class IN ('rain', 'no_rain')", name="ck_prediction_class"),
        sa.CheckConstraint("risk_level IN ('low', 'medium', 'high')", name="ck_prediction_risk_level"),
    )
    op.create_index(
        "ix_prediction_location_date_created",
        "predictions",
        ["location_id", "target_date", "created_at"],
    )

    op.create_table(
        "prediction_inputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("normalized_metric_id", sa.Integer(), sa.ForeignKey("normalized_weather_metrics.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("prediction_id", "normalized_metric_id", name="uq_prediction_input"),
    )

    op.create_table(
        "prediction_factors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("raw_value", sa.Float()),
        sa.Column("normalized_value", sa.Float(), nullable=False),
        sa.Column("base_weight", sa.Float(), nullable=False),
        sa.Column("effective_weight", sa.Float(), nullable=False),
        sa.Column("contribution", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON()),
    )
    op.create_index("ix_factor_prediction", "prediction_factors", ["prediction_id"])

    op.create_table(
        "prediction_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("actual_metric_id", sa.Integer(), sa.ForeignKey("normalized_weather_metrics.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("actual_rain", sa.Boolean()),
        sa.Column("actual_rain_mm", sa.Float()),
        sa.Column("absolute_probability_error", sa.Float()),
        sa.Column("brier_score", sa.Float()),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.CheckConstraint("status IN ('pending', 'correct', 'incorrect')", name="ck_evaluation_status"),
    )

    op.create_table(
        "update_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="SET NULL")),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id", ondelete="SET NULL")),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("details", sa.JSON()),
        sa.CheckConstraint("status IN ('success', 'partial', 'failed')", name="ck_update_status"),
    )
    op.create_index("ix_update_history_location_started", "update_history", ["location_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_update_history_location_started", table_name="update_history")
    op.drop_table("update_history")
    op.drop_table("prediction_evaluations")
    op.drop_index("ix_factor_prediction", table_name="prediction_factors")
    op.drop_table("prediction_factors")
    op.drop_table("prediction_inputs")
    op.drop_index("ix_prediction_location_date_created", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_metric_target_date", table_name="normalized_weather_metrics")
    op.drop_table("normalized_weather_metrics")
    op.drop_index("ix_raw_source_fetched", table_name="raw_weather_records")
    op.drop_index("ix_raw_location_target", table_name="raw_weather_records")
    op.drop_table("raw_weather_records")
    op.drop_table("data_sources")
    op.drop_index("ix_locations_active", table_name="locations")
    op.drop_table("locations")
