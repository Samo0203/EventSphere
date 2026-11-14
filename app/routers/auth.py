
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse
from app.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


# USER REGISTRATION
@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):

    existing_user = db.query(User).filter(
        User.email == user_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )

    new_user = User(
        full_name=user_data.full_name,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        role="attendee"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# USER LOGIN

@router.post("/login")
def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
   

    user = db.query(User).filter(
        User.email == form_data.username
    ).first()


    if user:
        password_ok = verify_password(
            form_data.password,
            user.hashed_password
        )
        
        if not password_ok:
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="User account is inactive"
            )

        access_token = create_access_token(
            data={"sub": user.email, "role": user.role}
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role
            }
        }

    raise HTTPException(
        status_code=401,
        detail="User not found"
    )
