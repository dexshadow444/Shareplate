"""Authentication and role-based access control dependencies."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import NGOProfile, NgoStatus, Role, User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user_id = decode_token(token)
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require_roles(*roles: str):
    """Dependency factory: only users whose role is listed may call the endpoint."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role is not allowed to do this")
        return user

    return checker


def require_verified_ngo(user: User = Depends(require_roles(Role.NGO)), db: Session = Depends(get_db)) -> NGOProfile:
    profile = db.query(NGOProfile).filter(NGOProfile.user_id == user.id).one_or_none()
    if profile is None or profile.status != NgoStatus.VERIFIED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your organisation has not been verified by an administrator yet")
    return profile
