from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import RelayConfig, SourceGroup
from app.routes.auth import get_admin_user
from app.telegram.relay import start_relay, stop_relay, get_run_debug

router = APIRouter(prefix="/api/relay")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


async def reload_relay_if_running(db: AsyncSession) -> bool:
    """Redémarre le relais si celui-ci était en marche. Retourne True si un redémarrage a eu lieu."""
    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    if not (config and config.is_running):
        return False
    await stop_relay()
    await _start_relay_from_db(db)
    return True


async def _start_relay_from_db(db: AsyncSession) -> int | None:
    """Démarre le relais depuis la config en base. Retourne un message d'erreur ou None."""
    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()

    r = await db.execute(select(SourceGroup).where(SourceGroup.is_active == True))
    active_groups = r.scalars().all()
    if not active_groups:
        return "Aucun groupe source actif sélectionné."

    source_ids: dict[int, list[int]] = {}
    dest_map: dict[int, dict[int, int]] = {}
    fictive_names: dict[int, dict[int, str]] = {}
    undestined = 0
    for g in active_groups:
        source_ids.setdefault(g.session_id, []).append(g.group_id)
        if g.fictive_name:
            fictive_names.setdefault(g.session_id, {})[g.group_id] = g.fictive_name
        if g.destination_group_id is not None:
            dest_map.setdefault(g.session_id, {})[g.group_id] = g.destination_group_id
        else:
            undestined += 1

    keywords = None
    if config and config.filter_enabled:
        keywords = [kw.strip() for kw in (config.filter_keywords or "").split(",") if kw.strip()] or None

    await start_relay(source_ids, dest_map, keywords, fictive_names=fictive_names)
    if config:
        config.is_running = True
        await db.commit()
    return f"{undestined} source(s) sans destination ignorée(s)." if undestined else None


@router.post("/start")
async def relay_start(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    error = await _start_relay_from_db(db)
    return await _status_html(db, error)


@router.post("/restart")
async def relay_restart(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    await stop_relay()
    error = await _start_relay_from_db(db)
    return await _status_html(db, error)


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

    head = '<div class="flex items-center gap-2">' + "".join(parts) + '</div>'
    head += _debug_html()
    return HTMLResponse(head)


def _stat_card(label: str, value: int, color: str = "#334155") -> str:
    return f'<div class="flex-1 text-center" style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);padding:10px 8px;"><div style="font-size:20px;font-weight:700;color:{color};">{value}</div><div class="text-xs text-secondary mt-1">{label}</div></div>'


def _debug_html() -> str:
    debug = get_run_debug()
    stats = debug["stats"]
    lines = debug["lines"]
    started = debug["started_at"]

    stat_cards = "".join([
        _stat_card("Reçus", stats["received"], "#0F172A"),
        _stat_card("Relayés", stats["forwarded"], "#009252"),
        _stat_card("Hors source", stats["outside"], "#64748B"),
        _stat_card("Filtrés", stats["filtered"], "#F59E0B"),
        _stat_card("Skippés", stats["skip"], "#94A3B8"),
        _stat_card("Erreurs", stats["errors"], "#EF4444"),
    ])

    if not lines:
        log_html = '<div class="text-xs text-muted py-2">Aucune activité de relais pour l\'instant.</div>'
    else:
        log_html = '<div class="text-xs font-mono" style="line-height:1.6;">' + "<br>".join(f'<div>{_esc_line(l)}</div>' for l in lines) + '</div>'

    started_html = f"<span class='text-xs text-muted'>Début : {started.replace('T', ' ')[:19]}</span>" if started else ""
    return f"""
    <div class="mt-4" style="border-top:1px solid var(--border-subtle);padding-top:16px;">
        <div class="flex items-center justify-between mb-2">
            <div class="text-sm font-semibold" style="color:var(--navy-dark);">Débogage de la dernière exécution</div>
            {started_html}
        </div>
        <div class="flex gap-2 mb-3">{stat_cards}</div>
        <div style="background:#0F172A;color:#A5B4CC;border-radius:var(--radius-md);padding:10px 12px;max-height:220px;overflow:auto;">{log_html}</div>
    </div>
    """


def _esc_line(line: str) -> str:
    return line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
