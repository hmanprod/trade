from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import MTProtoSession, RelayConfig, SourceGroup
from app.routes.auth import get_admin_user
from app.telegram.client import multi_telethon_manager

router = APIRouter(prefix="/api/groups")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


@router.get("")
async def list_groups(request: Request, session_id: int = 0, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(MTProtoSession).order_by(MTProtoSession.created_at))
    sessions = r.scalars().all()

    if not sessions:
        return HTMLResponse('<div class="alert alert-warning mt-2">No Telegram accounts connected yet.</div>')

    if session_id == 0:
        session_id = sessions[0].id

    if session_id not in {s.id for s in sessions}:
        return HTMLResponse('<div class="alert alert-error">Invalid account selected</div>')

    client = multi_telethon_manager.get(session_id)
    if not client or not client.is_connected():
        return HTMLResponse('<div class="alert alert-warning mt-2">Selected account is currently disconnected</div>')

    dialogs = await client.get_dialogs()

    r = await db.execute(select(SourceGroup).where(SourceGroup.session_id == session_id))
    saved = {sg.group_id: sg for sg in r.scalars().all()}

    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    dest_id = config.destination_group_id if config else None

    session_switcher = []
    for s in sessions:
        label = s.label or s.phone_number
        selected = "selected" if s.id == session_id else ""
        session_switcher.append(f'<option value="{s.id}" {selected}>{label}</option>')

    rows = []
    for d in dialogs:
        if not (d.is_group or d.is_channel):
            continue
        checked = "checked" if d.id in saved and saved[d.id].is_active else ""
        is_dest_badge = '<span class="badge badge-primary text-xs ml-2">DESTINATION</span>' if d.id == dest_id else ""
        escaped_title = (d.title or "Untitled").replace("'", "\\'")
        rows.append(f"""<tr>
            <td>
                <div class="font-semibold">{d.title or "Untitled"}</div>
                {is_dest_badge}
            </td>
            <td>
                <label class="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" class="checkbox"
                           hx-post="/api/groups/toggle"
                           hx-vals='{{"group_id":{d.id},"title":"{escaped_title}","active":{str(not checked).lower()},"session_id":{session_id}}}'
                           hx-trigger="change"
                           hx-target="#groups-msg" {checked} />
                    <span class="text-xs text-secondary">Scrape Source</span>
                </label>
            </td>
            <td>
                <button class="btn btn-ghost btn-xs"
                        hx-post="/api/groups/set-destination"
                        hx-vals='{{"group_id":{d.id},"title":"{escaped_title}"}}'
                        hx-target="#dest-msg">
                    Target Destination
                </button>
            </td>
        </tr>""")

    if not rows:
        return HTMLResponse(f"""
            <div class="flex gap-3 items-center mb-4">
                <label class="form-label mb-0">Active Account Session:</label>
                <select class="select" hx-get="/api/groups" hx-target="#groups-list"
                        name="session_id" hx-trigger="change">
                    {"".join(session_switcher)}
                </select>
            </div>
            <div class="alert alert-warning">No groups or channel dialogs found for this account.</div>
        """)

    return HTMLResponse(f"""
        <div id="groups-msg" class="mb-2"></div>
        <div id="dest-msg" class="mb-2"></div>
        <div class="flex gap-3 items-center mb-4">
            <label class="form-label mb-0">Account Dialog Scope:</label>
            <select class="select" hx-get="/api/groups" hx-target="#groups-list"
                    name="session_id" hx-trigger="change">
                {"".join(session_switcher)}
            </select>
        </div>
        <div class="table-wrapper">
            <table class="table">
                <thead>
                    <tr>
                        <th>Group / Channel Name</th>
                        <th>Source Scraping</th>
                        <th>Destination Action</th>
                    </tr>
                </thead>
                <tbody>{"".join(rows)}</tbody>
            </table>
        </div>
    """)


@router.post("/toggle")
async def toggle_source(
    request: Request,
    group_id: int = Form(...),
    title: str = Form(...),
    active: bool = Form(...),
    session_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    result = await db.execute(
        select(SourceGroup).where(
            SourceGroup.group_id == group_id, SourceGroup.session_id == session_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_active = active
        existing.title = title
    else:
        db.add(SourceGroup(group_id=group_id, title=title, is_active=active, session_id=session_id))
    await db.commit()

    status = "added to active sources" if active else "removed from active sources"
    return HTMLResponse(f'<div class="alert alert-success text-xs py-2">Source update: <strong>{title}</strong> {status}.</div>')


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
    return HTMLResponse(f'<div class="alert alert-success text-xs py-2">Destination target updated → <strong>{title}</strong></div>')
