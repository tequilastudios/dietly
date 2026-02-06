from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

import json

from .models import AIInteraction, DailySummary, Meal, Routine, User
from .ollama_client import (
    generate_daily_advice,
    generate_daily_needs,
    generate_timeline_guidance,
)


def _round(value: float) -> float:
    return round(float(value), 2)


def log_ai_interaction(
    db: Session,
    user_id: int,
    kind: str,
    model: str | None,
    input_payload: dict | None,
    output_payload: dict | str | None,
    meta: dict | None = None,
) -> None:
    try:
        entry = AIInteraction(
            user_id=user_id,
            kind=kind,
            model=model,
            input_payload=json.dumps(input_payload, ensure_ascii=False) if input_payload is not None else None,
            output_payload=json.dumps(output_payload, ensure_ascii=False) if isinstance(output_payload, (dict, list)) else output_payload,
            meta=json.dumps(meta, ensure_ascii=False) if meta is not None else None,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


def aggregate_macros(meals: list[Meal]) -> dict:
    totals = {
        "calories": 0.0,
        "proteins": 0.0,
        "carbs": 0.0,
        "fats": 0.0,
    }

    for meal in meals:
        totals["calories"] += meal.calories or 0
        totals["proteins"] += meal.proteins or 0
        totals["carbs"] += meal.carbs or 0
        totals["fats"] += meal.fats or 0

    return {key: _round(value) for key, value in totals.items()}


def targets_from_routine(routine: Routine | None) -> dict:
    if not routine:
        return {"calories": None, "proteins": None, "carbs": None, "fats": None}

    return {
        "calories": _round(routine.calorie_target) if routine.calorie_target is not None else None,
        "proteins": _round(routine.protein_target) if routine.protein_target is not None else None,
        "carbs": _round(routine.carbs_target) if routine.carbs_target is not None else None,
        "fats": _round(routine.fats_target) if routine.fats_target is not None else None,
    }


def compute_day_end_time(routine: Routine | None) -> time:
    if routine and routine.day_end_time:
        return routine.day_end_time

    dinner_time = routine.dinner_time if routine else time(20, 0)
    today = date.today()
    day_end_dt = datetime.combine(today, dinner_time) + timedelta(hours=3)
    return day_end_dt.time().replace(second=0, microsecond=0)


def is_day_closed(day: date, routine: Routine | None, now: datetime | None = None) -> bool:
    now = now or datetime.now()

    if day < now.date():
        return True
    if day > now.date():
        return False

    return now.time() >= compute_day_end_time(routine)


def ai_preferences_from_user(user: User) -> dict | None:
    ai_settings = user.ai_settings
    if not ai_settings:
        return None

    return {
        "ollama_base_url": ai_settings.ollama_base_url,
        "vision_model": ai_settings.vision_model,
        "text_model": ai_settings.text_model,
        "timeout_seconds": ai_settings.timeout_seconds,
        "temperature": ai_settings.temperature,
        "macro_fallback_enabled": ai_settings.macro_fallback_enabled,
        "meal_type_autodetect_enabled": ai_settings.meal_type_autodetect_enabled,
        "smart_routine_enabled": ai_settings.smart_routine_enabled,
        "response_language": ai_settings.response_language,
        "system_prompt": ai_settings.system_prompt,
        "reasoning_cycles": ai_settings.reasoning_cycles,
        "age_years": ai_settings.age_years,
        "sex": ai_settings.sex,
        "height_cm": ai_settings.height_cm,
        "weight_kg": ai_settings.weight_kg,
        "target_weight_kg": ai_settings.target_weight_kg,
        "activity_level": ai_settings.activity_level,
        "goals": ai_settings.goals,
        "dietary_preferences": ai_settings.dietary_preferences,
        "allergies": ai_settings.allergies,
    }


async def build_daily_summary(
    db: Session,
    user: User,
    day: date,
    refresh: bool = False,
) -> dict:
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)

    meals = (
        db.query(Meal)
        .filter(Meal.user_id == user.id, Meal.consumed_at >= start, Meal.consumed_at <= end)
        .order_by(Meal.consumed_at.asc())
        .all()
    )

    totals = aggregate_macros(meals)
    routine = user.routine
    targets = targets_from_routine(routine)
    day_end_time = compute_day_end_time(routine)
    closed = is_day_closed(day, routine)

    stored_summary = db.query(DailySummary).filter(DailySummary.user_id == user.id, DailySummary.day == day).first()
    advice = stored_summary.advice if stored_summary else None
    ai_preferences = ai_preferences_from_user(user)

    ai_used = False
    if closed:
        if refresh or not advice:
            prompt_payload = {
                "day": str(day),
                "totals": totals,
                "targets": targets,
                "meal_count": len(meals),
                "user_profile": {
                    "age_years": ai_preferences.get("age_years") if ai_preferences else None,
                    "sex": ai_preferences.get("sex") if ai_preferences else None,
                    "height_cm": ai_preferences.get("height_cm") if ai_preferences else None,
                    "weight_kg": ai_preferences.get("weight_kg") if ai_preferences else None,
                    "target_weight_kg": ai_preferences.get("target_weight_kg") if ai_preferences else None,
                    "activity_level": ai_preferences.get("activity_level") if ai_preferences else None,
                    "goals": ai_preferences.get("goals") if ai_preferences else None,
                    "dietary_preferences": ai_preferences.get("dietary_preferences") if ai_preferences else None,
                    "allergies": ai_preferences.get("allergies") if ai_preferences else None,
                },
            }
            try:
                advice = await generate_daily_advice(
                    prompt_payload,
                    preferences=ai_preferences,
                )
                ai_used = True
            except Exception:
                advice = (
                    "Giornata chiusa: prova a distribuire meglio i macro nei pasti principali "
                    "e aumenta leggermente verdura/fibra nei prossimi giorni."
                )

        if stored_summary:
            stored_summary.calories = totals["calories"]
            stored_summary.proteins = totals["proteins"]
            stored_summary.carbs = totals["carbs"]
            stored_summary.fats = totals["fats"]
            stored_summary.status = "closed"
            stored_summary.advice = advice
            stored_summary.generated_at = datetime.utcnow()
        else:
            db.add(
                DailySummary(
                    user_id=user.id,
                    day=day,
                    calories=totals["calories"],
                    proteins=totals["proteins"],
                    carbs=totals["carbs"],
                    fats=totals["fats"],
                    status="closed",
                    advice=advice,
                    generated_at=datetime.utcnow(),
                )
            )

        db.commit()

        if ai_used and ai_preferences:
            log_ai_interaction(
                db,
                user.id,
                kind="daily_advice",
                model=ai_preferences.get("text_model"),
                input_payload=prompt_payload,
                output_payload={"advice": advice},
                meta={"day": str(day)},
            )

    return {
        "day": day,
        "is_closed": closed,
        "status": "closed" if closed else "open",
        "day_end_time": day_end_time,
        "meals_count": len(meals),
        "totals": totals,
        "targets": targets,
        "advice": advice if closed else None,
    }


def _activity_multiplier(level: str | None) -> float:
    mapping = {
        "sedentario": 1.2,
        "leggero": 1.375,
        "moderato": 1.55,
        "alto": 1.725,
        "molto_alto": 1.9,
    }
    if not level:
        return 1.35
    return mapping.get(level.lower(), 1.35)


def _goal_adjustment(goals: str | None) -> int:
    if not goals:
        return 0
    normalized = goals.lower()
    if any(keyword in normalized for keyword in ("dimagr", "perdere", "deficit", "snell")):
        return -300
    if any(keyword in normalized for keyword in ("massa", "muscolo", "aumentare", "bulk")):
        return 250
    return 0


def estimate_daily_needs_from_profile(profile: dict) -> dict:
    weight = profile.get("weight_kg")
    height = profile.get("height_cm")
    age = profile.get("age_years")
    sex = (profile.get("sex") or "").lower()
    goals = profile.get("goals")

    if weight and height and age:
        base = 10 * weight + 6.25 * height - 5 * age
        if "donn" in sex or "fem" in sex:
            base -= 161
        elif "uomo" in sex or "mas" in sex:
            base += 5
    else:
        base = 1500

    calories = base * _activity_multiplier(profile.get("activity_level")) + _goal_adjustment(goals)
    calories = max(calories, 1200)

    if weight:
        proteins = weight * 1.6
        fats = weight * 0.8
    else:
        proteins = calories * 0.22 / 4
        fats = calories * 0.25 / 9

    carbs = max((calories - proteins * 4 - fats * 9) / 4, 0)

    return {
        "calories": _round(calories),
        "proteins": _round(proteins),
        "carbs": _round(carbs),
        "fats": _round(fats),
    }


def estimate_water_target_ml(profile: dict) -> int | None:
    weight = profile.get("weight_kg")
    if weight:
        return int(weight * 35)
    return 2000


def _macro_focus(remaining: dict) -> str:
    ordered = sorted(
        (
            ("proteine", remaining.get("proteins", 0)),
            ("carboidrati", remaining.get("carbs", 0)),
            ("grassi", remaining.get("fats", 0)),
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    for label, value in ordered:
        if value and value > 0:
            return label
    return "macro"


async def build_daily_needs(db: Session, user: User, day: date) -> dict:
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    meals = (
        db.query(Meal)
        .filter(Meal.user_id == user.id, Meal.consumed_at >= start, Meal.consumed_at <= end)
        .order_by(Meal.consumed_at.asc())
        .all()
    )
    totals = aggregate_macros(meals)
    ai_preferences = ai_preferences_from_user(user) or {}
    needs = estimate_daily_needs_from_profile(ai_preferences)
    source = "stimato"
    note = "Stima basata su dati inseriti e livello di attivita."

    ai_payload = {"profile": ai_preferences, "totals": totals}
    try:
        ai_result = await generate_daily_needs(
            ai_payload,
            preferences=ai_preferences,
        )
        if ai_result:
            candidate = ai_result.get("needs", {})
            used = False
            if sum(candidate.values()) > 0:
                needs = candidate
                note = ai_result.get("note") or note
                source = "ai"
                used = True
            log_ai_interaction(
                db,
                user.id,
                kind="daily_needs",
                model=ai_preferences.get("text_model"),
                input_payload=ai_payload,
                output_payload=ai_result,
                meta={"day": str(day), "used": used},
            )
    except Exception:
        pass

    return {
        "day": day,
        "needs": needs,
        "totals": totals,
        "water_ml": estimate_water_target_ml(ai_preferences),
        "source": source,
        "note": note,
    }


async def build_timeline(db: Session, user: User, day: date) -> dict:
    routine = user.routine
    if not routine:
        return {"day": day, "phases": [], "guidance": None}

    phases = [
        ("Colazione", routine.breakfast_time),
        ("Pranzo", routine.lunch_time),
        ("Cena", routine.dinner_time),
        ("Fine giornata", compute_day_end_time(routine)),
    ]

    today = date.today()
    now = datetime.now()
    phase_status = []

    if day < today:
        phase_status = ["past"] * len(phases)
    elif day > today:
        phase_status = ["future"] * len(phases)
    else:
        current_index = 0
        for idx, (_, phase_time) in enumerate(phases):
            if now.time() >= phase_time:
                current_index = idx
        for idx in range(len(phases)):
            if idx < current_index:
                phase_status.append("past")
            elif idx == current_index:
                phase_status.append("current")
            else:
                phase_status.append("future")

    totals = aggregate_macros(
        db.query(Meal)
        .filter(
            Meal.user_id == user.id,
            Meal.consumed_at >= datetime.combine(day, time.min),
            Meal.consumed_at <= datetime.combine(day, time.max),
        )
        .all()
    )

    ai_preferences = ai_preferences_from_user(user) or {}
    targets = targets_from_routine(routine)
    if not targets.get("calories"):
        targets = estimate_daily_needs_from_profile(ai_preferences)

    remaining = {
        "calories": max((targets.get("calories") or 0) - totals.get("calories", 0), 0),
        "proteins": max((targets.get("proteins") or 0) - totals.get("proteins", 0), 0),
        "carbs": max((targets.get("carbs") or 0) - totals.get("carbs", 0), 0),
        "fats": max((targets.get("fats") or 0) - totals.get("fats", 0), 0),
    }

    guidance = None
    try:
        timeline_payload = {
            "day": str(day),
            "totals": totals,
            "targets": targets,
            "remaining": remaining,
        }
        guidance = await generate_timeline_guidance(
            timeline_payload,
            preferences=ai_preferences,
        )
        log_ai_interaction(
            db,
            user.id,
            kind="timeline_guidance",
            model=ai_preferences.get("text_model"),
            input_payload=timeline_payload,
            output_payload={"guidance": guidance},
            meta={"day": str(day)},
        )
    except Exception:
        guidance = f"Restano circa {round(remaining['calories'])} kcal: privilegia {_macro_focus(remaining)} nei prossimi pasti."

    output_phases = []
    focus = _macro_focus(remaining)
    for (label, phase_time), status in zip(phases, phase_status):
        if status == "current":
            suggestion = f"Focalizzati su {focus}."
        elif status == "future":
            suggestion = "Mantieni equilibrio nei macro."
        else:
            suggestion = "Completato."
        output_phases.append(
            {
                "label": label,
                "time": phase_time.strftime("%H:%M"),
                "status": status,
                "suggestion": suggestion,
            }
        )

    return {"day": day, "phases": output_phases, "guidance": guidance}
