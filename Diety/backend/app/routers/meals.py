from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Meal, User
from ..ollama_client import OllamaServiceError, analyze_food_image, estimate_manual_meal_from_items
from ..schemas import (
    ImageAnalysisResponse,
    ManualMealEstimateRequest,
    ManualMealEstimateResponse,
    MealCreate,
    MealListResponse,
    MealRead,
    MealUpdate,
)
from ..services import ai_preferences_from_user, aggregate_macros, log_ai_interaction


router = APIRouter(prefix="/api/meals", tags=["Meals"])


def _get_user_meal_or_404(db: Session, user_id: int, meal_id: int) -> Meal:
    meal = db.query(Meal).filter(Meal.id == meal_id, Meal.user_id == user_id).first()
    if not meal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasto non trovato")
    return meal


@router.post("/analyze-image", response_model=ImageAnalysisResponse)
async def analyze_image(
    image: UploadFile = File(...),
    hint: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File non supportato")

    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Immagine vuota")

    ai_preferences = ai_preferences_from_user(current_user) or {}

    try:
        result = await analyze_food_image(payload, hint, preferences=ai_preferences)
    except OllamaServiceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_ai_interaction(
        db,
        current_user.id,
        kind="image_analysis",
        model=ai_preferences.get("vision_model"),
        input_payload={
            "hint": hint,
            "file_name": image.filename,
            "content_type": image.content_type,
            "size_bytes": len(payload),
        },
        output_payload=result,
        meta={"fallback_used": result.get("fallback_used")},
    )

    return {
        "meal_type": result["meal_type"],
        "food_name": result["food_name"],
        "calories": result["calories"],
        "proteins": result["proteins"],
        "carbs": result["carbs"],
        "fats": result["fats"],
        "notes": result["notes"],
        "confidence": result["confidence"],
    }


@router.post("/estimate-manual", response_model=ManualMealEstimateResponse)
async def estimate_manual_meal(
    payload: ManualMealEstimateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ai_preferences = ai_preferences_from_user(current_user) or {}

    items = [
        {"name": item.name, "quantity": item.quantity}
        for item in payload.items
        if item.name and item.name.strip()
    ]
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inserisci almeno un ingrediente valido.")

    try:
        result = await estimate_manual_meal_from_items(
            items=items,
            hint=payload.hint or "",
            meal_type=payload.meal_type,
            preferences=ai_preferences,
        )
    except OllamaServiceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_ai_interaction(
        db,
        current_user.id,
        kind="manual_meal_estimate",
        model=ai_preferences.get("text_model"),
        input_payload={"items": items, "hint": payload.hint, "meal_type": payload.meal_type},
        output_payload=result,
    )

    return {
        "food_name": result["food_name"],
        "calories": result["calories"],
        "proteins": result["proteins"],
        "carbs": result["carbs"],
        "fats": result["fats"],
        "notes": result["notes"],
        "confidence": result["confidence"],
    }


@router.post("", response_model=MealRead, status_code=status.HTTP_201_CREATED)
def create_meal(
    payload: MealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = Meal(
        user_id=current_user.id,
        meal_type=payload.meal_type,
        food_name=payload.food_name,
        consumed_at=payload.consumed_at or datetime.now(),
        calories=payload.calories,
        proteins=payload.proteins,
        carbs=payload.carbs,
        fats=payload.fats,
        notes=payload.notes,
        source=payload.source,
        ai_payload=payload.ai_payload,
    )

    db.add(meal)
    db.commit()
    db.refresh(meal)

    return meal


@router.put("/{meal_id}", response_model=MealRead)
def update_meal(
    meal_id: int,
    payload: MealUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = _get_user_meal_or_404(db, current_user.id, meal_id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(meal, field, value)

    db.add(meal)
    db.commit()
    db.refresh(meal)

    return meal


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = _get_user_meal_or_404(db, current_user.id, meal_id)
    db.delete(meal)
    db.commit()
    return None


@router.get("", response_model=MealListResponse)
def get_meals_for_day(
    day: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    selected_day = day or date.today()
    start = datetime.combine(selected_day, time.min)
    end = datetime.combine(selected_day, time.max)

    meals = (
        db.query(Meal)
        .filter(Meal.user_id == current_user.id, Meal.consumed_at >= start, Meal.consumed_at <= end)
        .order_by(Meal.consumed_at.desc())
        .all()
    )

    totals = aggregate_macros(meals)

    return {"day": selected_day, "totals": totals, "meals": meals}
