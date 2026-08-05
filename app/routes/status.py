from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text

from app.config import settings
from app.db.engine import async_session
from app.db.models import MTProtoSession
from app.routes.auth import get_admin_user
from app.telegram.client import multi_telethon_manager

router = APIRouter(prefix="/api/system")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


def _row(icon: str, label: str, status: str, detail: str) -> str:
    state = {
        "ok": ("status-connected", "check"),
        "warn": ("status-warn", "minus"),
        "err": ("status-disconnected", "x"),
    }[status]
    return f"""
    <div class="status-row">
        <div class="status-row-icon">{icon}</div>
        <div class="status-row-label">{label}</div>
        <div class="status-row-detail">{detail}</div>
        <div class="status-row-value">
            <span class="status {state[0]}">
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                    {state[1] == 'check' and '<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>' or ''}
                    {state[1] == 'minus' and '<path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14"/>' or ''}
                    {state[1] == 'x' and '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>' or ''}
                </svg>
            </span>
        </div>
    </div>"""


@router.get("/status")
async def system_status(request: Request):
    guard = _guard(request)
    if guard:
        return guard

    rows = []

    # Telegram API
    api_ok = bool(settings.telegram_api_id and settings.telegram_api_hash)
    if api_ok:
        rows.append(_row(
            "TG",
            "Telegram API",
            "ok",
            f"api_id {settings.telegram_api_id} configured",
        ))
    else:
        rows.append(_row(
            "TG",
            "Telegram API",
            "err",
            "missing API credentials",
        ))

    # Account(s)
    async with async_session() as db:
        r = await db.execute(select(MTProtoSession))
        sessions = r.scalars().all()
        total = len(sessions)
        connected = sum(1 for row in sessions if multi_telethon_manager.is_connected(row.id))

    if total == 0:
        rows.append(_row(
            "AC",
            "Account",
            "warn",
            "no account connected",
        ))
    elif connected > 0:
        rows.append(_row(
            "AC",
            "Account",
            "ok",
            f"{connected}/{total} connected",
        ))
    else:
        rows.append(_row(
            "AC",
            "Account",
            "err",
            f"{total} account(s) disconnected",
        ))

    # Database
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        rows.append(_row(
            "DB",
            "Database",
            "ok",
            "connection healthy",
        ))
    except Exception:
        rows.append(_row(
            "DB",
            "Database",
            "err",
            "connection failed",
        ))

    return HTMLResponse(f"""
        <div class="block">
            <div class="block-header">
                <div class="block-title-group">
                    <div class="block-title-icon" style="background:#EFF6FF; color:#1D4ED8;">
                        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                    </div>
                    <div>
                        <h2 class="block-title">System Status</h2>
                        <div class="block-subtitle">Live verification of core services powering the relay</div>
                    </div>
                </div>
            </div>
            <div class="flex flex-col gap-2">
                {''.join(rows)}
            </div>
        </div>
    """)
