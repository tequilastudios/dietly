from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=72)


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class RoutineUpdate(BaseModel):
    breakfast_time: Optional[time] = None
    lunch_time: Optional[time] = None
    dinner_time: Optional[time] = None
    day_end_time: Optional[time] = None

    calorie_target: Optional[float] = Field(default=None, ge=0)
    protein_target: Optional[float] = Field(default=None, ge=0)
    carbs_target: Optional[float] = Field(default=None, ge=0)
    fats_target: Optional[float] = Field(default=None, ge=0)


class RoutineRead(BaseModel):
    breakfast_time: time
    lunch_time: time
    dinner_time: time
    day_end_time: Optional[time]

    calorie_target: Optional[float]
    protein_target: Optional[float]
    carbs_target: Optional[float]
    fats_target: Optional[float]
    ai_applied: Optional[bool] = None
    ai_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AISettingsRead(BaseModel):
    ollama_base_url: Optional[str]
    vision_model: str
    text_model: str
    timeout_seconds: int
    temperature: float
    macro_fallback_enabled: bool
    meal_type_autodetect_enabled: bool
    smart_routine_enabled: bool
    age_years: Optional[int]
    sex: Optional[str]
    height_cm: Optional[float]
    weight_kg: Optional[float]
    target_weight_kg: Optional[float]
    activity_level: Optional[str]
    goals: Optional[str]
    dietary_preferences: Optional[str]
    allergies: Optional[str]
    response_language: str
    system_prompt: Optional[str]
    reasoning_cycles: int

    model_config = ConfigDict(from_attributes=True)


class AISettingsUpdate(BaseModel):
    ollama_base_url: Optional[str] = Field(default=None, max_length=255)
    vision_model: Optional[str] = Field(default=None, min_length=2, max_length=120)
    text_model: Optional[str] = Field(default=None, min_length=2, max_length=120)
    timeout_seconds: Optional[int] = Field(default=None, ge=30, le=600)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.5)
    macro_fallback_enabled: Optional[bool] = None
    meal_type_autodetect_enabled: Optional[bool] = None
    smart_routine_enabled: Optional[bool] = None
    age_years: Optional[int] = Field(default=None, ge=10, le=120)
    sex: Optional[str] = Field(default=None, max_length=32)
    height_cm: Optional[float] = Field(default=None, ge=80, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=25, le=350)
    target_weight_kg: Optional[float] = Field(default=None, ge=25, le=350)
    activity_level: Optional[str] = Field(default=None, max_length=32)
    goals: Optional[str] = Field(default=None, max_length=2000)
    dietary_preferences: Optional[str] = Field(default=None, max_length=2000)
    allergies: Optional[str] = Field(default=None, max_length=2000)
    response_language: Optional[str] = Field(default=None, max_length=16)
    system_prompt: Optional[str] = Field(default=None, max_length=4000)
    reasoning_cycles: Optional[int] = Field(default=None, ge=1, le=4)


class OllamaModelsResponse(BaseModel):
    base_url: str
    models: list[str]
    vision_candidates: list[str]
    text_candidates: list[str]
    default_vision_model: str
    default_text_model: str
    default_vision_installed: bool
    default_text_installed: bool


class MealCreate(BaseModel):
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack|other)$")
    food_name: str = Field(min_length=1, max_length=255)

    consumed_at: Optional[datetime] = None
    calories: float = Field(default=0, ge=0)
    proteins: float = Field(default=0, ge=0)
    carbs: float = Field(default=0, ge=0)
    fats: float = Field(default=0, ge=0)

    notes: Optional[str] = Field(default=None, max_length=1000)
    source: str = Field(default="manual", pattern="^(manual|ai)$")
    ai_payload: Optional[str] = None


class MealUpdate(BaseModel):
    meal_type: Optional[str] = Field(default=None, pattern="^(breakfast|lunch|dinner|snack|other)$")
    food_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    consumed_at: Optional[datetime] = None

    calories: Optional[float] = Field(default=None, ge=0)
    proteins: Optional[float] = Field(default=None, ge=0)
    carbs: Optional[float] = Field(default=None, ge=0)
    fats: Optional[float] = Field(default=None, ge=0)

    notes: Optional[str] = Field(default=None, max_length=1000)
    source: Optional[str] = Field(default=None, pattern="^(manual|ai)$")
    ai_payload: Optional[str] = None


class MealRead(BaseModel):
    id: int
    meal_type: str
    food_name: str
    consumed_at: datetime
    calories: float
    proteins: float
    carbs: float
    fats: float
    notes: Optional[str]
    source: str

    model_config = ConfigDict(from_attributes=True)


class MacroTotals(BaseModel):
    calories: float
    proteins: float
    carbs: float
    fats: float


class TargetTotals(BaseModel):
    calories: Optional[float] = None
    proteins: Optional[float] = None
    carbs: Optional[float] = None
    fats: Optional[float] = None


class MealListResponse(BaseModel):
    day: date
    totals: MacroTotals
    meals: list[MealRead]


class ImageAnalysisResponse(BaseModel):
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack|other)$")
    food_name: str
    calories: float
    proteins: float
    carbs: float
    fats: float
    notes: str
    confidence: float


class ManualMealItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: Optional[str] = Field(default=None, max_length=80)


class ManualMealEstimateRequest(BaseModel):
    items: list[ManualMealItem] = Field(min_length=1, max_length=20)
    hint: Optional[str] = Field(default=None, max_length=400)
    meal_type: Optional[str] = Field(default=None, pattern="^(breakfast|lunch|dinner|snack|other)$")


class ManualMealEstimateResponse(BaseModel):
    food_name: str
    calories: float
    proteins: float
    carbs: float
    fats: float
    notes: str
    confidence: float


class DailySummaryResponse(BaseModel):
    day: date
    is_closed: bool
    status: str
    day_end_time: Optional[time]
    meals_count: int
    totals: MacroTotals
    targets: TargetTotals
    advice: Optional[str]


class WaterCreate(BaseModel):
    amount_ml: int = Field(default=250, ge=50, le=2000)
    consumed_at: Optional[datetime] = None


class WaterIntakeRead(BaseModel):
    id: int
    amount_ml: int
    consumed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WaterSummaryResponse(BaseModel):
    day: date
    total_ml: int
    target_ml: Optional[int]
    entries: list[WaterIntakeRead]


class DailyNeeds(BaseModel):
    calories: float
    proteins: float
    carbs: float
    fats: float


class DailyNeedsResponse(BaseModel):
    day: date
    needs: DailyNeeds
    totals: MacroTotals
    water_ml: Optional[int]
    source: str
    note: Optional[str]


class TimelinePhase(BaseModel):
    label: str
    time: str
    status: str
    suggestion: Optional[str]


class TimelineResponse(BaseModel):
    day: date
    phases: list[TimelinePhase]
    guidance: Optional[str]


class BodyPhotoRead(BaseModel):
    id: int
    kind: str
    image_url: str
    captured_at: datetime
    ai_summary: Optional[str]


class BodyPhotoCompareResponse(BaseModel):
    latest: BodyPhotoRead
    previous: BodyPhotoRead
    comparison: Optional[str]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
