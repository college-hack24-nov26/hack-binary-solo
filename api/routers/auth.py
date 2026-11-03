from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ocr import auth as ocr_auth
from ocr.config import load_settings

from ..deps import COOKIE, User, authenticator, current_user, https_on
from ..schemas import LoginIn, Me
from ..views import doctor_for

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _me(u: User) -> dict:
    d = doctor_for(u.username) if u.role == "doctor" else None
    return {"username": u.username, "role": u.role, "doctorId": d.id if d else None}


@router.post("/login", response_model=Me)
def login(body: LoginIn, request: Request, response: Response, a: ocr_auth.Authenticator = Depends(authenticator)):
    if not ocr_auth.has_users(load_settings().users_file):
        raise HTTPException(409, "No users exist yet. Create one: .venv/bin/python scripts/create_user.py <username> <doctor|staff>")
    user, msg = a.login(body.username, body.password)
    if not user:
        raise HTTPException(401, msg)
    sid = request.app.state.sessions.create(user["username"], user["role"])
    response.set_cookie(COOKIE, sid, httponly=True, samesite="strict", secure=https_on(), path="/")
    return _me(User(user["username"], user["role"], 0))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, _: User = Depends(current_user)):
    request.app.state.sessions.drop(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=Me)
def me(u: User = Depends(current_user)):
    return _me(u)
