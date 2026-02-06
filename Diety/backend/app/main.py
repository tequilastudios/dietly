import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings as app_settings
from .database import Base, engine
from .migrations import run_startup_migrations
from .routers import auth, body_photos, chat, meals, routine, settings as settings_router, summary, water


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=app_settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(routine.router)
app.include_router(meals.router)
app.include_router(summary.router)
app.include_router(settings_router.router)
app.include_router(water.router)
app.include_router(body_photos.router)
app.include_router(chat.router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    run_startup_migrations()
    os.makedirs(app_settings.upload_dir, exist_ok=True)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/settings", include_in_schema=False)
def settings_page() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "settings.html"))


@app.get("/health", tags=["System"])
def health_check() -> dict:
    return {"status": "ok", "app": app_settings.app_name}
