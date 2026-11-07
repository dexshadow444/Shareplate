from datetime import datetime
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator, model_validator

from .config import settings
from .timeutil import to_iso_z, to_naive_utc

# datetime that is stored as naive UTC and returned as ISO-8601 with a trailing Z
UTCDateTime = Annotated[datetime, PlainSerializer(to_iso_z, return_type=str, when_used="json")]


def _check_kerala(lat: float, lng: float) -> None:
    if not (settings.LAT_MIN <= lat <= settings.LAT_MAX and settings.LNG_MIN <= lng <= settings.LNG_MAX):
        raise ValueError("location must be inside Kerala")


def _clean_list(values: List[str]) -> List[str]:
    return sorted({v.strip().lower() for v in values if v and v.strip()})


# ---------- auth ----------
class NgoRegisterIn(BaseModel):
    org_name: str = Field(min_length=2, max_length=160)
    registration_no: str = Field(min_length=3, max_length=80)
    address: str = Field(min_length=3, max_length=300)
    district: str = Field(min_length=2, max_length=60)
    latitude: float
    longitude: float
    capacity_kg: float = Field(gt=0, le=100000)
    veg_only: bool = False
    excluded_allergens: List[str] = []

    @model_validator(mode="after")
    def _check(self):
        _check_kerala(self.latitude, self.longitude)
        self.excluded_allergens = _clean_list(self.excluded_allergens)
        return self


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=30)
    role: Literal["donor", "ngo"]
    ngo: Optional[NgoRegisterIn] = None

    @model_validator(mode="after")
    def _ngo_required(self):
        if self.role == "ngo" and self.ngo is None:
            raise ValueError("ngo details are required when role is 'ngo'")
        return self


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class NgoProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    org_name: str
    registration_no: str
    address: str
    district: str
    latitude: float
    longitude: float
    capacity_kg: float
    veg_only: bool
    excluded_allergens: List[str]
    status: str
    review_note: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str  # plain str on output: stored addresses were already validated at registration
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    ngo_profile: Optional[NgoProfileOut] = None


class NgoPrefsIn(BaseModel):
    capacity_kg: Optional[float] = Field(default=None, gt=0, le=100000)
    veg_only: Optional[bool] = None
    excluded_allergens: Optional[List[str]] = None


# ---------- donations ----------
class DonationCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    food_type: str
    quantity_kg: float = Field(gt=0, le=5000)
    prepared_at: datetime
    expires_at: datetime
    storage: str
    allergens: List[str] = []
    is_veg: bool = True
    address: str = Field(min_length=3, max_length=300)
    district: str = Field(min_length=2, max_length=60)
    latitude: float
    longitude: float
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("prepared_at", "expires_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return to_naive_utc(v)

    @model_validator(mode="after")
    def _check(self):
        _check_kerala(self.latitude, self.longitude)
        self.allergens = _clean_list(self.allergens)
        return self


class DonationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    donor_id: int
    title: str
    food_type: str
    quantity_kg: float
    prepared_at: UTCDateTime
    expires_at: UTCDateTime
    storage: str
    allergens: List[str]
    is_veg: bool
    address: str
    district: str
    latitude: float
    longitude: float
    notes: Optional[str] = None
    status: str
    claimed_by_ngo_id: Optional[int] = None
    claimed_at: Optional[UTCDateTime] = None
    collected_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime


class MatchOut(BaseModel):
    donation: DonationOut
    score: float
    distance_km: float
    travel_minutes: float
    hours_left: float
    breakdown: Dict[str, float]


# ---------- admin ----------
class ReviewIn(BaseModel):
    decision: Literal["verify", "reject"]
    note: Optional[str] = Field(default=None, max_length=500)


class ActiveIn(BaseModel):
    is_active: bool


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: Optional[int]
    action: str
    entity: str
    entity_id: Optional[int]
    detail: dict
    created_at: UTCDateTime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    message: str
    is_read: bool
    created_at: UTCDateTime
