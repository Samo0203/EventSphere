from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import RegisterIn, UserOut
from app.security import create_token_pair, current_user, hash_password, roles, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "Email already registered")
    u = User(full_name=data.full_name.strip(), email=email, hashed_password=hash_password(data.password), role="attendee")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email=form.username.lower()).first()
    if not u or not verify_password(form.password, u.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    if not u.is_active:
        raise HTTPException(403, "Account inactive")
    token, csrf = create_token_pair(u)
    return {"access_token": token, "token_type": "bearer", "csrf_token": csrf,
            "user": {"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role}}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.get("/admin/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(roles("admin"))):
    return db.query(User).order_by(User.id).all()


@router.post("/admin/users/{user_id}/role")
def set_role(user_id: int, role: str, db: Session = Depends(get_db), admin: User = Depends(roles("admin"))):
    if role not in ("admin", "staff", "attendee"):
        raise HTTPException(400, "Role must be admin, staff or attendee")
    u = db.query(User).filter_by(id=user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    u.role = role
    db.commit()
    return {"id": u.id, "role": u.role}
