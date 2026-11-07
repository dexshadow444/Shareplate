"""Notifications (per user) and the public impact counter."""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Donation, DonationStatus, NGOProfile, NgoStatus, Notification, User
from ..schemas import NotificationOut

router = APIRouter(tags=["misc"])


@router.get("/api/notifications", response_model=List[NotificationOut])
def my_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(50)
    ).all()


@router.post("/api/notifications/read-all")
def mark_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
               .values(is_read=True))
    db.commit()
    return {"ok": True}


@router.get("/api/impact")
def impact(db: Session = Depends(get_db)):
    """Public, anonymous totals for the landing page."""
    kg = float(db.scalar(select(func.coalesce(func.sum(Donation.quantity_kg), 0.0))
                         .where(Donation.status == DonationStatus.COLLECTED)))
    n = db.scalar(select(func.count()).select_from(Donation).where(Donation.status == DonationStatus.COLLECTED))
    ngos = db.scalar(select(func.count()).select_from(NGOProfile).where(NGOProfile.status == NgoStatus.VERIFIED))
    return {"kg_rescued": round(kg, 1), "donations_collected": n, "verified_organisations": ngos,
            "est_meals": int(kg / settings.KG_PER_MEAL)}


@router.get("/api/health")
def health():
    return {"status": "ok"}
