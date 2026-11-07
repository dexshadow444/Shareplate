"""Shared helpers: audit trail, notifications, expiry sweeps, and DB-to-matching adapters."""
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .matching import DonationInfo, NgoInfo, evaluate
from .models import AuditLog, Donation, DonationStatus, NGOProfile, NgoStatus, Notification
from .timeutil import utcnow


def audit(db: Session, actor_id: Optional[int], action: str, entity: str, entity_id: Optional[int], **detail) -> None:
    """Adds an audit record to the current transaction; the caller commits."""
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id, detail=detail))


def notify(db: Session, user_id: int, message: str) -> None:
    db.add(Notification(user_id=user_id, message=message[:300]))


def expire_stale(db: Session) -> int:
    """Marks AVAILABLE/CLAIMED donations past their deadline as EXPIRED (recorded as a system action)."""
    now = utcnow()
    rows = db.scalars(
        select(Donation).where(
            Donation.status.in_([DonationStatus.AVAILABLE, DonationStatus.CLAIMED]), Donation.expires_at <= now
        )
    ).all()
    for d in rows:
        was = d.status
        d.status = DonationStatus.EXPIRED
        audit(db, None, "donation.expired", "donation", d.id, previous_status=was)
        notify(db, d.donor_id, f"Your donation '{d.title}' expired before it was collected.")
    if rows:
        db.commit()
    return len(rows)


def claimed_open_kg(db: Session, ngo_id: int) -> float:
    total = db.scalar(
        select(func.coalesce(func.sum(Donation.quantity_kg), 0.0)).where(
            Donation.claimed_by_ngo_id == ngo_id, Donation.status == DonationStatus.CLAIMED
        )
    )
    return float(total or 0.0)


def donation_info(d: Donation) -> DonationInfo:
    hours_left = (d.expires_at - utcnow()).total_seconds() / 3600
    return DonationInfo(
        id=d.id,
        quantity_kg=d.quantity_kg,
        hours_left=hours_left,
        latitude=d.latitude,
        longitude=d.longitude,
        is_veg=d.is_veg,
        allergens=frozenset(d.allergens or []),
    )


def ngo_info(db: Session, p: NGOProfile) -> NgoInfo:
    remaining = max(0.0, p.capacity_kg - claimed_open_kg(db, p.id))
    return NgoInfo(
        id=p.id,
        latitude=p.latitude,
        longitude=p.longitude,
        available_capacity_kg=remaining,
        veg_only=p.veg_only,
        excluded_allergens=frozenset(p.excluded_allergens or []),
    )


def notify_matching_ngos(db: Session, d: Donation) -> int:
    """Tells every verified NGO that could actually take this donation. Fine at prototype scale;
    for large volumes move this to a background worker."""
    info = donation_info(d)
    count = 0
    for p in db.scalars(select(NGOProfile).where(NGOProfile.status == NgoStatus.VERIFIED)).all():
        res = evaluate(info, ngo_info(db, p))
        if res.eligible:
            notify(db, p.user_id, f"New donation: {d.title} ({d.quantity_kg:g} kg, {res.distance_km:.1f} km away)")
            count += 1
    return count
