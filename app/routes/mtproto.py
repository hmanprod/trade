from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telethon import TelegramClient

from app.config import settings
from app.db.engine import get_db, async_session
from app.db.models import MTProtoSession, SourceGroup
from app.routes.auth import get_admin_user
from app.telegram.client import multi_telethon_manager

router = APIRouter(prefix="/api/mtproto")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


_pending_clients: dict[str, dict] = {}


@router.post("/send-code")
async def send_code(request: Request, phone: str = Form(...)):
    guard = _guard(request)
    if guard:
        return guard

    client = TelegramClient(":memory:", settings.telegram_api_id, settings.telegram_api_hash)
    await client.connect()

    try:
        sent = await client.send_code_request(phone)
    except Exception as e:
        await client.disconnect()
        return HTMLResponse(f"""
            <div class="alert alert-error mb-3">{e}</div>
            <form hx-post="/api/mtproto/send-code" hx-target="#accounts-section" hx-swap="outerHTML"
                  class="flex gap-3 items-end mt-3">
                <div class="flex-1">
                    <label class="fieldset-label">Phone number</label>
                    <input type="text" name="phone" class="input"
                           placeholder="+33612345678" value="{phone}" required>
                </div>
                <button class="btn btn-primary">Send code</button>
            </form>
        """)

    token = str(id(client))
    _pending_clients[token] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash}

    return HTMLResponse(f"""
        <form hx-post="/api/mtproto/verify" hx-target="#add-account-form"
              class="flex gap-3 items-end mt-3">
            <input type="hidden" name="token" value="{token}">
            <div class="flex-1">
                <label class="form-label mb-2">Verification Code (sent to Telegram app)</label>
                <input type="text" name="code" class="input w-full"
                       placeholder="12345" required autofocus>
            </div>
            <button class="btn btn-primary">Verify & Complete</button>
        </form>
    """)


@router.post("/verify")
async def verify(
    request: Request,
    token: str = Form(...),
    code: str = Form(""),
    password: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    pending = _pending_clients.pop(token, None)
    if not pending:
        return HTMLResponse('<div class="alert alert-error">Session expired, please try again.</div>')

    client = pending["client"]
    phone = pending["phone"]
    phone_code_hash = pending["phone_code_hash"]

    if password:
        try:
            await client.sign_in(password=password)
        except Exception as e:
            return HTMLResponse(f'<div class="alert alert-error">{e}</div>')
    else:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except Exception as e:
            error_msg = str(e)
            if "PasswordNeededError" in type(e).__name__ or "password" in error_msg.lower():
                token = str(id(client))
                _pending_clients[token] = pending
                return HTMLResponse(f"""
                    <form hx-post="/api/mtproto/verify" hx-target="#add-account-form"
                          class="flex gap-3 items-end mt-3">
                        <input type="hidden" name="token" value="{token}">
                        <div class="flex-1">
                            <label class="form-label mb-2">2FA Password Required</label>
                            <input type="password" name="password" class="input w-full"
                                   placeholder="Enter Telegram 2FA password" required autofocus>
                        </div>
                        <button class="btn btn-primary">Submit Password</button>
                    </form>
                """)
            if "PHONE_CODE_INVALID" in error_msg:
                error_msg = "Invalid verification code provided."
            return HTMLResponse(f"""
                <div class="alert alert-error mb-2">{error_msg}</div>
                <button class="btn btn-ghost btn-sm" hx-get="/api/mtproto/accounts"
                        hx-target="#accounts-section" hx-swap="outerHTML">
                    Back to accounts
                </button>
            """)

    session_str = client.session.save()
    from cryptography.fernet import Fernet

    cipher = Fernet(settings.encryption_key.encode())
    encrypted = cipher.encrypt(session_str.encode()).decode()

    me = await client.get_me()
    display_name = me.username or me.first_name or phone

    session_row = MTProtoSession(phone_number=phone, string_session=encrypted, is_connected=True, label=display_name)
    db.add(session_row)
    await db.commit()
    await db.refresh(session_row)

    await multi_telethon_manager.add(session_row.id, client, phone)

    return HTMLResponse("""
        <div class="alert alert-success mb-3">Telegram account successfully connected.</div>
        <button class="btn btn-primary btn-sm" hx-get="/api/mtproto/accounts"
                hx-target="#accounts-section" hx-swap="outerHTML">
            Refresh Accounts List
        </button>
    """)


@router.get("/accounts")
async def list_accounts(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(MTProtoSession).order_by(MTProtoSession.created_at.desc()))
    rows = r.scalars().all()

    if not rows:
        return HTMLResponse("""
            <div class="onboard-card">
                <h2 class="onboard-title">Connect your Telegram Account</h2>
                <p class="onboard-desc">Link a Telegram account via official MTProto session to discover groups and start forwarding messages in real time.</p>
                <button class="btn btn-primary"
                        hx-get="/api/mtproto/add-form"
                        hx-target="#accounts-section" hx-swap="outerHTML">
                    + Connect Telegram Account
                </button>
            </div>
        """)

    items = []
    for row in rows:
        connected = multi_telethon_manager.is_connected(row.id)
        status_cls = "status-connected" if connected else "status-disconnected"
        status_text = "Connected" if connected else "Disconnected"
        phone = row.phone_number
        label = row.label or "Account"
        initial = (label[0] if label else phone[-2:]).upper()
        items.append(f"""<div class="account-card">
            <div class="account-info">
                <div class="account-avatar">{initial}</div>
                <div class="account-details">
                    <div class="account-label">{label} <span class="account-phone font-normal">({phone})</span></div>
                    <div class="mt-2"><span class="status {status_cls}">{status_text}</span></div>
                </div>
            </div>
            <div class="account-actions">
                <button class="btn btn-ghost btn-xs text-error"
                        type="button"
                        onclick="showConfirmModal('Delete Account', 'Are you sure you want to delete session {phone}?', function() {{ htmx.ajax('DELETE', '/api/mtproto/{row.id}', {{target: '#accounts-section', swap: 'outerHTML'}}); }})">
                    Delete
                </button>
            </div>
        </div>""")

    return HTMLResponse(f"""
        <div class="block">
            <div class="block-header">
                <div class="block-title-group">
                    <div class="block-title-icon" style="background:#ECFDF5; color:#009252;">
                        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                    </div>
                    <div>
                        <h2 class="block-title">Telegram Accounts</h2>
                        <div class="block-subtitle">Active MTProto sessions linked to this relay engine</div>
                    </div>
                </div>
                <button class="btn btn-primary btn-sm"
                        hx-get="/api/mtproto/add-form"
                        hx-target="#accounts-section" hx-swap="outerHTML">
                    + Add Account
                </button>
            </div>
            <div>
                {"".join(items)}
            </div>
            <div id="add-account-form"></div>
            <div id="accounts-msg"></div>
            <div class="flex gap-2 mt-4 pt-3" style="border-top:1px solid var(--border-subtle)">
                <button class="btn btn-xs btn-warning"
                        type="button"
                        onclick="showConfirmModal('Disconnect All Accounts', 'Are you sure you want to disconnect all active sessions?', function() {{ htmx.ajax('POST', '/api/mtproto/disconnect-all', {{target: '#accounts-section', swap: 'outerHTML'}}); }})">
                    Disconnect All
                </button>
                <button class="btn btn-xs btn-error"
                        type="button"
                        onclick="showConfirmModal('Delete All Accounts', 'Are you sure you want to PERMANENTLY delete all sessions? This action cannot be undone.', function() {{ htmx.ajax('DELETE', '/api/mtproto/all', {{target: '#accounts-section', swap: 'outerHTML'}}); }})">
                    Delete All Accounts
                </button>
            </div>
        </div>
    """)


@router.get("/add-form")
async def add_form(request: Request):
    guard = _guard(request)
    if guard:
        return guard

    return HTMLResponse("""
        <div class="block" style="margin-top:16px; border:1px solid var(--primary-border); background:var(--primary-light);">
            <div class="block-header" style="border-bottom: 1px solid rgba(0,146,82,0.15)">
                <div>
                    <h2 class="block-title" style="color:var(--primary)">Connect Telegram Account</h2>
                    <div class="block-subtitle">Enter phone number to receive an official MTProto connection code</div>
                </div>
            </div>
            <form hx-post="/api/mtproto/send-code" hx-target="#accounts-section" hx-swap="outerHTML"
                  class="flex gap-3 items-end" style="padding-top:12px;">
                <div style="flex:3;">
                    <label class="fieldset-label">Phone Number</label>
                    <input type="text" name="phone" class="input"
                           placeholder="+33612345678" required>
                </div>
                <button class="btn btn-primary" style="white-space:nowrap;">Send Verification Code</button>
            </form>
        </div>
    """)


@router.delete("/{session_id}")
async def delete_account(request: Request, session_id: int, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    await multi_telethon_manager.remove(session_id)
    r = await db.execute(select(SourceGroup).where(SourceGroup.session_id == session_id))
    for sg in r.scalars().all():
        await db.delete(sg)
    r = await db.execute(select(MTProtoSession).where(MTProtoSession.id == session_id))
    row = r.scalar_one_or_none()
    if row:
        await db.delete(row)
    await db.commit()

    return await list_accounts(request, db)


@router.post("/disconnect-all")
async def disconnect_all(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    await multi_telethon_manager.disconnect_all()
    r = await db.execute(select(MTProtoSession))
    for row in r.scalars().all():
        row.is_connected = False
    await db.commit()

    return await list_accounts(request, db)


@router.delete("/all")
async def delete_all_accounts(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    await multi_telethon_manager.disconnect_all()
    r = await db.execute(select(SourceGroup))
    for sg in r.scalars().all():
        await db.delete(sg)
    r = await db.execute(select(MTProtoSession))
    for row in r.scalars().all():
        await db.delete(row)
    await db.commit()

    return await list_accounts(request, db)


@router.get("/status")
async def status(request: Request):
    guard = _guard(request)
    if guard:
        return guard

    total = 0
    connected = 0
    async with async_session() as db:
        r = await db.execute(select(MTProtoSession))
        rows = r.scalars().all()
        total = len(rows)
        connected = sum(1 for row in rows if multi_telethon_manager.is_connected(row.id))

    if total == 0:
        return HTMLResponse('<span class="badge badge-neutral"><span class="status-dot status-dot-inactive"></span> No accounts</span>')

    if connected > 0:
        return HTMLResponse(f'<span class="badge badge-success"><span class="status-dot status-dot-active"></span> {connected}/{total} Connected</span>')
    else:
        return HTMLResponse(f'<span class="badge badge-warning"><span class="status-dot status-dot-inactive"></span> 0/{total} Connected</span>')
