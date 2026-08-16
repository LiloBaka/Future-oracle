from datetime import date, datetime, timezone

import httpx

from app.config import get_settings
from app.services.weather.common import FetchResult, LocationSnapshot


MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"


class MetNorwayClient:
    source_code = "met_norway"

    def __init__(self) -> None:
        settings = get_settings()
        self.timeout = settings.request_timeout_seconds
        self.headers = {"User-Agent": settings.met_user_agent, "Accept": "application/json"}

    def fetch_forecast(self, location: LocationSnapshot, target_date: date) -> FetchResult:
        fetched_at = datetime.now(timezone.utc)
        params = {
            "lat": round(location.latitude, 4),
            "lon": round(location.longitude, 4),
        }
        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                response = client.get(MET_URL, params=params)
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
