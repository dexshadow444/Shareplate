from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_roles, require_verified_ngo
from ..matching import evaluate, rank_donations_for_ngo
from ..models import Donation, DonationStatus, NGOProfile, Role, User
from ..schemas import DonationOut, MatchOut, NgoPrefsIn, NgoProfileOut
from ..services import audit, claimed_open_kg, donation_info, expire_stale, ngo_info, notify
from ..timeutil import utcnow

router = APIRouter(prefix="/api/ngo", tags=["ngo"])


@router.get("/profile", response_model=NgoProfileOut)
def get_profile(user: User = Depends(require_roles(Role.NGO)), db: Session = Depends(get_db)):
    return db.scalar(select(NGOProfile).where(NGOProfile.user_id == user.id))


@router.put("/profile", response_model=NgoProfileOut)
def update_prefs(payload: NgoPrefsIn, user: User = Depends(require_roles(Role.NGO)), db: Session = Depends(get_db)):
    p = db.scalar(select(NGOProfile).where(NGOProfile.user_id == user.id))
    changes = payload.model_dump(exclude_none=True)
    if "excluded_allergens" in changes:
        changes["excluded_allergens"] = sorted({a.strip().lower() for a in changes["excluded_allergens"] if a.strip()})
    for k, v in changes.items():
        setattr(p, k, v)
    audit(db, user.id, "ngo.prefs_updated", "ngo", p.id, **{k: v for k, v in changes.items()})
    db.commit()
    db.refresh(p)
    return p


@router.get("/capacity")
def capacity(ngo: NGOProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    used = claimed_open_kg(db, ngo.id)
    return {"capacity_kg": ngo.capacity_kg, "claimed_kg": used, "remaining_kg": max(0.0, ngo.capacity_kg - used)}


@router.get("/matches", response_model=List[MatchOut])
def matches(limit: int = Query(default=20, ge=1, le=100), ngo: NGOProfile = Depends(require_verified_ngo),
            db: Session = Depends(get_db)):
    """Available donations this NGO can actually take, best match first."""
    expire_stale(db)
    available = db.scalars(select(Donation).where(Donation.status == DonationStatus.AVAILABLE)).all()
    by_id = {d.id: d for d in available}
    ranked = rank_donations_for_ngo([donation_info(d) for d in available], ngo_info(db, ngo))[:limit]
    return [
        MatchOut(donation=by_id[r.donation_id], score=r.score, distance_km=r.distance_km,
                 travel_minutes=r.travel_minutes, hours_left=r.hours_left, breakdown=r.breakdown)
        for r in ranked
    ]


@router.get("/claims", response_model=List[DonationOut])
def my_claims(ngo: NGOProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    expire_stale(db)
    return db.scalars(
        select(Donation).where(Donation.claimed_by_ngo_id == ngo.id).order_by(Donation.claimed_at.desc())
    ).all()


def _own_claimed(db: Session, donation_id: int, ngo: NGOProfile) -> Donation:
    d = db.get(Donation, donation_id)
    if d is None or d.claimed_by_ngo_id != ngo.id:
        raise HTTPException(404, "Claim not found")
    return d


@router.post("/donations/{donation_id}/claim", response_model=DonationOut)
def claim(donation_id: int, ngo: NGOProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    expire_stale(db)
    d = db.get(Donation, donation_id)
    if d is None:
        raise HTTPException(404, "Donation not found")
    if d.status != DonationStatus.AVAILABLE:
        raise HTTPException(409, f"This donation is {d.status.lower()} and can no longer be claimed")

    result = evaluate(donation_info(d), ngo_info(db, ngo))
    if not result.eligible:
        raise HTTPException(422, result.reasons)

    # Atomic compare-and-set: if two NGOs race, only one UPDATE matches status == AVAILABLE.
    upd = db.execute(
        update(Donation)
        .where(Donation.id == donation_id, Donation.status == DonationStatus.AVAILABLE)
        .values(status=DonationStatus.CLAIMED, claimed_by_ngo_id=ngo.id, claimed_at=utcnow())
    )
    if upd.rowcount == 0:
        db.rollback()
        raise HTTPException(409, "Another organisation claimed this donation first")
    audit(db, ngo.user_id, "donation.claimed", "donation", d.id, ngo_id=ngo.id, score=result.score)
    notify(db, d.donor_id, f"{ngo.org_name} will collect your donation '{d.title}'.")
    db.commit()
    db.refresh(d)
    return d


@router.post("/donations/{donation_id}/collect", response_model=DonationOut)
def collect(donation_id: int, ngo: NGOProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    d = _own_claimed(db, donation_id, ngo)
    if d.status != DonationStatus.CLAIMED:
        raise HTTPException(409, f"A {d.status.lower()} donation cannot be marked collected")
    d.status = DonationStatus.COLLECTED
    d.collected_at = utcnow()
    audit(db, ngo.user_id, "donation.collected", "donation", d.id, ngo_id=ngo.id, quantity_kg=d.quantity_kg)
    notify(db, d.donor_id, f"Your donation '{d.title}' was collected by {ngo.org_name}. Thank you!")
    db.commit()
    db.refresh(d)
    return d


@router.post("/donations/{donation_id}/release", response_model=DonationOut)
def release(donation_id: int, ngo: NGOProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    """Give a claim back so another organisation can take it."""
    d = _own_claimed(db, donation_id, ngo)
    if d.status != DonationStatus.CLAIMED:
        raise HTTPException(409, f"A {d.status.lower()} donation cannot be released")
    d.status = DonationStatus.AVAILABLE
    d.claimed_by_ngo_id = None
    d.claimed_at = None
    audit(db, ngo.user_id, "donation.released", "donation", d.id, ngo_id=ngo.id)
    notify(db, d.donor_id, f"{ngo.org_name} could not collect '{d.title}'; it is available again.")
    db.commit()
    db.refresh(d)
    return d
