from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import RelayConfig, SourceGroup
from app.routes.auth import get_admin_user
from app.telegram.client import telethon_manager

router = APIRouter(prefix="/api/groups")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


@router.get("")
async def list_groups(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    if not telethon_manager.is_connected:
        return HTMLResponse('<div class="alert alert-warning mt-2">Connect Telegram first</div>')

    dialogs = await telethon_manager.client.get_dialogs()

    r = await db.execute(select(SourceGroup))
    saved = {sg.group_id: sg for sg in r.scalars().all()}

    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    dest_id = config.destination_group_id if config else None

    rows = []
    for d in dialogs:
        if not (d.is_group or d.is_channel):
            continue
        checked = "checked" if d.id in saved and saved[d.id].is_active else ""
        is_dest = "badge badge-primary badge-xs" if d.id == dest_id else ""
        rows.append(f"""<tr>
            <td>{d.title or "Untitled"} <span class="{is_dest}">dest</span></td>
            <td>
                <input type="checkbox" class="checkbox checkbox-sm"
                       hx-post="/api/groups/toggle"
                       hx-vals='{{"group_id":{d.id},"title":"{d.title or 'Untitled'}","active":{str(not checked).lower()}}}'
                       hx-trigger="change"
                       hx-target="#groups-msg" {checked} />
            </td>
            <td>
                <button class="btn btn-ghost btn-xs"
                        hx-post="/api/groups/set-destination"
                        hx-vals='{{"group_id":{d.id},"title":"{d.title or 'Untitled'}"}}'
                        hx-target="#dest-msg">
                    Set dest
                </button>
            </td>
        </tr>""")

    if not rows:
        return HTMLResponse('<div class="alert mt-2">No groups or channels found</div>')

    return HTMLResponse(f"""
        <div id="groups-msg"></div>
        <div id="dest-msg"></div>
        <table class="table table-zebra">
            <thead><tr><th>Group</th><th>Source</th><th>Destination</th></tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
    """)


@router.post("/toggle")
async def toggle_source(
    request: Request,
    group_id: int = Form(...),
    title: str = Form(...),
    active: bool = Form(...),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    result = await db.execute(select(SourceGroup).where(SourceGroup.group_id == group_id))
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_active = active
        existing.title = title
    else:
        db.add(SourceGroup(group_id=group_id, title=title, is_active=active))
    await db.commit()

    status = "added to" if active else "removed from"
    return HTMLResponse(f'<div class="text-xs text-success">{title} {status} sources</div>')


@router.post("/set-destination")
async def set_destination(
    request: Request,
    group_id: int = Form(...),
    title: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    if config:
        config.destination_group_id = group_id
        config.destination_title = title
    else:
        db.add(RelayConfig(destination_group_id=group_id, destination_title=title))
    await db.commit()
    return HTMLResponse(f'<div class="text-xs text-success">Destination → {title}</div>')
