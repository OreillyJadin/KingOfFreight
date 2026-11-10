from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.auth import require_broker
from app.services.usage import CLIENT_EVENTS, normalize_path, record_event

router = APIRouter(prefix="/api/usage", dependencies=[Depends(require_broker)])


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
