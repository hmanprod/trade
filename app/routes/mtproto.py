from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telethon import TelegramClient
from telethon.sessions import StringSession

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


def _connect_step(phone: str = "", error: str = "") -> str:
    error_html = f'<div class="alert alert-error mb-3"><svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>{error}</div>' if error else ''
    return f"""
    <div>
        {error_html}
        <form hx-post="/api/mtproto/send-code" hx-target="#mtproto-step" hx-swap="innerHTML"
              hx-indicator="#phone-spinner" hx-disabled-elt="#send-code-btn">
            <label class="fieldset-label">Numéro de téléphone</label>
            <input type="text" name="phone" class="input mb-3"
                   placeholder="+33612345678" value="{phone}" required autofocus>
            <button id="send-code-btn" class="btn btn-primary" style="white-space:nowrap;">
                <span id="phone-spinner" class="spinner htmx-indicator"></span>
                Envoyer le code de vérification
            </button>
        </form>
        <div class="reassurance">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
            </svg>
            <span>Votre compte est utilisé uniquement pour ce relais. La session est chiffrée et stockée localement, et vous pouvez la supprimer à tout moment depuis cette page.</span>
        </div>
    </div>"""


@router.get("/add-form-step")
async def add_form_step(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    return HTMLResponse(_connect_step())


@router.post("/send-code")
async def send_code(request: Request, phone: str = Form(...)):
    guard = _guard(request)
    if guard:
        return guard

    client = TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash)
    await client.connect()

    try:
        sent = await client.send_code_request(phone)
    except Exception as e:
        await client.disconnect()
        return HTMLResponse(_connect_step(phone=phone, error=str(e)))

    token = str(id(client))
    _pending_clients[token] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash}

    return HTMLResponse(f"""
    <div>
        <div class="alert alert-success mb-3">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            Code envoyé à <b class="font-semibold">{phone}</b>. Saisissez le code de vérification reçu dans votre application Telegram.
        </div>
        <form hx-post="/api/mtproto/verify" hx-target="#mtproto-step" hx-swap="innerHTML"
              hx-indicator="#verify-spinner" hx-disabled-elt="#verify-btn">
            <input type="hidden" name="token" value="{token}">
            <label class="fieldset-label">Code de vérification</label>
            <input type="text" name="code" class="input code-input mb-3"
                   placeholder="12345" inputmode="numeric" maxlength="8" required autofocus>
            <button id="verify-btn" class="btn btn-primary" style="white-space:nowrap;">
                <span id="verify-spinner" class="spinner htmx-indicator"></span>
                Vérifier et connecter
            </button>
        </form>
        <div class="reassurance">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            <span>Si Telegram affiche « C'est bien vous ? » dans votre application, <b>confirmez</b> avant de saisir le code, sinon la connexion sera bloquée.</span>
        </div>
        <div class="mt-3">
            <button class="btn btn-ghost btn-sm" hx-get="/api/mtproto/add-form-step"
                hx-target="#mtproto-step" hx-swap="innerHTML">
                &larr; Utiliser un autre numéro
            </button>
        </div>
    </div>
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
        return HTMLResponse('<div class="alert alert-error">Session expirée, veuillez réessayer.</div>')

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
                <div>
                    <form hx-post="/api/mtproto/verify" hx-target="#mtproto-step" hx-swap="innerHTML"
                          hx-indicator="#password-spinner" hx-disabled-elt="#password-btn">
                        <input type="hidden" name="token" value="{token}">
                        <label class="fieldset-label">Mot de passe 2FA requis</label>
                        <input type="password" name="password" class="input mb-3"
                               placeholder="Entrez le mot de passe 2FA Telegram" required autofocus>
                        <button id="password-btn" class="btn btn-primary" style="white-space:nowrap;">
                            <span id="password-spinner" class="spinner htmx-indicator"></span>
                            Envoyer le mot de passe
                        </button>
                    </form>
                    <div class="mt-3">
                        <button class="btn btn-ghost btn-sm" hx-get="/api/mtproto/add-form-step"
                            hx-target="#mtproto-step" hx-swap="innerHTML">
                            &larr; Utiliser un autre numéro
                        </button>
                    </div>
                </div>
                """)
            if "PHONE_CODE_INVALID" in error_msg:
                error_msg = "Code de vérification invalide."
            return HTMLResponse(f"""
                <div class="alert alert-error mb-2">{error_msg}</div>
                <button class="btn btn-ghost btn-sm" hx-get="/api/mtproto/add-form-step"
                        hx-target="#mtproto-step" hx-swap="innerHTML">
                    &larr; Réessayer
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
        <div class="alert alert-success mb-3">Compte Telegram connecté avec succès.</div>
        <button class="btn btn-primary btn-sm" hx-get="/api/mtproto/accounts"
                hx-target="#accounts-section" hx-swap="innerHTML">
            Actualiser la liste des comptes
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
                            <h2 class="block-title">Comptes Telegram</h2>
                            <div class="block-subtitle">Sessions MTProto actives liées au moteur du relais</div>
                        </div>
                    </div>
                    <button class="btn btn-primary btn-sm"
                            hx-get="/api/mtproto/add-form"
                            hx-target="#accounts-section" hx-swap="innerHTML">
                        + Ajouter un compte
                    </button>
                </div>
                <div class="text-secondary text-sm">Aucun compte connecté pour l'instant. Ajoutez un compte Telegram pour commencer à scraper et transférer des messages.</div>
                <div id="add-account-form"></div>
            </div>
        """)

    items = []
    for row in rows:
        connected = multi_telethon_manager.is_connected(row.id)
        status_cls = "status-connected" if connected else "status-disconnected"
        status_text = "Connecté" if connected else "Déconnecté"
        phone = row.phone_number
        label = row.label or "Compte"
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
                <button class="btn btn-ghost btn-xs"
                        type="button"
                        onclick="htmx.ajax('POST', '/api/mtproto/{row.id}/reconnect', {{target: '#accounts-section', swap: 'innerHTML'}})"
                        {'disabled' if connected else ''}>Reconnecter</button>
                <button class="btn btn-ghost btn-xs text-error"
                        type="button"
                        onclick="showConfirmModal('Supprimer le compte', 'Voulez-vous vraiment supprimer la session {phone} ?', function() {{ htmx.ajax('DELETE', '/api/mtproto/{row.id}', {{target: '#accounts-section', swap: 'innerHTML'}}); }})">
                    Supprimer
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
                        <h2 class="block-title">Comptes Telegram</h2>
                        <div class="block-subtitle">Sessions MTProto actives liées au moteur du relais</div>
                    </div>
                </div>
                <button class="btn btn-primary btn-sm"
                        hx-get="/api/mtproto/add-form"
                        hx-target="#accounts-section" hx-swap="innerHTML">
                    + Ajouter un compte
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
                        onclick="showConfirmModal('Déconnecter tous les comptes', 'Voulez-vous vraiment déconnecter toutes les sessions actives ?', function() {{ htmx.ajax('POST', '/api/mtproto/disconnect-all', {{target: '#accounts-section', swap: 'innerHTML'}}); }})">
                    Déconnecter tous les comptes
                </button>
                <button class="btn btn-xs btn-error"
                        type="button"
                        onclick="showConfirmModal('Supprimer tous les comptes', 'Voulez-vous vraiment supprimer définitivement toutes les sessions ? Cette action est irréversible.', function() {{ htmx.ajax('DELETE', '/api/mtproto/all', {{target: '#accounts-section', swap: 'innerHTML'}}); }})">
                    Supprimer tous les comptes
                </button>
            </div>
        </div>
    """)


@router.get("/add-form")
async def add_form(request: Request):
    guard = _guard(request)
    if guard:
        return guard

    return HTMLResponse(f"""
        <div class="block" style="margin-top:16px; border:1px solid var(--primary-border); background:var(--primary-light);">
            <div class="block-header" style="border-bottom: 1px solid rgba(0,146,82,0.15)">
                <div>
                    <h2 class="block-title" style="color:var(--primary)">Connecter un compte Telegram</h2>
                    <div class="block-subtitle">Entrez votre numéro de téléphone pour recevoir un code de connexion MTProto officiel</div>
                </div>
            </div>
            <div id="mtproto-step">
                {_connect_step()}
            </div>
        </div>
    """)


@router.post("/{session_id}/reconnect")
async def reconnect_account(request: Request, session_id: int, db: AsyncSession = Depends(get_db)):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(MTProtoSession).where(MTProtoSession.id == session_id))
    row = r.scalar_one_or_none()
    if not row:
        return HTMLResponse('<div class="alert alert-error">Compte introuvable.</div>')

    try:
        from cryptography.fernet import Fernet

        cipher = Fernet(settings.encryption_key.encode())
        decrypted = cipher.decrypt(row.string_session.encode()).decode()
        client = TelegramClient(
            session=decrypted,
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
        )
        await client.connect()
        if not client.is_connected():
            raise RuntimeError("connect() returned without an active connection")
        await multi_telethon_manager.add(row.id, client, row.phone_number)
        row.is_connected = True
        await db.commit()
    except Exception as e:
        return HTMLResponse(f'<div class="alert alert-error">Reconnexion échouée : {e}</div>')

    return await list_accounts(request, db)


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
        return HTMLResponse('<span class="badge badge-neutral"><span class="status-dot status-dot-inactive"></span> Aucun compte</span>')

    if connected > 0:
        return HTMLResponse(f'<span class="badge badge-success"><span class="status-dot status-dot-active"></span> {connected}/{total} Connectés</span>')
    else:
        return HTMLResponse(f'<span class="badge badge-warning"><span class="status-dot status-dot-inactive"></span> 0/{total} Connectés</span>')
