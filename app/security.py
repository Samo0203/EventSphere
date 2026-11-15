import os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User

SECRET_KEY = os.getenv("SECRET_KEY", "local-dev-secret-change-before-deploy-please-123456789")
ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)

def create_token(user: User):
    payload = {"sub": str(user.id), "role": user.role,
               "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    error = HTTPException(status_code=401, detail="Invalid or expired login")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError, TypeError):
        raise error
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise error
    return user

def roles(*allowed):
    def checker(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Your account role cannot access this feature")
        return user
    return checker
