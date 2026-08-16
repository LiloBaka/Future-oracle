from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Location, Prediction, PredictionEvaluation
from app.services.evaluation import evaluate_prediction
from app.services.refresh import refresh_location


scheduler = BackgroundScheduler(timezone="UTC")


def refresh_all_locations() -> None:
    with SessionLocal() as db:
        ids = db.scalars(select(Location.id).where(Location.is_active.is_(True))).all()
    for location_id in ids:
        with SessionLocal() as db:
            try:
                refresh_location(db, location_id)
            except Exception:
                db.rollback()


def evaluate_due_predictions() -> None:
    with SessionLocal() as db:
        predictions = db.scalars(
            select(Prediction)
            .join(PredictionEvaluation)
            .where(PredictionEvaluation.status == "pending")
        ).all()
        due_ids = [
            item.id
            for item in predictions
            if item.target_date < datetime.now(timezone.utc).astimezone(ZoneInfo(item.location.timezone)).date()
        ]
    for prediction_id in due_ids:
        with SessionLocal() as db:
            try:
                evaluate_prediction(db, prediction_id)
            except Exception:
                db.rollback()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        refresh_all_locations,
        "interval",
        hours=3,
        id="refresh_weather",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        evaluate_due_predictions,
        "interval",
        hours=6,
        id="evaluate_predictions",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
