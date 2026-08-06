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

    r = await db.execute(select(SourceGroup).where(SourceGroup.is_active == True))
    active_groups = r.scalars().all()
    if not active_groups:
        return await _status_html(db, "Aucun groupe source actif sélectionné.")

    source_ids: dict[int, list[int]] = {}
    dest_map: dict[int, dict[int, int]] = {}
    undestined = 0
    for g in active_groups:
        source_ids.setdefault(g.session_id, []).append(g.group_id)
        if g.destination_group_id is not None:
            dest_map.setdefault(g.session_id, {})[g.group_id] = g.destination_group_id
        else:
            undestined += 1

    keywords = None
    if config and config.filter_enabled:
        keywords = [kw.strip() for kw in (config.filter_keywords or "").split(",") if kw.strip()] or None

    await start_relay(source_ids, dest_map, keywords)
    config.is_running = True
    await db.commit()
    return await _status_html(db, f"{undestined} source(s) sans destination ignorée(s)." if undestined else None)


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
        parts.append(f'<div class="alert alert-error text-xs mb-2">{error}</div>')

    if config and config.is_running:
        parts.append('<span class="badge badge-success"><span class="status-dot status-dot-active"></span> EN COURS</span>')
    else:
        parts.append('<span class="badge badge-neutral"><span class="status-dot status-dot-inactive"></span> ARRÊTÉ</span>')

    return HTMLResponse('<div class="flex items-center gap-2">' + "".join(parts) + '</div>')
