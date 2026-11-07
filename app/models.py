from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .timeutil import utcnow


class Role:
    DONOR = "donor"
    NGO = "ngo"
    ADMIN = "admin"


class DonationStatus:
    AVAILABLE = "AVAILABLE"
    CLAIMED = "CLAIMED"
    COLLECTED = "COLLECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class NgoStatus:
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    ngo_profile: Mapped[Optional["NGOProfile"]] = relationship(back_populates="user", uselist=False)


class NGOProfile(Base):
    __tablename__ = "ngo_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    org_name: Mapped[str] = mapped_column(String(160))
    registration_no: Mapped[str] = mapped_column(String(80))
    address: Mapped[str] = mapped_column(String(300))
    district: Mapped[str] = mapped_column(String(60))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    capacity_kg: Mapped[float] = mapped_column(Float)            # max kg held at once
    veg_only: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_allergens: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default=NgoStatus.PENDING, index=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="ngo_profile")


class Donation(Base):
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    food_type: Mapped[str] = mapped_column(String(30))
    quantity_kg: Mapped[float] = mapped_column(Float)
    prepared_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    storage: Mapped[str] = mapped_column(String(20))
    allergens: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True)
    address: Mapped[str] = mapped_column(String(300))
    district: Mapped[str] = mapped_column(String(60))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=DonationStatus.AVAILABLE, index=True)
    claimed_by_ngo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ngo_profiles.id"), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    donor: Mapped[User] = relationship()
    claimed_by: Mapped[Optional[NGOProfile]] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)  # None = system
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(String(300))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
