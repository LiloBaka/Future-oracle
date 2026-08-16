from __future__ import annotations

from datetime import date, datetime
from statistics import fmean
from zoneinfo import ZoneInfo

from app.services.weather.common import NormalizedMetrics


def _mean(values: list[float]) -> float | None:
    return round(fmean(values), 3) if values else None


def _max(values: list[float]) -> float | None:
    return round(max(values), 3) if values else None


def _sum(values: list[float]) -> float | None:
    return round(sum(values), 3) if values else None


def _completeness(values: list[object | None]) -> float:
    return round(sum(value is not None for value in values) / len(values), 3)


def normalize_open_meteo(payload: dict, target_date: date) -> NormalizedMetrics:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("Open-Meteo response does not contain 'hourly'")

    times = hourly.get("time") or []
    if not times:
        raise ValueError("Open-Meteo response has no hourly timestamps")

    indexes = [idx for idx, value in enumerate(times) if str(value).startswith(target_date.isoformat())]
    if not indexes:
        raise ValueError(f"Open-Meteo response has no data for {target_date}")

    def values(key: str) -> list[float]:
        raw = hourly.get(key) or []
        result: list[float] = []
        for idx in indexes:
            if idx < len(raw) and raw[idx] is not None:
                result.append(float(raw[idx]))
        return result

    probability = _max(values("precipitation_probability"))
    rain = _sum(values("rain"))
    humidity = _mean(values("relative_humidity_2m"))
    cloud = _mean(values("cloud_cover"))
    pressure = _mean(values("pressure_msl"))
    temperature = _mean(values("temperature_2m"))
    wind = _mean(values("wind_speed_10m"))
    rain_values = values("rain")
    rain_hours = float(sum(value >= 0.1 for value in rain_values)) if rain_values else None

    required = [probability, rain, humidity, cloud, pressure, temperature, wind, rain_hours]
    return NormalizedMetrics(
        precipitation_probability_pct=probability,
        rain_amount_mm=rain,
        humidity_pct=humidity,
        cloud_cover_pct=cloud,
        pressure_hpa=pressure,
        temperature_c=temperature,
        wind_speed_kmh=wind,
        rain_hours=rain_hours,
        completeness=_completeness(required),
    )


def normalize_met_norway(payload: dict, target_date: date, timezone_name: str) -> NormalizedMetrics:
    timeseries = payload.get("properties", {}).get("timeseries")
    if not isinstance(timeseries, list):
        raise ValueError("MET Norway response does not contain properties.timeseries")

    tz = ZoneInfo(timezone_name)
    instant_rows: list[dict] = []
    precipitation_values: list[float] = []
    probability_values: list[float] = []
    rain_hours = 0.0

    for item in timeseries:
        raw_time = item.get("time")
        if not raw_time:
            continue
        timestamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).astimezone(tz)
        if timestamp.date() != target_date:
            continue

        data = item.get("data", {})
        details = data.get("instant", {}).get("details", {})
        instant_rows.append(details)

        next_hour = data.get("next_1_hours", {})
        next_details = next_hour.get("details", {})
        amount = next_details.get("precipitation_amount")
        probability = next_details.get("probability_of_precipitation")
        symbol = str(next_hour.get("summary", {}).get("symbol_code", "")).lower()
        temperature = details.get("air_temperature")

        if probability is not None:
            probability_values.append(float(probability))

        if amount is not None:
            amount = float(amount)
            rain_like = "rain" in symbol or (temperature is not None and float(temperature) > 1.0)
            if rain_like:
                precipitation_values.append(amount)
                if amount >= 0.1:
                    rain_hours += 1.0

    if not instant_rows:
        raise ValueError(f"MET Norway response has no data for {target_date} in {timezone_name}")

    def instant_values(key: str) -> list[float]:
        return [float(row[key]) for row in instant_rows if row.get(key) is not None]

    probability = _max(probability_values)
    rain = _sum(precipitation_values)
    humidity = _mean(instant_values("relative_humidity"))
    cloud = _mean(instant_values("cloud_area_fraction"))
    pressure = _mean(instant_values("air_pressure_at_sea_level"))
    temperature = _mean(instant_values("air_temperature"))
    wind_ms = _mean(instant_values("wind_speed"))
    wind_kmh = round(wind_ms * 3.6, 3) if wind_ms is not None else None

    required = [rain, humidity, cloud, pressure, temperature, wind_kmh, rain_hours]
    return NormalizedMetrics(
        precipitation_probability_pct=probability,
        rain_amount_mm=rain,
        humidity_pct=humidity,
        cloud_cover_pct=cloud,
        pressure_hpa=pressure,
        temperature_c=temperature,
        wind_speed_kmh=wind_kmh,
        rain_hours=rain_hours,
        completeness=_completeness(required),
    )
