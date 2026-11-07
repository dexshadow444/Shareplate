from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import NGOProfile, NgoStatus, Role, User
from ..schemas import RegisterIn, TokenOut, UserOut
from ..security import create_token, hash_password, verify_password
from ..services import audit, notify

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == Role.NGO:
        db.add(NGOProfile(user_id=user.id, status=NgoStatus.PENDING, **payload.ngo.model_dump()))
        for admin in db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True))).all():
            notify(db, admin.id, f"New organisation awaiting verification: {payload.ngo.org_name}")

    audit(db, user.id, "user.registered", "user", user.id, role=payload.role)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    audit(db, user.id, "user.login", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_token(user.id, user.role), role=user.role)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
