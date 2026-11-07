from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_roles
from ..models import AuditLog, Donation, DonationStatus, NGOProfile, NgoStatus, Role, User
from ..schemas import ActiveIn, AuditOut, DonationOut, NgoProfileOut, ReviewIn, UserOut
from ..services import audit, expire_stale, notify
from ..timeutil import utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_roles(Role.ADMIN))])


@router.get("/ngos", response_model=List[NgoProfileOut])
def list_ngos(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = select(NGOProfile).order_by(NGOProfile.created_at.desc())
    if status:
        q = q.where(NGOProfile.status == status.upper())
    return db.scalars(q).all()


@router.post("/ngos/{ngo_id}/review", response_model=NgoProfileOut)
def review_ngo(ngo_id: int, payload: ReviewIn, admin: User = Depends(require_roles(Role.ADMIN)),
               db: Session = Depends(get_db)):
    p = db.get(NGOProfile, ngo_id)
    if p is None:
        raise HTTPException(404, "Organisation not found")
    p.status = NgoStatus.VERIFIED if payload.decision == "verify" else NgoStatus.REJECTED
    p.review_note = payload.note
    p.reviewed_at = utcnow()
    audit(db, admin.id, f"ngo.{payload.decision}", "ngo", p.id, org_name=p.org_name, note=payload.note)
    notify(db, p.user_id, f"Your organisation was {p.status.lower()}." + (f" Note: {payload.note}" if payload.note else ""))
    db.commit()
    db.refresh(p)
    return p


@router.get("/donations", response_model=List[DonationOut])
def list_donations(status: Optional[str] = None, limit: int = Query(default=100, ge=1, le=500),
                   db: Session = Depends(get_db)):
    expire_stale(db)
    q = select(Donation).order_by(Donation.created_at.desc()).limit(limit)
    if status:
        q = q.where(Donation.status == status.upper())
    return db.scalars(q).all()


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.created_at.desc())).all()


@router.post("/users/{user_id}/active", response_model=UserOut)
def set_active(user_id: int, payload: ActiveIn, admin: User = Depends(require_roles(Role.ADMIN)),
               db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(409, "You cannot deactivate your own account")
    u.is_active = payload.is_active
    audit(db, admin.id, "user.activated" if payload.is_active else "user.deactivated", "user", u.id)
    db.commit()
    db.refresh(u)
    return u


@router.get("/audit", response_model=List[AuditOut])
def audit_log(entity: Optional[str] = None, action: Optional[str] = None,
              limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if entity:
        q = q.where(AuditLog.entity == entity)
    if action:
        q = q.where(AuditLog.action == action)
    return db.scalars(q).all()


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    expire_stale(db)
    by_status = dict(db.execute(select(Donation.status, func.count()).group_by(Donation.status)).all())
    kg_collected = db.scalar(select(func.coalesce(func.sum(Donation.quantity_kg), 0.0))
                             .where(Donation.status == DonationStatus.COLLECTED))
    kg_expired = db.scalar(select(func.coalesce(func.sum(Donation.quantity_kg), 0.0))
                           .where(Donation.status == DonationStatus.EXPIRED))
    ngos = dict(db.execute(select(NGOProfile.status, func.count()).group_by(NGOProfile.status)).all())
    users = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    return {
        "donations_by_status": by_status,
        "kg_collected": round(float(kg_collected), 2),
        "kg_expired_uncollected": round(float(kg_expired), 2),
        "est_meals_served": int(kg_collected / settings.KG_PER_MEAL),
        "ngos_by_status": ngos,
        "users_by_role": users,
    }
