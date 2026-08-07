from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import MTProtoSession, SourceGroup
from app.routes.auth import get_admin_user
from app.routes.relay import reload_relay_if_running
from app.telegram.client import multi_telethon_manager

router = APIRouter(prefix="/api/groups")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


def _esc(value: str) -> str:
    return value.replace("'", "\\'")


def _is_admin_or_creator(dialog) -> bool:
    """True si le compte est créateur ou admin du groupe/canal."""
    ent = getattr(dialog, "entity", None)
    if ent is None:
        return False
    if getattr(ent, "creator", False):
        return True
    return getattr(ent, "admin_rights", None) is not None


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


async def _admin_dialogs_by_session() -> dict[int, list]:
    """Dialogues (groupes/canaux) dont le compte est créateur ou admin."""
    all_dialogs = await _all_dialogs_by_session()
    return {
        sid: [d for d in dialogs if _is_admin_or_creator(d)]
        for sid, dialogs in all_dialogs.items()
    }


@router.get("")
async def list_groups(request: Request, session_id: int = 0, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(MTProtoSession).order_by(MTProtoSession.created_at))
    sessions = r.scalars().all()

    if not sessions:
        return HTMLResponse('<div class="alert alert-warning mt-2">Aucun compte Telegram connecté pour l\'instant.</div>')

    if session_id and session_id not in {s.id for s in sessions}:
        return HTMLResponse('<div class="alert alert-error">Compte sélectionné invalide</div>')

    session_labels = {s.id: (s.label or s.phone_number) for s in sessions}

    all_dialogs = await _all_dialogs_by_session()
    admin_dialogs = await _admin_dialogs_by_session()

    if session_id:
        all_dialogs = {session_id: all_dialogs.get(session_id, [])}

    r = await db.execute(select(SourceGroup))
    saved_by_session: dict[int, dict[int, SourceGroup]] = {}
    for sg in r.scalars().all():
        saved_by_session.setdefault(sg.session_id, {})[sg.group_id] = sg

    # Filtre par compte (option "Tous les comptes" par défaut)
    filter_switcher = ['<option value="0">Tous les comptes</option>']
    for s in sessions:
        label = session_labels[s.id]
        selected = "selected" if s.id == session_id else ""
        filter_switcher.append(f'<option value="{s.id}" {selected}>{label}</option>')

    def dest_options_html(src_session_id: int, selected_group_id: int | None = None) -> str:
        opts = ['<option value="0">— À définir —</option>']
        label = session_labels.get(src_session_id, f"Compte {src_session_id}")
        for d in admin_dialogs.get(src_session_id, []):
            title = d.title or "Sans titre"
            sel = " selected" if d.id == selected_group_id else ""
            opts.append(f'<option value="{d.id}"{sel}>@ {_esc(label)} — {_esc(title)}</option>')
        if not admin_dialogs.get(src_session_id):
            opts.append('<option value="0" disabled>⚠ Aucun groupe où vous êtes admin</option>')
        return "".join(opts)

    rows = []
    total_rows = 0
    for sid in sorted(all_dialogs):
        if not multi_telethon_manager.is_connected(sid):
            continue
        account_label = session_labels.get(sid, f"Compte {sid}")
        saved = saved_by_session.get(sid, {})
        for d in all_dialogs[sid]:
            total_rows += 1
            checked = "checked" if d.id in saved and saved[d.id].is_active else ""
            sg = saved.get(d.id)
            escaped_title = _esc(d.title or "Sans titre")
            fictive = _esc(sg.fictive_name) if sg and sg.fictive_name else ""
            rows.append(f"""<tr>
            <td>
                <div class="font-semibold">{d.title or "Sans titre"}</div>
            </td>
            <td>
                <span class="badge badge-neutral">{_esc(account_label)}</span>
            </td>
            <td>
                <input type="text" class="input input-sm" name="fictive_{sid}_{d.id}"
                       value="{fictive}" placeholder="Nom fictif">
            </td>
            <td>
                <label class="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" class="checkbox"
                           name="source_{sid}_{d.id}" {checked} />
                    <span class="text-xs text-secondary">Scraper</span>
                </label>
            </td>
            <td>
                <div class="flex flex-col gap-1">
                    <select class="select select-sm" name="dest_{sid}_{d.id}">
                        {dest_options_html(sid, sg.destination_group_id if sg else None)}
                    </select>
                </div>
            </td>
        </tr>""")

    if total_rows == 0:
        return HTMLResponse(f"""
            <div id="groups-msg" class="mb-2"></div>
            <div class="flex gap-3 items-center mb-4">
                <label class="form-label mb-0">Compte :</label>
                <select class="select" hx-get="/api/groups" hx-target="#groups-list"
                        name="session_id" hx-trigger="change">
                    {"".join(filter_switcher)}
                </select>
            </div>
            <div class="alert alert-warning">Aucun groupe ou canal trouvé.</div>
        """)

    return HTMLResponse(f"""
        <div id="groups-msg" class="mb-2"></div>
        <div class="flex flex-wrap gap-3 items-center mb-4">
            <label class="form-label mb-0">Compte :</label>
            <select class="select" hx-get="/api/groups" hx-target="#groups-list"
                    name="session_id" hx-trigger="change">
                {"".join(filter_switcher)}
            </select>
        </div>
        <form id="groups-form"
              hx-post="/api/groups/apply"
              hx-target="#groups-msg"
              hx-swap="innerHTML">
            <input type="hidden" name="session_id" value="{session_id}">
            <div class="flex items-center justify-between mb-3">
                <div></div>
                <button type="submit" class="btn btn-primary btn-sm"
                        hx-disabled-elt="this" hx-indicator="#apply-groups-indicator">
                    <span id="apply-groups-indicator" class="htmx-indicator spinner"></span>
                    Appliquer les modifications
                </button>
            </div>
            <div class="table-wrapper" id="gdest-target">
                <table class="table" id="source-group-table">
                    <thead>
                        <tr>
                            <th>Groupe / Canal</th>
                            <th>Compte</th>
                            <th>Nom fictif</th>
                            <th>Source à scraper</th>
                            <th>Destination</th>
                        </tr>
                    </thead>
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>
        </form>
    """)


@router.post("/apply")
async def apply_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    form = await request.form()

    all_dialogs = await _all_dialogs_by_session()
    admin_dialogs = await _admin_dialogs_by_session()

    active_count = 0
    warnings = []

    for sid in sorted(all_dialogs):
        if not multi_telethon_manager.is_connected(sid):
            continue
        admin_ids = {dd.id for dd in admin_dialogs.get(sid, [])}
        for d in all_dialogs[sid]:
            group_id = d.id
            title = d.title or "Sans titre"

            r = await db.execute(
                select(SourceGroup).where(
                    SourceGroup.group_id == group_id, SourceGroup.session_id == sid
                )
            )
            sg = r.scalar_one_or_none()
            if not sg:
                sg = SourceGroup(group_id=group_id, title=title, is_active=False, session_id=sid)
                db.add(sg)

            is_active = form.get(f"source_{sid}_{group_id}") is not None
            sg.is_active = is_active
            sg.title = title
            fictive_val = form.get(f"fictive_{sid}_{group_id}")
            if fictive_val is not None:
                fictive = fictive_val.strip() or None
                if fictive != sg.fictive_name:
                    sg.fictive_name = fictive
            if is_active:
                active_count += 1

            dest_val = form.get(f"dest_{sid}_{group_id}")
            if dest_val is not None:
                dest_group_id = int(dest_val)
                if dest_group_id and dest_group_id not in admin_ids:
                    warnings.append(f"Destination invalide ignorée pour « {title} »")
                else:
                    sg.destination_group_id = dest_group_id or None
                    sg.destination_session_id = sid if dest_group_id else None

    await db.commit()

    restart_msg = ""
    if await reload_relay_if_running(db):
        restart_msg = ' <span class="text-info">Relais redémarré automatiquement.</span>'

    if warnings:
        body = ' '.join(warnings)
        html = f'<div class="alert alert-warning text-xs py-2">{body}{restart_msg}</div>'
    else:
        html = f'<div class="alert alert-success text-xs py-2">Modifications appliquées — <strong>{active_count}</strong> source(s) active(s).{restart_msg}</div>'
    return HTMLResponse(html)
