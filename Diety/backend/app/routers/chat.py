from datetime import date, datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import DailySummary, Meal, User
from ..ollama_client import generate_chat_response
from ..schemas import ChatRequest, ChatResponse
from ..services import (
    aggregate_macros,
    ai_preferences_from_user,
    log_ai_interaction,
    targets_from_routine,
)


router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat_with_bot(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)

    meals = (
        db.query(Meal)
        .filter(Meal.user_id == current_user.id, Meal.consumed_at >= start, Meal.consumed_at <= end)
        .order_by(Meal.consumed_at.asc())
        .all()
    )
    totals = aggregate_macros(meals)
    routine = current_user.routine
    targets = targets_from_routine(routine)

    summary = (
        db.query(DailySummary)
        .filter(DailySummary.user_id == current_user.id, DailySummary.day == today)
        .first()
    )

    preferences = ai_preferences_from_user(current_user) or {}

    context = {
        "message": payload.message,
        "history": [item.model_dump() for item in payload.history[-8:]],
        "totals": totals,
        "targets": targets,
        "daily_summary": summary.advice if summary else None,
        "user_profile": {
            "age_years": preferences.get("age_years"),
            "sex": preferences.get("sex"),
            "height_cm": preferences.get("height_cm"),
            "weight_kg": preferences.get("weight_kg"),
            "target_weight_kg": preferences.get("target_weight_kg"),
            "activity_level": preferences.get("activity_level"),
            "goals": preferences.get("goals"),
            "dietary_preferences": preferences.get("dietary_preferences"),
            "allergies": preferences.get("allergies"),
        },
    }

    reply = await generate_chat_response(context, preferences=preferences)

    log_ai_interaction(
        db,
        current_user.id,
        kind="dietly_chat",
        model=preferences.get("text_model"),
        input_payload=context,
        output_payload={"reply": reply},
    )

    return {"reply": reply}
