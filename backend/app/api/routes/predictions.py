from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Prediction, PredictionFactor, UpdateHistory
from app.presenters import load_prediction, prediction_query, to_prediction_read
from app.schemas import EvaluationRead, FactorRead, PredictionRead
from app.services.evaluation import evaluate_prediction


router = APIRouter(tags=["predictions"])


@router.get("/predictions", response_model=list[PredictionRead])
def list_predictions(
    location_id: int | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = prediction_query().order_by(Prediction.created_at.desc()).limit(limit)
    if location_id is not None:
        query = query.where(Prediction.location_id == location_id)
    return [to_prediction_read(item) for item in db.scalars(query).all()]


@router.get("/predictions/{prediction_id}", response_model=PredictionRead)
def get_prediction(prediction_id: int, db: Session = Depends(get_db)):
    prediction = load_prediction(db, prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return to_prediction_read(prediction)


@router.get("/predictions/{prediction_id}/factors", response_model=list[FactorRead])
def get_factors(prediction_id: int, db: Session = Depends(get_db)):
    exists = db.get(Prediction, prediction_id)
    if exists is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return db.scalars(
        select(PredictionFactor)
        .where(PredictionFactor.prediction_id == prediction_id)
        .order_by(PredictionFactor.id)
    ).all()


@router.get("/predictions/{prediction_id}/evaluation", response_model=EvaluationRead)
def get_evaluation(prediction_id: int, db: Session = Depends(get_db)):
    prediction = load_prediction(db, prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if prediction.evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return EvaluationRead.model_validate(prediction.evaluation, from_attributes=True)


@router.post("/predictions/{prediction_id}/evaluate", response_model=EvaluationRead)
def run_evaluation(prediction_id: int, db: Session = Depends(get_db)):
    try:
        evaluation = evaluate_prediction(db, prediction_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EvaluationRead.model_validate(evaluation, from_attributes=True)


@router.get("/updates")
def list_updates(
    location_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = select(UpdateHistory).order_by(UpdateHistory.started_at.desc()).limit(limit)
    if location_id is not None:
        query = query.where(UpdateHistory.location_id == location_id)
    rows = db.scalars(query).all()
    return [
        {
            "id": item.id,
            "location_id": item.location_id,
            "prediction_id": item.prediction_id,
            "job_type": item.job_type,
            "status": item.status,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "details": item.details,
        }
        for item in rows
    ]
