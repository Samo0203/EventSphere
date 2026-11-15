import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User

SECRET_KEY = os.getenv("SECRET_KEY", "local-dev-secret-change-before-deploy-please-123456789")
ALGORITHM = "HS256"
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_token(user: User, csrf: Optional[str] = None) -> str:
    """JWT carrying a per-login CSRF secret. State-changing requests must echo it in X-CSRF-Token."""
    payload = {"sub": str(user.id), "role": user.role, "csrf": csrf or secrets.token_urlsafe(16),
               "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_token_pair(user: User):
    csrf = secrets.token_urlsafe(16)
    return create_token(user, csrf), csrf


def _decode(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def _load_user(token: str, db: Session):
    payload = _decode(token)
    user_id = int(payload.get("sub", "0"))
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
    return user, payload


def current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    error = HTTPException(status_code=401, detail="Invalid or expired login")
    try:
        user, payload = _load_user(token, db)
    except (JWTError, ValueError, TypeError):
        raise error
    if not user:
        raise error
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("X-CSRF-Token", "")
        if not sent or not hmac.compare_digest(sent, str(payload.get("csrf", ""))):
            raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
    return user


def optional_user(token: Optional[str] = Depends(oauth2_optional), db: Session = Depends(get_db)):
    """Used by public GET endpoints that show extra data to admins."""
    if not token:
        return None
    try:
        user, _ = _load_user(token, db)
        return user
    except (JWTError, ValueError, TypeError):
        return None


def roles(*allowed):
    def checker(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Your account role cannot access this feature")
        return user
    return checker
