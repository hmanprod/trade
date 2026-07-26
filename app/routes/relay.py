from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import RelayConfig, SourceGroup
from app.routes.auth import get_admin_user
from app.telegram.relay import start_relay, stop_relay

router = APIRouter(prefix="/api/relay")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


@router.post("/start")
async def relay_start(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    if not config or not config.destination_group_id:
        return await _status_html(db, "No destination configured")

    r = await db.execute(select(SourceGroup).where(SourceGroup.is_active == True))
    active_groups = r.scalars().all()
    if not active_groups:
        return await _status_html(db, "No active source groups")

    source_ids = [g.group_id for g in active_groups]
    keywords = [kw.strip() for kw in (config.filter_keywords or "").split(",") if kw.strip()] or None

    await start_relay(source_ids, config.destination_group_id, keywords)
    config.is_running = True
    await db.commit()
    return await _status_html(db)


@router.post("/stop")
async def relay_stop(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    await stop_relay()
    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    if config:
        config.is_running = False
        await db.commit()
    return await _status_html(db)


@router.get("/status")
async def relay_status(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard
    return await _status_html(db)


async def _status_html(db: AsyncSession, error: str | None = None):
    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()

    parts = []
    if error:
        parts.append(f'<div class="alert alert-error text-sm">{error}</div>')

    if config and config.is_running:
        parts.append('<span class="badge badge-success">Running</span>')
    else:
        parts.append('<span class="badge badge-neutral">Stopped</span>')

    if config and config.destination_title:
        parts.append(f'<span class="text-sm">→ {config.destination_title}</span>')

    return HTMLResponse(" ".join(parts))
