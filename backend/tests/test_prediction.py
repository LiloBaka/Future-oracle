from datetime import datetime, timezone

import pytest

from app.services.prediction import MetricInput, calculate_prediction


def make_inputs(now: datetime):
    return [
        MetricInput(
            source_code="open_meteo_gfs",
            metric_id=1,
            fetched_at=now,
            precipitation_probability_pct=70.0,
            rain_amount_mm=3.0,
            humidity_pct=80.0,
            cloud_cover_pct=70.0,
            rain_hours=4.0,
        ),
        MetricInput(
            source_code="met_norway",
            metric_id=2,
            fetched_at=now,
            precipitation_probability_pct=None,
            rain_amount_mm=2.0,
            humidity_pct=80.0,
            cloud_cover_pct=70.0,
            rain_hours=3.0,
        ),
    ]


def test_prediction_math_is_deterministic():
    now = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    result = calculate_prediction(make_inputs(now), now=now)

    assert result.rain_probability_pct == pytest.approx(57.4)
    assert result.prediction_class == "rain"
    assert result.confidence_pct == pytest.approx(89.2)
    assert result.risk_score == pytest.approx(0.225)
    assert result.risk_level == "low"
    assert sum(item.contribution for item in result.factors) == pytest.approx(0.574, abs=0.001)
    assert result.diagnostics["agreement"] == pytest.approx(0.76)
    assert result.diagnostics["coverage"] == 1.0


def test_one_source_degrades_confidence_and_increases_missing_data_risk():
    now = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    result = calculate_prediction([make_inputs(now)[0]], now=now)

    assert result.diagnostics["coverage"] == pytest.approx(0.65)
    assert result.diagnostics["agreement"] == pytest.approx(0.35)
    assert result.confidence_pct < 60.0
    assert result.risk_score > 0.30


def test_stale_data_reduces_confidence():
    now = datetime(2026, 8, 16, 18, tzinfo=timezone.utc)
    fresh_inputs = make_inputs(now)
    stale_at = datetime(2026, 8, 16, 8, tzinfo=timezone.utc)
    stale_inputs = [
        MetricInput(**{**item.__dict__, "fetched_at": stale_at})
        for item in fresh_inputs
    ]

    fresh = calculate_prediction(fresh_inputs, now=now)
    stale = calculate_prediction(stale_inputs, now=now)

    assert stale.confidence_pct < fresh.confidence_pct
    assert stale.risk_score > fresh.risk_score
