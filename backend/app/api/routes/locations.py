from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Location, Prediction
from app.presenters import load_prediction, prediction_query, to_prediction_read
from app.schemas import LocationCreate, LocationRead, PredictionRead, RefreshRead
from app.services.refresh import refresh_location
from app.services.weather.open_meteo import OpenMeteoClient


router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead])
def list_locations(db: Session = Depends(get_db)):
    return db.scalars(select(Location).order_by(Location.name)).all()


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    try:
        result = OpenMeteoClient().geocode(payload.query)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    latitude = float(result["latitude"])
    longitude = float(result["longitude"])
    name = str(result["name"])
    country_code = result.get("country_code")
    timezone = result.get("timezone")
    if not timezone:
        raise HTTPException(status_code=502, detail="Geocoding result has no timezone")

    existing = db.scalar(
        select(Location).where(
            Location.name == name,
            Location.country_code == country_code,
            Location.latitude == latitude,
            Location.longitude == longitude,
        )
    )
    if existing:
        return existing

    location = Location(
        name=name,
        country_code=country_code,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.post("/{location_id}/refresh", response_model=RefreshRead)
def refresh(location_id: int, db: Session = Depends(get_db)):
    try:
        prediction, source_errors = refresh_location(db, location_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if prediction is None:
        raise HTTPException(
            status_code=503,
            detail={"message": "Forecast could not be built", "source_errors": source_errors},
        )
    loaded = load_prediction(db, prediction.id)
    assert loaded is not None
    return RefreshRead(
        status="partial" if source_errors else "success",
        prediction=to_prediction_read(loaded),
        source_errors=source_errors,
    )


@router.get("/{location_id}/forecast", response_model=PredictionRead)
def latest_forecast(location_id: int, db: Session = Depends(get_db)):
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    prediction = db.scalar(
        prediction_query()
        .where(Prediction.location_id == location_id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
    )
    if prediction is None:
        raise HTTPException(status_code=404, detail="No forecast yet. Refresh the location first.")
    return to_prediction_read(prediction)
