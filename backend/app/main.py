from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.email import get_email_provider
from app.integrations.llm import get_llm_provider
from app.routers.api import _ingest_email_message, dev_public, protected, public
from app.routers.auth import router as auth_router
from app.services.checkins import run_checkin_tick

settings = get_settings()
scheduler = BackgroundScheduler(timezone="UTC")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _run_tick() -> None:
    with SessionLocal() as db:
        run_checkin_tick(db)


def _poll_inbox() -> None:
    provider = get_email_provider()
    with SessionLocal() as db:
        for message in provider.fetch_new_messages():
            _ingest_email_message(db, message, get_llm_provider())


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    if settings.scheduler_enabled:
        scheduler.add_job(
            _run_tick,
            "interval",
            seconds=settings.scheduler_interval_seconds,
            id="checkin-tick",
        )
        if settings.email_provider == "graph":
            scheduler.add_job(
                _poll_inbox,
                "interval",
                seconds=settings.scheduler_interval_seconds,
                id="inbox-poll",
            )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="KingOfFreight API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(protected)
app.include_router(public)
if settings.env == "development":
    app.include_router(dev_public)


def mount_frontend(application: FastAPI, dist_dir: Path = FRONTEND_DIST) -> None:
    if not dist_dir.is_dir() or not (dist_dir / "index.html").is_file():
        return
    asset_dir = dist_dir / "assets"
    if asset_dir.is_dir():
        application.mount(
            "/assets", StaticFiles(directory=asset_dir), name="frontend-assets"
        )

    @application.get("/{frontend_path:path}", include_in_schema=False)
    def serve_frontend(frontend_path: str) -> FileResponse:
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        root = dist_dir.resolve()
        target = (root / frontend_path).resolve()
        if root not in target.parents and target != root:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(target if target.is_file() else root / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


mount_frontend(app)
