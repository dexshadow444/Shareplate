from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import food_safety
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import Donation, DonationStatus, NGOProfile, Role, User
from ..schemas import DonationCreate, DonationOut
from ..services import audit, expire_stale, notify, notify_matching_ngos
from ..timeutil import utcnow

router = APIRouter(prefix="/api/donations", tags=["donations"])


@router.get("/options")
def options():
    """Allowed values for the food type and storage dropdowns."""
    return {"food_types": food_safety.FOOD_TYPES, "storage_types": food_safety.STORAGE_TYPES}


@router.post("", response_model=DonationOut, status_code=status.HTTP_201_CREATED)
def create_donation(payload: DonationCreate, user: User = Depends(require_roles(Role.DONOR)),
                    db: Session = Depends(get_db)):
    errors = food_safety.validate(payload.food_type, payload.storage, payload.prepared_at, payload.expires_at, utcnow())
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, errors)

    donation = Donation(donor_id=user.id, **payload.model_dump())
    db.add(donation)
    db.flush()
    audit(db, user.id, "donation.created", "donation", donation.id,
          quantity_kg=donation.quantity_kg, food_type=donation.food_type)
    notify_matching_ngos(db, donation)
    db.commit()
    db.refresh(donation)
    return donation


@router.get("/mine", response_model=List[DonationOut])
def my_donations(status_filter: Optional[str] = Query(default=None, alias="status"),
                 user: User = Depends(require_roles(Role.DONOR)), db: Session = Depends(get_db)):
    expire_stale(db)
    q = select(Donation).where(Donation.donor_id == user.id).order_by(Donation.created_at.desc())
    if status_filter:
        q = q.where(Donation.status == status_filter.upper())
    return db.scalars(q).all()


@router.get("/{donation_id}", response_model=DonationOut)
def get_donation(donation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = db.get(Donation, donation_id)
    if d is None:
        raise HTTPException(404, "Donation not found")
    allowed = user.role == Role.ADMIN or d.donor_id == user.id
    if not allowed and user.role == Role.NGO:
        profile = db.scalar(select(NGOProfile).where(NGOProfile.user_id == user.id))
        allowed = bool(profile) and d.claimed_by_ngo_id == profile.id
    if not allowed:
        raise HTTPException(403, "You do not have access to this donation")
    return d


@router.post("/{donation_id}/cancel", response_model=DonationOut)
def cancel_donation(donation_id: int, user: User = Depends(require_roles(Role.DONOR)), db: Session = Depends(get_db)):
    d = db.get(Donation, donation_id)
    if d is None or d.donor_id != user.id:
        raise HTTPException(404, "Donation not found")
    if d.status not in (DonationStatus.AVAILABLE, DonationStatus.CLAIMED):
        raise HTTPException(409, f"A {d.status.lower()} donation cannot be cancelled")
    if d.status == DonationStatus.CLAIMED and d.claimed_by:
        notify(db, d.claimed_by.user_id, f"The donation '{d.title}' you claimed was cancelled by the donor.")
    previous = d.status
    d.status = DonationStatus.CANCELLED
    audit(db, user.id, "donation.cancelled", "donation", d.id, previous_status=previous)
    db.commit()
    db.refresh(d)
    return d
