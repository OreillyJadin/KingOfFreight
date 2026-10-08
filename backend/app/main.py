from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.email import get_email_provider
from app.integrations.llm import get_llm_provider
from app.routers.api import _ingest_email_message, dev_public, protected, public
from app.routers.auth import router as auth_router
from app.services.checkins import run_checkin_tick

settings = get_settings()
scheduler = BackgroundScheduler(timezone="UTC")


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
