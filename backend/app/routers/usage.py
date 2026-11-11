from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.auth import require_broker
from app.auth import COOKIE_NAME
from app.services.usage_health import accept_client_error, record_metric
from app.services.usage import (
    CLIENT_EVENTS,
    normalize_path,
    record_event,
    record_heartbeat,
)

router = APIRouter(prefix="/api/usage", dependencies=[Depends(require_broker)])


@router.post("/client-error", status_code=202)
async def client_error(request: Request):
    try:
        if len(await request.body()) > 16384:
            return {"accepted": False}
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("message"), str):
            return {"accepted": False}
        path = normalize_path(payload.get("path"))
        if not path or not payload["message"].strip():
            return {"accepted": False}
        if not accept_client_error(request.cookies.get(COOKIE_NAME, "")):
            return {"accepted": False}
        accepted = await run_in_threadpool(
            record_metric,
            request.state.usage_identity,
            path,
            "CLIENT",
            0,
            0,
            "client",
            payload["message"][:1000],
        )
        return {"accepted": accepted}
    except Exception:
        return {"accepted": False}


@router.post("/heartbeat", status_code=202)
async def heartbeat(request: Request):
    try:
        if len(await request.body()) > 4096:
            return {"accepted": False}
        payload = await request.json()
        path = (
            normalize_path(payload.get("path")) if isinstance(payload, dict) else None
        )
        if not path:
            return {"accepted": False}
        accepted = await run_in_threadpool(
            record_heartbeat,
            request.state.usage_identity,
            path,
            request.headers.get("user-agent", ""),
        )
        return {"accepted": accepted}
    except Exception:
        return {"accepted": False}


@router.post("/events", status_code=202)
async def events(request: Request):
    try:
        raw = await request.body()
        if len(raw) > 4096:
            return {"accepted": False}
        payload = await request.json()
        if not isinstance(payload, dict):
            return {"accepted": False}
        event = payload.get("event")
        path = normalize_path(payload.get("path"))
        if not isinstance(event, str) or event not in CLIENT_EVENTS or not path:
            return {"accepted": False}
        accepted = await run_in_threadpool(
            record_event,
            request.state.usage_identity,
            event,
            path,
            request.headers.get("user-agent", ""),
        )
        return {"accepted": accepted}
    except Exception:
        return {"accepted": False}
