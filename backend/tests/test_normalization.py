from datetime import date

import pytest

from app.services.weather.normalize import normalize_met_norway, normalize_open_meteo


def test_open_meteo_normalization_aggregates_daily_values():
    payload = {
        "hourly": {
            "time": ["2026-08-17T00:00", "2026-08-17T01:00", "2026-08-18T00:00"],
            "precipitation_probability": [30, 70, 90],
            "rain": [0.0, 1.2, 9.0],
            "relative_humidity_2m": [70, 90, 95],
            "cloud_cover": [40, 80, 100],
            "pressure_msl": [1010, 1008, 1000],
            "temperature_2m": [18, 16, 14],
            "wind_speed_10m": [10, 14, 20],
        }
    }
    result = normalize_open_meteo(payload, date(2026, 8, 17))

    assert result.precipitation_probability_pct == 70
    assert result.rain_amount_mm == pytest.approx(1.2)
    assert result.humidity_pct == 80
    assert result.cloud_cover_pct == 60
    assert result.rain_hours == 1
    assert result.completeness == 1.0


def test_met_norway_normalization_converts_wind_and_counts_rain():
    payload = {
        "properties": {
            "timeseries": [
                {
                    "time": "2026-08-16T22:00:00Z",
                    "data": {
                        "instant": {"details": {
                            "air_temperature": 12,
                            "relative_humidity": 80,
                            "cloud_area_fraction": 70,
                            "air_pressure_at_sea_level": 1010,
                            "wind_speed": 5,
                        }},
                        "next_1_hours": {
                            "summary": {"symbol_code": "rain"},
                            "details": {"precipitation_amount": 0.7},
                        },
                    },
                },
                {
                    "time": "2026-08-16T23:00:00Z",
                    "data": {
                        "instant": {"details": {
                            "air_temperature": 11,
                            "relative_humidity": 90,
                            "cloud_area_fraction": 90,
                            "air_pressure_at_sea_level": 1008,
                            "wind_speed": 3,
                        }},
                        "next_1_hours": {
                            "summary": {"symbol_code": "cloudy"},
                            "details": {"precipitation_amount": 0.0},
                        },
                    },
                },
            ]
        }
    }
    result = normalize_met_norway(payload, date(2026, 8, 17), "Europe/Berlin")

    assert result.rain_amount_mm == pytest.approx(0.7)
    assert result.rain_hours == 1
    assert result.humidity_pct == 85
    assert result.cloud_cover_pct == 80
    assert result.wind_speed_kmh == pytest.approx(14.4)
