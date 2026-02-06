import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import BodyPhoto, User
from ..ollama_client import analyze_body_photo, compare_body_photos
from ..schemas import BodyPhotoCompareResponse, BodyPhotoRead
from ..services import ai_preferences_from_user, log_ai_interaction


router = APIRouter(prefix="/api/body-photos", tags=["BodyPhotos"])


def _store_upload(file: UploadFile, user_id: int) -> str:
    extension = Path(file.filename or "").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{extension}"
    user_dir = Path(settings.upload_dir) / "body" / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / filename

    with file_path.open("wb") as buffer:
        buffer.write(file.file.read())

    relative_path = file_path.relative_to(Path(settings.upload_dir)).as_posix()
    return f"/static/uploads/{relative_path}"


@router.get("", response_model=list[BodyPhotoRead])
def list_body_photos(
    kind: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(BodyPhoto).filter(BodyPhoto.user_id == current_user.id)
    if kind:
        query = query.filter(BodyPhoto.kind == kind.lower())
    photos = query.order_by(BodyPhoto.captured_at.desc()).all()
    return [
        BodyPhotoRead(
            id=photo.id,
            kind=photo.kind,
            image_url=photo.image_path,
            captured_at=photo.captured_at,
            ai_summary=photo.ai_summary,
        )
        for photo in photos
    ]


@router.post("", response_model=BodyPhotoRead)
async def upload_body_photo(
    kind: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kind = kind.lower()
    if kind not in {"front", "back"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo foto non valido.")

    image_url = _store_upload(image, current_user.id)
    ai_preferences = ai_preferences_from_user(current_user) or {}

    ai_summary = None
    ai_payload = None
    analysis = None
    try:
        image.file.seek(0)
        analysis = await analyze_body_photo(image.file.read(), kind=kind, preferences=ai_preferences)
        ai_summary = analysis.get("summary")
        ai_payload = analysis.get("raw")
    except Exception:
        ai_summary = "Analisi AI non disponibile per questa foto."

    photo = BodyPhoto(
        user_id=current_user.id,
        kind=kind,
        image_path=image_url,
        captured_at=datetime.utcnow(),
        ai_summary=ai_summary,
        ai_payload=ai_payload,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    if analysis:
        log_ai_interaction(
            db,
            current_user.id,
            kind="body_photo_analysis",
            model=ai_preferences.get("vision_model"),
            input_payload={"kind": kind},
            output_payload=analysis,
            meta={"photo_id": photo.id},
        )

    return BodyPhotoRead(
        id=photo.id,
        kind=photo.kind,
        image_url=photo.image_path,
        captured_at=photo.captured_at,
        ai_summary=photo.ai_summary,
    )


@router.get("/compare", response_model=BodyPhotoCompareResponse)
async def compare_latest_photos(
    kind: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kind = kind.lower()
    photos = (
        db.query(BodyPhoto)
        .filter(BodyPhoto.user_id == current_user.id, BodyPhoto.kind == kind)
        .order_by(BodyPhoto.captured_at.desc())
        .limit(2)
        .all()
    )
    if len(photos) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Servono almeno 2 foto per il confronto.")

    latest, previous = photos[0], photos[1]
    ai_preferences = ai_preferences_from_user(current_user) or {}

    comparison = None
    try:
        comparison = await compare_body_photos(
            {
                "latest": {
                    "date": latest.captured_at.isoformat(),
                    "summary": latest.ai_summary,
                },
                "previous": {
                    "date": previous.captured_at.isoformat(),
                    "summary": previous.ai_summary,
                },
            },
            preferences=ai_preferences,
        )
    except Exception:
        comparison = "Confronto non disponibile al momento."

    log_ai_interaction(
        db,
        current_user.id,
        kind="body_photo_compare",
        model=ai_preferences.get("text_model"),
        input_payload={
            "latest_id": latest.id,
            "previous_id": previous.id,
        },
        output_payload={"comparison": comparison},
    )

    return {
        "latest": BodyPhotoRead(
            id=latest.id,
            kind=latest.kind,
            image_url=latest.image_path,
            captured_at=latest.captured_at,
            ai_summary=latest.ai_summary,
        ),
        "previous": BodyPhotoRead(
            id=previous.id,
            kind=previous.kind,
            image_url=previous.image_path,
            captured_at=previous.captured_at,
            ai_summary=previous.ai_summary,
        ),
        "comparison": comparison,
    }
