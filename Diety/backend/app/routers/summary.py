from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import DailyNeedsResponse, DailySummaryResponse, TimelineResponse
from ..services import build_daily_needs, build_daily_summary, build_timeline


router = APIRouter(prefix="/api/summary", tags=["Summary"])


@router.get("/day", response_model=DailySummaryResponse)
async def get_day_summary(
    day: Optional[date] = Query(default=None),
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_day = day or date.today()
    return await build_daily_summary(db=db, user=current_user, day=target_day, refresh=refresh)


@router.get("/needs", response_model=DailyNeedsResponse)
async def get_daily_needs(
    day: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_day = day or date.today()
    return await build_daily_needs(db=db, user=current_user, day=target_day)


@router.get("/timeline", response_model=TimelineResponse)
async def get_daily_timeline(
    day: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_day = day or date.today()
    return await build_timeline(db=db, user=current_user, day=target_day)
