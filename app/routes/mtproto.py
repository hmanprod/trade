from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.db.models import MTProtoSession
from app.routes.auth import get_admin_user
from app.telegram.client import telethon_manager

router = APIRouter(prefix="/api/mtproto")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


@router.post("/send-code")
async def send_code(request: Request, phone: str = Form(...)):
    guard = _guard(request)
    if guard:
        return guard

    if not telethon_manager.is_connected:
        await telethon_manager.create_client()
    client = telethon_manager.client

    try:
        sent = await client.send_code_request(phone)
    except Exception as e:
        return HTMLResponse(f"""
            <div class="alert alert-error">{e}</div>
            <form hx-post="/api/mtproto/send-code" hx-target="#mtproto-form"
                  class="flex gap-2 items-end mt-2">
                <fieldset class="fieldset flex-1">
                    <label class="fieldset-label">Phone number</label>
                    <input type="text" name="phone" class="input w-full"
                           placeholder="+33612345678" value="{phone}" required>
                </fieldset>
                <button class="btn btn-primary">Send code</button>
            </form>
        """)

    return HTMLResponse(f"""
        <form hx-post="/api/mtproto/verify" hx-target="#mtproto-form"
              class="flex gap-2 items-end">
            <input type="hidden" name="phone" value="{phone}">
            <input type="hidden" name="phone_code_hash" value="{sent.phone_code_hash}">
            <fieldset class="fieldset flex-1">
                <label class="fieldset-label">Code received on Telegram</label>
                <input type="text" name="code" class="input w-full"
                       placeholder="12345" required autofocus>
            </fieldset>
            <button class="btn btn-primary">Verify</button>
        </form>
    """)


@router.post("/verify")
async def verify(
    request: Request,
    phone: str = Form(...),
    code: str = Form(""),
    phone_code_hash: str = Form(...),
    password: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    client = telethon_manager.client
    if not client or not client.is_connected():
        return HTMLResponse('<div class="alert alert-error">Not connected</div>')

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
                return HTMLResponse(f"""
                    <form hx-post="/api/mtproto/verify" hx-target="#mtproto-form"
                          class="flex gap-2 items-end">
                        <input type="hidden" name="phone" value="{phone}">
                        <input type="hidden" name="phone_code_hash" value="{phone_code_hash}">
                        <fieldset class="fieldset flex-1">
                            <label class="fieldset-label">2FA password required</label>
                            <input type="password" name="password" class="input w-full"
                                   placeholder="Enter 2FA password" required autofocus>
                        </fieldset>
                        <button class="btn btn-primary">Submit</button>
                    </form>
                """)
            if "PHONE_CODE_INVALID" in error_msg:
                error_msg = "Invalid code"
            return HTMLResponse(f"""
                <div class="alert alert-error">{error_msg}</div>
                <button class="btn btn-ghost btn-sm" hx-get="/api/mtproto/status"
                        hx-target="#mtproto-form" hx-swap="outerHTML">
                    Try again
                </button>
            """)

    session_str = client.session.save()
    from cryptography.fernet import Fernet

    cipher = Fernet(settings.encryption_key.encode())
    encrypted = cipher.encrypt(session_str.encode()).decode()

    result = await db.execute(select(MTProtoSession).limit(1))
    existing = result.scalar_one_or_none()
    if existing:
        existing.phone_number = phone
        existing.string_session = encrypted
        existing.is_connected = True
    else:
        db.add(MTProtoSession(phone_number=phone, string_session=encrypted, is_connected=True))
    await db.commit()

    telethon_manager.phone = phone
    return HTMLResponse(f"""
        <div class="alert alert-success">Connected as {phone}</div>
        <button class="btn btn-ghost btn-sm mt-2"
                onclick="disconnect_modal.showModal()">
            Disconnect
        </button>
        <dialog id="disconnect_modal" class="modal">
            <div class="modal-box">
                <h3 class="text-lg font-bold">Disconnect Telegram?</h3>
                <p class="py-4">This will disconnect your Telegram account. You will need to reconnect to restart the relay.</p>
                <div class="modal-action">
                    <form method="dialog">
                        <button class="btn btn-ghost">Cancel</button>
                    </form>
                    <button class="btn btn-error"
                            hx-get="/api/mtproto/disconnect" hx-target="#mtproto-form"
                            onclick="document.getElementById('disconnect_modal').close()">
                        Confirm disconnect
                    </button>
                </div>
            </div>
            <form method="dialog" class="modal-backdrop">
                <button>close</button>
            </form>
        </dialog>
    """)


@router.get("/disconnect")
async def disconnect(request: Request, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    await telethon_manager.disconnect()
    result = await db.execute(select(MTProtoSession).limit(1))
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_connected = False
        await db.commit()

    return HTMLResponse("""
        <form hx-post="/api/mtproto/send-code" hx-target="#mtproto-form"
              class="flex gap-2 items-end">
            <fieldset class="fieldset flex-1">
                <label class="fieldset-label">Phone number</label>
                <input type="text" name="phone" class="input w-full"
                       placeholder="+33612345678" required>
            </fieldset>
            <button class="btn btn-primary">Connect</button>
        </form>
    """)


@router.get("/status")
async def status(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    if telethon_manager.is_connected:
        phone = telethon_manager.phone or "Connected"
        return HTMLResponse(f"""
            <div class="flex items-center gap-2">
                <span class="badge badge-success">Connected</span>
                <span>{phone}</span>
            </div>
        """)
    return HTMLResponse("""
        <div class="flex items-center gap-2">
            <span class="badge badge-neutral">Disconnected</span>
        </div>
    """)
