from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select

from app.config import settings
from app.db.engine import engine, async_session
from app.db.models import Base, MTProtoSession
from app.routes import auth, config, groups, mtproto, relay
from app.routes.auth import get_admin_user
from app.telegram.client import telethon_manager

_jinja_env = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)


def render(name: str, **context) -> HTMLResponse:
    tmpl = _jinja_env.get_template(name)
    return HTMLResponse(tmpl.render(**context))


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        r = await db.execute(select(MTProtoSession).limit(1))
        session_row = r.scalar_one_or_none()
        if session_row and session_row.string_session:
            from cryptography.fernet import Fernet

            try:
                cipher = Fernet(settings.encryption_key.encode())
                decrypted = cipher.decrypt(session_row.string_session.encode()).decode()
                await telethon_manager.restore(decrypted)
                session_row.is_connected = True
                await db.commit()
            except Exception:
                session_row.is_connected = False
                await db.commit()

    yield

    await telethon_manager.disconnect()
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
