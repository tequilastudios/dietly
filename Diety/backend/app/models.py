from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    routine = relationship("Routine", back_populates="user", uselist=False, cascade="all, delete-orphan")
    meals = relationship("Meal", back_populates="user", cascade="all, delete-orphan")
    daily_summaries = relationship("DailySummary", back_populates="user", cascade="all, delete-orphan")
    ai_settings = relationship("AISettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    water_intakes = relationship("WaterIntake", back_populates="user", cascade="all, delete-orphan")
    body_photos = relationship("BodyPhoto", back_populates="user", cascade="all, delete-orphan")
    ai_interactions = relationship("AIInteraction", back_populates="user", cascade="all, delete-orphan")


class Routine(Base):
    __tablename__ = "routines"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    breakfast_time = Column(Time, default=time(8, 0), nullable=False)
    lunch_time = Column(Time, default=time(13, 0), nullable=False)
    dinner_time = Column(Time, default=time(20, 0), nullable=False)
    day_end_time = Column(Time, nullable=True)

    calorie_target = Column(Float, nullable=True)
    protein_target = Column(Float, nullable=True)
    carbs_target = Column(Float, nullable=True)
    fats_target = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="routine")


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    meal_type = Column(String(32), nullable=False)
    food_name = Column(String(255), nullable=False)
    consumed_at = Column(DateTime, nullable=False, index=True)

    calories = Column(Float, default=0, nullable=False)
    proteins = Column(Float, default=0, nullable=False)
    carbs = Column(Float, default=0, nullable=False)
    fats = Column(Float, default=0, nullable=False)

    notes = Column(Text, nullable=True)
    source = Column(String(16), default="manual", nullable=False)
    ai_payload = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="meals")


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_summary_user_day"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    day = Column(Date, nullable=False, index=True)

    calories = Column(Float, default=0, nullable=False)
    proteins = Column(Float, default=0, nullable=False)
    carbs = Column(Float, default=0, nullable=False)
    fats = Column(Float, default=0, nullable=False)

    status = Column(String(16), default="open", nullable=False)
    advice = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="daily_summaries")


class AISettings(Base):
    __tablename__ = "ai_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    ollama_base_url = Column(String(255), nullable=True)
    vision_model = Column(String(120), default="llava:latest", nullable=False)
    text_model = Column(String(120), default="mistral:latest", nullable=False)
    timeout_seconds = Column(Integer, default=180, nullable=False)
    temperature = Column(Float, default=0.2, nullable=False)

    macro_fallback_enabled = Column(Boolean, default=True, nullable=False)
    meal_type_autodetect_enabled = Column(Boolean, default=True, nullable=False)
    smart_routine_enabled = Column(Boolean, default=False, nullable=False)

    age_years = Column(Integer, nullable=True)
    sex = Column(String(32), nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    target_weight_kg = Column(Float, nullable=True)
    activity_level = Column(String(32), nullable=True)
    goals = Column(Text, nullable=True)
    dietary_preferences = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    response_language = Column(String(16), default="it", nullable=False)
    system_prompt = Column(Text, nullable=True)
    reasoning_cycles = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="ai_settings")


class AIInteraction(Base):
    __tablename__ = "ai_interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    model = Column(String(120), nullable=True)
    input_payload = Column(Text, nullable=True)
    output_payload = Column(Text, nullable=True)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="ai_interactions")


class WaterIntake(Base):
    __tablename__ = "water_intakes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount_ml = Column(Integer, default=250, nullable=False)
    consumed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="water_intakes")


class BodyPhoto(Base):
    __tablename__ = "body_photos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    image_path = Column(String(255), nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    ai_summary = Column(Text, nullable=True)
    ai_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="body_photos")
