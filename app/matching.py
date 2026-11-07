"""Intelligent matching engine (pure Python, no framework or database imports).

Each (donation, NGO) pair is first checked against hard constraints. A pair that
fails any of them is ineligible and carries the reasons. Eligible pairs get a
weighted score in [0, 1] built from three factors:

  distance  - closer is better (linear falloff to 0 at MAX_RADIUS_KM)
  urgency   - less time left before the deadline is better, so food that is about
              to expire is surfaced first (linear over the last URGENCY_WINDOW_H hours)
  capacity  - how well the quantity fits the NGO's remaining capacity

Hard constraints:
  * within MAX_RADIUS_KM
  * quantity <= NGO's remaining capacity
  * NGO can physically arrive before the deadline (travel time + pickup buffer)
  * vegetarian-only NGOs only receive vegetarian food
  * no allergen overlap with the NGO's excluded allergens
"""
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from typing import Dict, FrozenSet, Iterable, List

EARTH_RADIUS_KM = 6371.0088
MAX_RADIUS_KM = 50.0
AVG_SPEED_KMH = 30.0          # conservative average road speed in Kerala
PICKUP_BUFFER_MIN = 30.0      # loading / handover time
URGENCY_WINDOW_H = 24.0

WEIGHTS: Dict[str, float] = {"distance": 0.40, "urgency": 0.35, "capacity": 0.25}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dphi = p2 - p1
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


@dataclass(frozen=True)
class DonationInfo:
    id: int
    quantity_kg: float
    hours_left: float
    latitude: float
    longitude: float
    is_veg: bool = True
    allergens: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class NgoInfo:
    id: int
    latitude: float
    longitude: float
    available_capacity_kg: float
    veg_only: bool = False
    excluded_allergens: FrozenSet[str] = frozenset()


@dataclass
class MatchResult:
    donation_id: int
    ngo_id: int
    eligible: bool
    score: float
    distance_km: float
    travel_minutes: float
    hours_left: float
    breakdown: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


def evaluate(d: DonationInfo, n: NgoInfo) -> MatchResult:
    dist = haversine_km(d.latitude, d.longitude, n.latitude, n.longitude)
    travel_min = dist / AVG_SPEED_KMH * 60.0
    reasons: List[str] = []

    if d.hours_left <= 0:
        reasons.append("donation has expired")
    if dist > MAX_RADIUS_KM:
        reasons.append(f"too far ({dist:.1f} km, limit {MAX_RADIUS_KM:.0f} km)")
    if d.quantity_kg > n.available_capacity_kg:
        reasons.append(
            f"quantity {d.quantity_kg:g} kg exceeds remaining capacity {n.available_capacity_kg:g} kg"
        )
    if d.hours_left > 0 and travel_min + PICKUP_BUFFER_MIN > d.hours_left * 60.0:
        reasons.append("cannot be collected before the deadline")
    if n.veg_only and not d.is_veg:
        reasons.append("non-vegetarian food, organisation accepts vegetarian only")
    overlap = {a.lower() for a in d.allergens} & {a.lower() for a in n.excluded_allergens}
    if overlap:
        reasons.append("contains excluded allergens: " + ", ".join(sorted(overlap)))

    distance_s = max(0.0, 1.0 - dist / MAX_RADIUS_KM)
    urgency_s = max(0.0, min(1.0, 1.0 - d.hours_left / URGENCY_WINDOW_H))
    cap = n.available_capacity_kg
    capacity_s = min(1.0, d.quantity_kg / cap) if cap > 0 else 0.0
    breakdown = {"distance": round(distance_s, 4), "urgency": round(urgency_s, 4), "capacity": round(capacity_s, 4)}
    score = sum(WEIGHTS[k] * breakdown[k] for k in WEIGHTS)

    return MatchResult(
        donation_id=d.id,
        ngo_id=n.id,
        eligible=not reasons,
        score=round(score, 4),
        distance_km=round(dist, 2),
        travel_minutes=round(travel_min, 1),
        hours_left=round(d.hours_left, 2),
        breakdown=breakdown,
        reasons=reasons,
    )


def rank_donations_for_ngo(donations: Iterable[DonationInfo], ngo: NgoInfo) -> List[MatchResult]:
    """Eligible donations for one NGO, best first (ties: sooner deadline, then nearer)."""
    results = [r for r in (evaluate(d, ngo) for d in donations) if r.eligible]
    results.sort(key=lambda r: (-r.score, r.hours_left, r.distance_km))
    return results
