from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select, text
from telethon import TelegramClient

from app.config import settings
from app.db.engine import engine, async_session
from app.db.models import Base, MTProtoSession
from app.routes import auth, config, groups, mtproto, relay
from app.routes.auth import get_admin_user
from app.telegram.client import multi_telethon_manager

_jinja_env = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)


def render(name: str, **context) -> HTMLResponse:
    tmpl = _jinja_env.get_template(name)
    return HTMLResponse(tmpl.render(**context))


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migrations for new columns
        for table, col, dtype in [
            ("mtproto_session", "label", "VARCHAR(64)"),
            ("mtproto_session", "created_at", "TIMESTAMPTZ DEFAULT NOW()"),
            ("source_groups", "session_id", "INTEGER REFERENCES mtproto_session(id) DEFAULT 1"),
        ]:
            r = await conn.execute(
                text("SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c"),
                {"t": table, "c": col},
            )
            if not r.scalar():
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}"))
                if col == "session_id":
                    await conn.execute(text("ALTER TABLE source_groups ALTER COLUMN session_id DROP DEFAULT"))

    async with async_session() as db:
        r = await db.execute(select(MTProtoSession).where(MTProtoSession.is_connected == True))
        rows = r.scalars().all()

        for row in rows:
            from cryptography.fernet import Fernet

            try:
                cipher = Fernet(settings.encryption_key.encode())
                decrypted = cipher.decrypt(row.string_session.encode()).decode()
                client = TelegramClient(
                    session=decrypted,
                    api_id=settings.telegram_api_id,
                    api_hash=settings.telegram_api_hash,
                )
                await client.connect()
                await multi_telethon_manager.add(row.id, client, row.phone_number)
            except Exception:
                row.is_connected = False
                await db.commit()

    yield

    await multi_telethon_manager.disconnect_all()
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(mtproto.router)
app.include_router(groups.router)
app.include_router(relay.router)
app.include_router(config.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/login")
async def login_page(request: Request, error: str = ""):
    user = get_admin_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return render("login.html", request=request, error=bool(error))


@app.get("/dashboard")
async def dashboard(request: Request):
    user = get_admin_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return render("dashboard.html", request=request)
