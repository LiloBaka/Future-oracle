from datetime import date, datetime, timezone

import httpx

from app.config import get_settings
from app.services.weather.common import FetchResult, LocationSnapshot


GFS_URL = "https://api.open-meteo.com/v1/gfs"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


class OpenMeteoClient:
    source_code = "open_meteo_gfs"

    def __init__(self) -> None:
        self.timeout = get_settings().request_timeout_seconds

    def fetch_forecast(self, location: LocationSnapshot, target_date: date) -> FetchResult:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "precipitation_probability",
                    "rain",
                    "cloud_cover",
                    "pressure_msl",
                    "wind_speed_10m",
                ]
            ),
            "timezone": location.timezone,
            "start_date": target_date.isoformat(),
            "end_date": target_date.isoformat(),
        }
        return self._get(GFS_URL, params, target_date)

    def fetch_actual(self, location: LocationSnapshot, target_date: date) -> FetchResult:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "rain",
                    "cloud_cover",
                    "pressure_msl",
                    "wind_speed_10m",
                ]
            ),
            "timezone": location.timezone,
            "start_date": target_date.isoformat(),
            "end_date": target_date.isoformat(),
            "models": "ecmwf_ifs",
        }
        result = self._get(ARCHIVE_URL, params, target_date)
        return FetchResult(
            source_code="open_meteo_actual",
            target_date=result.target_date,
            fetched_at=result.fetched_at,
            http_status=result.http_status,
            payload=result.payload,
            error_message=result.error_message,
            last_modified=result.last_modified,
            expires=result.expires,
        )

    def geocode(self, query: str) -> dict:
        params = {"name": query, "count": 1, "language": "en", "format": "json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(GEOCODING_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Geocoding request failed: {exc}") from exc
        results = payload.get("results") or []
        if not results:
            raise LookupError(f"Location '{query}' was not found")
        return results[0]

    def _get(self, url: str, params: dict, target_date: date) -> FetchResult:
        fetched_at = datetime.now(timezone.utc)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params)
                status = response.status_code
                response.raise_for_status()
                payload = response.json()
            return FetchResult(
                source_code=self.source_code,
                target_date=target_date,
                fetched_at=fetched_at,
                http_status=status,
                payload=payload,
                last_modified=response.headers.get("Last-Modified"),
                expires=response.headers.get("Expires"),
            )
        except httpx.HTTPStatusError as exc:
            return FetchResult(
                source_code=self.source_code,
                target_date=target_date,
                fetched_at=fetched_at,
                http_status=exc.response.status_code,
                payload=None,
                error_message=f"HTTP {exc.response.status_code}: {exc.response.text[:300]}",
            )
        except (httpx.TimeoutException, httpx.NetworkError, ValueError) as exc:
            return FetchResult(
                source_code=self.source_code,
                target_date=target_date,
                fetched_at=fetched_at,
                http_status=None,
                payload=None,
                error_message=f"{type(exc).__name__}: {exc}",
            )
