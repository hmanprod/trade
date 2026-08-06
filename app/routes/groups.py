from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import MTProtoSession, SourceGroup
from app.routes.auth import get_admin_user
from app.telegram.client import multi_telethon_manager

router = APIRouter(prefix="/api/groups")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


def _esc(value: str) -> str:
    return value.replace("'", "\\'")


async def _all_dialogs_by_session() -> dict[int, list]:
    """Récupère TOUS les dialogues (groupes/canaux) de chaque compte connecté."""
    out: dict[int, list] = {}
    for sid, client in multi_telethon_manager.get_all():
        if not client.is_connected():
            continue
        dialogs = []
        async for d in client.iter_dialogs():
            if d.is_group or d.is_channel:
                dialogs.append(d)
        out[sid] = dialogs
    return out


@router.get("")
async def list_groups(request: Request, session_id: int = 0, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(MTProtoSession).order_by(MTProtoSession.created_at))
    sessions = r.scalars().all()

    if not sessions:
        return HTMLResponse('<div class="alert alert-warning mt-2">Aucun compte Telegram connecté pour l\'instant.</div>')

    if session_id == 0:
        session_id = sessions[0].id

    if session_id not in {s.id for s in sessions}:
        return HTMLResponse('<div class="alert alert-error">Compte sélectionné invalide</div>')

    client = multi_telethon_manager.get(session_id)
    if not client or not client.is_connected():
        return HTMLResponse('<div class="alert alert-warning mt-2">Le compte sélectionné est actuellement déconnecté</div>')

    dialogs = []
    async for d in client.iter_dialogs():
        if d.is_group or d.is_channel:
            dialogs.append(d)

    r = await db.execute(select(SourceGroup).where(SourceGroup.session_id == session_id))
    saved = {sg.group_id: sg for sg in r.scalars().all()}

    session_switcher = []
    for s in sessions:
        label = s.label or s.phone_number
        selected = "selected" if s.id == session_id else ""
        session_switcher.append(f'<option value="{s.id}" {selected}>{label}</option>')

    # Options de destination : compte -> groupe, réutilisées pour le picker par source et le batch
    all_dialogs = await _all_dialogs_by_session()
    session_labels = {s.id: (s.label or s.phone_number) for s in sessions}

    def dest_options_html(selected_group_id: int | None = None) -> str:
        opts = ['<option value="0">— À définir —</option>']
        for sid in sorted(all_dialogs):
            label = session_labels.get(sid, f"Compte {sid}")
            for d in all_dialogs[sid]:
                title = d.title or "Sans titre"
                sel = " selected" if d.id == selected_group_id else ""
                opts.append(f'<option value="{d.id}"{sel}>@ {_esc(label)} — {_esc(title)}</option>')
        return "".join(opts)

    rows = []
    for d in dialogs:
        checked = "checked" if d.id in saved and saved[d.id].is_active else ""
        sg = saved.get(d.id)
        dest_label = ""
        dest_badge = ""
        if sg and sg.destination_group_id is not None:
            dest_badge = '<span class="badge badge-success text-xs">Destination</span>'
            for sid in sorted(all_dialogs):
                for dd in all_dialogs[sid]:
                    if dd.id == sg.destination_group_id:
                        dest_label = f"→ {_esc(dd.title or 'Sans titre')} (@ {session_labels.get(sid, '?')})"
        if not dest_label:
            dest_label = "À définir"
        select_chk = f'<input type="checkbox" class="checkbox checkbox-sm" name="source_group_ids" value="{sg.id}" hx-trigger="none"/>' if sg else ""
        escaped_title = _esc(d.title or "Sans titre")
        rows.append(f"""<tr>
            <td>
                <div class="font-semibold">{d.title or "Sans titre"}</div>
            </td>
            <td>
                <label class="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" class="checkbox"
                           hx-post="/api/groups/toggle"
                           hx-vals='{{"group_id":{d.id},"title":"{escaped_title}","active":{str(not checked).lower()},"session_id":{session_id}}}'
                           hx-trigger="change"
                           hx-target="#groups-msg" {checked} />
                    <span class="text-xs text-secondary">Scraper</span>
                </label>
            </td>
            <td>
                <div class="flex flex-col gap-1">
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-secondary">{dest_label}</span>
                        {dest_badge}
                    </div>
                    <select class="select select-sm"
                            hx-post="/api/groups/set-destination"
                            hx-vals='{{"source_group_id":{d.id},"session_id":{session_id},"title":"{escaped_title}"}}'
                            hx-target="#dest-msg"
                            hx-trigger="change"
                            name="dest_group_id">
                        {dest_options_html(sg.destination_group_id if sg else None)}
                    </select>
                </div>
            </td>
            <td class="text-center">
                {select_chk}
            </td>
        </tr>""")

    if not rows:
        return HTMLResponse(f"""
            <div id="groups-msg" class="mb-2"></div>
            <div id="dest-msg" class="mb-2"></div>
            <div class="flex gap-3 items-center mb-4">
                <label class="form-label mb-0">Compte :</label>
                <select class="select" hx-get="/api/groups" hx-target="#groups-list"
                        name="session_id" hx-trigger="change">
                    {"".join(session_switcher)}
                </select>
            </div>
            <div class="alert alert-warning">Aucun groupe ou canal trouvé pour ce compte.</div>
        """)

    return HTMLResponse(f"""
        <div id="groups-msg" class="mb-2"></div>
        <div id="dest-msg" class="mb-2"></div>
        <div class="flex flex-wrap gap-3 items-center mb-4">
            <label class="form-label mb-0">Compte :</label>
            <select class="select" hx-get="/api/groups" hx-target="#groups-list"
                    name="session_id" hx-trigger="change">
                {"".join(session_switcher)}
            </select>
        </div>
        <form hx-post="/api/groups/batch-destination" hx-target="#dest-msg"
              hx-include="#gdest-body input[name='source_group_ids']"
              class="flex flex-wrap gap-3 items-end mb-4 p-3" style="background:var(--primary-light); border:1px solid var(--primary-border); border-radius:var(--radius-md);">
            <div>
                <label class="fieldset-label">Appliquer une destination</label>
                <select class="select" name="dest_group_id">
                    {dest_options_html()}
                </select>
            </div>
            <button class="btn btn-primary btn-sm" type="submit">Appliquer aux sélectionnés</button>
            <button class="btn btn-primary btn-sm" type="submit" name="apply_to_all" value="on">Appliquer à tous</button>
        </form>
        <div class="table-wrapper" id="gdest-target">
            <table class="table" id="source-group-table">
                <thead>
                    <tr>
                        <th>Groupe / Canal</th>
                        <th>Source à scraper</th>
                        <th>Destination</th>
                        <th class="text-center">Sélection</th>
                    </tr>
                </thead>
                <tbody id="gdest-body">{"".join(rows)}</tbody>
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

    status = "ajouté aux sources actives" if active else "retiré des sources actives"
    return HTMLResponse(f'<div class="alert alert-success text-xs py-2">Mise à jour de la source : <strong>{title}</strong> {status}.</div>')


@router.post("/set-destination")
async def set_destination(
    request: Request,
    source_group_id: int = Form(...),
    session_id: int = Form(...),
    title: str = Form(...),
    dest_group_id: int = Form(0),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    result = await db.execute(
        select(SourceGroup).where(
            SourceGroup.group_id == source_group_id, SourceGroup.session_id == session_id
        )
    )
    sg = result.scalar_one_or_none()
    if not sg:
        sg = SourceGroup(group_id=source_group_id, title=title, is_active=True, session_id=session_id)
        db.add(sg)

    if dest_group_id:
        dest_session = None
        for sid, dialogs in (await _all_dialogs_by_session()).items():
            if any(d.id == dest_group_id for d in dialogs):
                dest_session = sid
                break
        sg.destination_group_id = dest_group_id
        sg.destination_session_id = dest_session
        msg = f'Destination définie pour <strong>{title}</strong>.'
    else:
        sg.destination_group_id = None
        sg.destination_session_id = None
        msg = f'Destination retirée pour <strong>{title}</strong> (À définir).'
    await db.commit()
    return HTMLResponse(f'<div class="alert alert-success text-xs py-2">{msg}</div>')


@router.post("/batch-destination")
async def batch_destination(
    request: Request,
    dest_group_id: int = Form(0),
    source_group_ids: list[int] = Form([]),
    apply_to_all: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(SourceGroup).where(SourceGroup.is_active == True))
    groups = r.scalars().all()

    if apply_to_all == "on":
        targets = groups
    else:
        targets = [g for g in groups if g.id in source_group_ids]

    if dest_group_id:
        dest_session = None
        for sid, dialogs in (await _all_dialogs_by_session()).items():
            if any(d.id == dest_group_id for d in dialogs):
                dest_session = sid
                break
        for g in targets:
            g.destination_group_id = dest_group_id
            g.destination_session_id = dest_session
        msg = f"Destination appliquée à {len(targets)} source(s)."
    else:
        for g in targets:
            g.destination_group_id = None
            g.destination_session_id = None
        msg = f"Destination retirée sur {len(targets)} source(s)."
    await db.commit()
    return HTMLResponse(f'<div class="alert alert-success text-xs py-2">{msg}</div>')
