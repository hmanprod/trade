from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer

from app.config import settings

router = APIRouter()

SESSION_COOKIE = "trade_session"
serializer = URLSafeTimedSerializer(settings.session_secret, salt="admin-auth")


@router.post("/login")
async def login(response: Response, username: str = Form(...), password: str = Form(...)):
    if username != settings.admin_username or password != settings.admin_password:
        return RedirectResponse(url="/login?error=1", status_code=303)
    token = serializer.dumps("admin")
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400 * 7,
    )
    return response


@router.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


def get_admin_user(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return serializer.loads(token, max_age=86400 * 7)
    except Exception:
        return None
