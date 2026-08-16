from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class LocationSnapshot:
    id: int
    name: str
    latitude: float
    longitude: float
    timezone: str


@dataclass(frozen=True)
class FetchResult:
    source_code: str
    target_date: date
    fetched_at: datetime
    http_status: int | None
    payload: dict[str, Any] | None
    error_message: str | None = None
    last_modified: str | None = None
    expires: str | None = None

    @property
    def is_success(self) -> bool:
        return self.payload is not None and self.error_message is None


@dataclass(frozen=True)
class NormalizedMetrics:
    precipitation_probability_pct: float | None
    rain_amount_mm: float | None
    humidity_pct: float | None
    cloud_cover_pct: float | None
    pressure_hpa: float | None
    temperature_c: float | None
    wind_speed_kmh: float | None
    rain_hours: float | None
    completeness: float
