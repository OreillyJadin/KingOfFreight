import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.types import Scope

from app.auth import COOKIE_NAME, decode_session, ensure_bootstrap_user, session_user
from app.config import get_settings
from app.db import SessionLocal
from app.integrations.email import GraphEmailProvider, get_email_provider
from app.integrations.llm import get_llm_provider
from app.routers.api import _ingest_email_message, dev_public, protected, public
from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router
from app.routers.usage import router as usage_router
from app.routers.assistant import router as assistant_router
from app.routers.twilio import router as twilio_router
from app.routers.outlook import router as outlook_router
from app.routers.kof import router as kof_router
from app.routers.kof_messages import router as kof_messages_router
from app.routers.kof_emails import router as kof_emails_router
from app.routers.customer_updates import router as customer_updates_router
from app.services.checkins import run_checkin_tick
from app.services.usage import prune_usage_events, record_event

settings = get_settings()
logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class ImmutableStaticFiles(StaticFiles):
    def file_response(
        self,
        full_path: os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _run_tick() -> None:
    prune_usage_events()
    with SessionLocal() as db:
        run_checkin_tick(db)


def _poll_inbox() -> None:
    provider = get_email_provider()
    with SessionLocal() as db:
        for message in provider.fetch_new_messages():
            _ingest_email_message(db, message, get_llm_provider())
        if isinstance(provider, GraphEmailProvider):
            provider.commit_poll()


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_bootstrap_user(db, settings.bootstrap_username)
    try:
        from app.services.kof_sync import fail_interrupted_sync_runs

        with SessionLocal() as db:
            fail_interrupted_sync_runs(db)
    except Exception:
        logger.warning(
            "Failed to clean interrupted KOF sync runs during startup",
            exc_info=True,
        )
    if settings.scheduler_enabled:
        scheduler.add_job(
            _run_tick,
            "interval",
            seconds=settings.scheduler_interval_seconds,
            id="checkin-tick",
        )
        if settings.email_provider in {"auto", "graph", "outlook"}:
            scheduler.add_job(
                _poll_inbox,
                "interval",
                seconds=settings.scheduler_interval_seconds,
                id="inbox-poll",
            )
        from app.services.kof_sync import run_scheduled_kof_sync

        scheduler.add_job(
            run_scheduled_kof_sync,
            "interval",
            minutes=max(1, settings.kof_sync_interval_minutes),
            id="kof-sync",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="KingOfFreight API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def password_setup_gate(request: Request, call_next: RequestResponseEndpoint):
    allowed_paths = {
        "/api/auth/me",
        "/api/auth/set-password",
        "/api/usage/events",
        "/api/auth/logout",
        "/api/email/oauth/callback",
    }
    if request.url.path.startswith("/api/") and request.url.path not in allowed_paths:
        token = request.cookies.get(COOKIE_NAME)
        payload = decode_session(token) if token else None
        if payload is not None and payload.get("uid") is not None:
            with SessionLocal() as db:
                user = session_user(payload, db)
                if user is not None and user.must_set_password:
                    return JSONResponse(
                        {"detail": "password_setup_required"}, status_code=403
                    )
    return await call_next(request)


@app.middleware("http")
async def usage_logging(request: Request, call_next: RequestResponseEndpoint):
    response = await call_next(request)
    try:
        identity = getattr(request.state, "usage_identity", None)
        route = request.scope.get("route")
        for event, detail in getattr(request.state, "usage_events", []):
            if identity is not None and (
                response.status_code < 400 or event == "assistant_question"
            ):
                await run_in_threadpool(
                    record_event,
                    identity,
                    event,
                    getattr(route, "path", None),
                    request.headers.get("user-agent", ""),
                    {**(detail or {}), "status_code": response.status_code},
                )
    except Exception:
        logger.warning("Usage request logging failed")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(usage_router)
app.include_router(assistant_router)
app.include_router(twilio_router)
app.include_router(outlook_router)
app.include_router(protected)
app.include_router(public)
app.include_router(kof_router)
app.include_router(kof_messages_router)
app.include_router(kof_emails_router)
app.include_router(customer_updates_router)
if settings.env == "development":
    app.include_router(dev_public)


def mount_frontend(application: FastAPI, dist_dir: Path = FRONTEND_DIST) -> None:
    if not dist_dir.is_dir() or not (dist_dir / "index.html").is_file():
        return
    asset_dir = dist_dir / "assets"
    if asset_dir.is_dir():
        application.mount(
            "/assets", ImmutableStaticFiles(directory=asset_dir), name="frontend-assets"
        )

    @application.get("/{frontend_path:path}", include_in_schema=False)
    def serve_frontend(frontend_path: str) -> FileResponse:
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        root = dist_dir.resolve()
        target = (root / frontend_path).resolve()
        if root not in target.parents and target != root:
            raise HTTPException(status_code=404, detail="Not Found")
        index_file = root / "index.html"
        response_file = target if target.is_file() else index_file
        headers = {"Cache-Control": "no-cache"} if response_file == index_file else None
        return FileResponse(response_file, headers=headers)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


mount_frontend(app)
