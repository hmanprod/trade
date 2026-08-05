from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import RelayConfig
from app.routes.auth import get_admin_user

router = APIRouter(prefix="/api/config")


def _guard(request: Request):
    if not get_admin_user(request):
        return HTMLResponse("Unauthorized", status_code=401)


@router.post("/filters")
async def save_filters(
    request: Request,
    keywords: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    if config:
        config.filter_keywords = keywords or None
    else:
        db.add(RelayConfig(filter_keywords=keywords or None))
    await db.commit()
    return HTMLResponse('<div class="alert alert-success text-xs py-2">Mots-clés de filtrage enregistrés.</div>')


@router.get("/filters")
async def get_filters(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    guard = _guard(request)
    if guard:
        return guard

    r = await db.execute(select(RelayConfig).limit(1))
    config = r.scalar_one_or_none()
    return JSONResponse({"keywords": config.filter_keywords if config else None})
