from datetime import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Routine, User
from ..ollama_client import generate_smart_routine
from ..schemas import RoutineRead, RoutineUpdate
from ..services import ai_preferences_from_user, log_ai_interaction


router = APIRouter(prefix="/api/routine", tags=["Routine"])


def _get_or_create_routine(db: Session, user: User) -> Routine:
    routine = db.query(Routine).filter(Routine.user_id == user.id).first()
    if routine:
        return routine

    routine = Routine(user_id=user.id)
    db.add(routine)
    db.commit()
    db.refresh(routine)
    return routine


def _parse_time(value: str) -> time | None:
    if not value:
        return None
    value = value.strip()
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return time(hours, minutes)


@router.get("", response_model=RoutineRead)
def get_routine(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    routine = _get_or_create_routine(db, current_user)
    return routine


@router.put("", response_model=RoutineRead)
async def upsert_routine(
    payload: RoutineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    routine = _get_or_create_routine(db, current_user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(routine, field, value)

    ai_note = None
    ai_applied = False
    ai_preferences = ai_preferences_from_user(current_user) or {}
    smart_enabled = ai_preferences.get("smart_routine_enabled")
    has_targets = any(
        value is not None
        for value in (
            routine.calorie_target,
            routine.protein_target,
            routine.carbs_target,
            routine.fats_target,
        )
    )

    if smart_enabled and (has_targets or ai_preferences.get("goals")):
        try:
            ai_payload = {
                "routine": {
                    "breakfast_time": routine.breakfast_time.strftime("%H:%M") if routine.breakfast_time else None,
                    "lunch_time": routine.lunch_time.strftime("%H:%M") if routine.lunch_time else None,
                    "dinner_time": routine.dinner_time.strftime("%H:%M") if routine.dinner_time else None,
                    "day_end_time": routine.day_end_time.strftime("%H:%M") if routine.day_end_time else None,
                },
                "targets": {
                    "calorie_target": routine.calorie_target,
                    "protein_target": routine.protein_target,
                    "carbs_target": routine.carbs_target,
                    "fats_target": routine.fats_target,
                },
                "profile": ai_preferences,
            }
            ai_result = await generate_smart_routine(ai_payload, preferences=ai_preferences)
            if ai_result:
                updated = False
                for field in ("breakfast_time", "lunch_time", "dinner_time", "day_end_time"):
                    parsed = _parse_time(ai_result.get(field) or "")
                    if parsed:
                        setattr(routine, field, parsed)
                        updated = True
                for field, key in (
                    ("calorie_target", "calorie_target"),
                    ("protein_target", "protein_target"),
                    ("carbs_target", "carbs_target"),
                    ("fats_target", "fats_target"),
                ):
                    value = ai_result.get(key)
                    if value and value > 0:
                        setattr(routine, field, value)
                        updated = True
                ai_note = ai_result.get("note") or "Routine ottimizzata da AI."
                ai_applied = updated
                log_ai_interaction(
                    db,
                    current_user.id,
                    kind="smart_routine",
                    model=ai_preferences.get("text_model"),
                    input_payload=ai_payload,
                    output_payload=ai_result,
                    meta={"note": ai_note, "applied": ai_applied},
                )
        except Exception:
            ai_note = None

    db.add(routine)
    db.commit()
    db.refresh(routine)

    response = RoutineRead.model_validate(routine).model_dump()
    response["ai_applied"] = ai_applied
    response["ai_note"] = ai_note
    return response
