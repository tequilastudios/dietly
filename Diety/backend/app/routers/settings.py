import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..config import settings as app_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import AISettings, User
from ..schemas import AISettingsRead, AISettingsUpdate, OllamaModelsResponse


router = APIRouter(prefix="/api/settings", tags=["Settings"])


def _get_or_create_ai_settings(db: Session, user: User) -> AISettings:
    settings = db.query(AISettings).filter(AISettings.user_id == user.id).first()
    if settings:
        return settings

    settings = AISettings(user_id=user.id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _resolve_ollama_base_url(ai_settings: AISettings, override: str | None = None) -> str:
    if override and override.strip():
        return override.strip().rstrip("/")
    if ai_settings.ollama_base_url and ai_settings.ollama_base_url.strip():
        return ai_settings.ollama_base_url.strip().rstrip("/")
    return app_settings.ollama_base_url.rstrip("/")


def _extract_model_names(payload: dict) -> list[str]:
    models = payload.get("models", [])
    names: list[str] = []
    for entry in models:
        if not isinstance(entry, dict):
            continue
        model_name = entry.get("name") or entry.get("model")
        if model_name:
            names.append(str(model_name))
    return sorted(set(names))


def _vision_candidates(model_names: list[str]) -> list[str]:
    keywords = ("llava", "vision", "ocr", "bakllava", "moondream", "minicpm")
    candidates = [name for name in model_names if any(keyword in name.lower() for keyword in keywords)]
    return candidates or model_names


@router.get("", response_model=AISettingsRead)
def get_ai_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_create_ai_settings(db, current_user)


@router.put("", response_model=AISettingsRead)
def update_ai_settings(
    payload: AISettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = _get_or_create_ai_settings(db, current_user)

    string_nullable_fields = {
        "ollama_base_url",
        "sex",
        "activity_level",
        "goals",
        "dietary_preferences",
        "allergies",
        "system_prompt",
    }
    string_trim_fields = {"vision_model", "text_model", "response_language"}

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in string_nullable_fields and isinstance(value, str):
            value = value.strip() or None
        if field in string_trim_fields and isinstance(value, str):
            value = value.strip()
        setattr(settings, field, value)

    db.add(settings)
    db.commit()
    db.refresh(settings)

    return settings


@router.get("/models", response_model=OllamaModelsResponse)
async def get_ollama_models(
    base_url: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ai_settings = _get_or_create_ai_settings(db, current_user)
    target_url = _resolve_ollama_base_url(ai_settings, base_url)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{target_url}/api/tags")
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Impossibile leggere i modelli da Ollama. "
                "Verifica URL, servizio avviato e accessibilita dal container backend."
            ),
        ) from exc

    model_names = _extract_model_names(payload)
    if not model_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nessun modello trovato in Ollama per l'URL specificato.",
        )

    vision = _vision_candidates(model_names)
    text = [name for name in model_names if name not in vision] or model_names

    default_vision_model = ai_settings.vision_model or app_settings.ollama_model
    default_text_model = ai_settings.text_model or app_settings.ollama_text_model

    return {
        "base_url": target_url,
        "models": model_names,
        "vision_candidates": vision,
        "text_candidates": text,
        "default_vision_model": default_vision_model,
        "default_text_model": default_text_model,
        "default_vision_installed": default_vision_model in model_names,
        "default_text_installed": default_text_model in model_names,
    }
