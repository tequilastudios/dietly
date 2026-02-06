from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User, WaterIntake
from ..schemas import WaterCreate, WaterIntakeRead, WaterSummaryResponse
from ..services import estimate_water_target_ml, ai_preferences_from_user


router = APIRouter(prefix="/api/water", tags=["Water"])


@router.post("", response_model=WaterIntakeRead)
def add_water(
    payload: WaterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consumed_at = payload.consumed_at or datetime.utcnow()
    entry = WaterIntake(user_id=current_user.id, amount_ml=payload.amount_ml, consumed_at=consumed_at)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=WaterSummaryResponse)
def get_water_summary(
    day: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_day = day or date.today()
    start = datetime.combine(target_day, time.min)
    end = datetime.combine(target_day, time.max)

    entries = (
        db.query(WaterIntake)
        .filter(WaterIntake.user_id == current_user.id, WaterIntake.consumed_at >= start, WaterIntake.consumed_at <= end)
        .order_by(WaterIntake.consumed_at.asc())
        .all()
    )

    total_ml = sum(entry.amount_ml for entry in entries)
    preferences = ai_preferences_from_user(current_user) or {}
    target_ml = estimate_water_target_ml(preferences)

    return {
        "day": target_day,
        "total_ml": total_ml,
        "target_ml": target_ml,
        "entries": entries,
    }
