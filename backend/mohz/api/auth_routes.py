from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth import (check_password_rules, client_ip, end_session, enforce_limit, hash_password, record_attempt,
                    session_from_request, start_session, verify_password)
from ..db import get_db
from ..models import User, default_plan
from .me import me_doc

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Register(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(max_length=200)


class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


@router.post("/register")
def register(body: Register, request: Request, response: Response, db=Depends(get_db)):
    ip = client_ip(request)
    enforce_limit(db, "register", ip)
    check_password_rules(body.password)
    email = body.email.strip().lower()
    record_attempt(db, "register", ip, email, ok=True)
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists. Log in instead.")
    plan = default_plan(db)
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password),
                plan_id=plan.id if plan else None)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists. Log in instead.")
    start_session(db, user, request, response)
    return {"user": me_doc(user)}


@router.post("/login")
def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    ip = client_ip(request)
    email = body.email.strip().lower()
    enforce_limit(db, "login", ip, email)
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(user.password_hash if user else None, body.password)
    record_attempt(db, "login", ip, email, ok=ok and user is not None)
    if not ok or user is None:
        raise HTTPException(401, "Wrong email or password.")
    start_session(db, user, request, response)
    return {"user": me_doc(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    end_session(db, request, response)
    return {"ok": True}


@router.get("/session")
def current(request: Request, db=Depends(get_db)):
    """Who is logged in (null when nobody). Never 401, so the page can decide what to show."""
    sess = session_from_request(db, request)
    user = db.get(User, sess.user_id) if sess else None
    return {"user": me_doc(user) if user else None}
