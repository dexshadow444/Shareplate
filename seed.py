"""Loads demo data so you can try every role immediately:  python seed.py

Creates (all passwords: Demo@1234):
  donor1@example.com   - a restaurant in Kochi
  ngo1@example.com     - verified NGO in Kochi (veg + all food)
  ngo2@example.com     - verified NGO in Thrissur (vegetarian only)
  ngo3@example.com     - NGO still pending verification
  admin: SHAREPLATE_ADMIN_EMAIL / SHAREPLATE_ADMIN_PASSWORD (default admin@example.com / ChangeMe@123)
"""
from datetime import timedelta

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.main import bootstrap_admin
from app.models import Donation, NGOProfile, NgoStatus, Role, User
from app.security import hash_password
from app.timeutil import utcnow

PW = "Demo@1234"


def user(db, email, name, role):
    u = db.scalar(select(User).where(User.email == email))
    if not u:
        u = User(email=email, full_name=name, role=role, hashed_password=hash_password(PW))
        db.add(u)
        db.flush()
    return u


def ngo(db, u, **kw):
    if not db.scalar(select(NGOProfile).where(NGOProfile.user_id == u.id)):
        db.add(NGOProfile(user_id=u.id, **kw))


def main():
    Base.metadata.create_all(engine)
    bootstrap_admin()
    with SessionLocal() as db:
        d1 = user(db, "donor1@example.com", "Malabar Kitchen", Role.DONOR)
        n1, n2, n3 = (user(db, f"ngo{i}@example.com", n, Role.NGO) for i, n in
                      [(1, "Anna Daanam Trust"), (2, "Thrissur Care Foundation"), (3, "Pending Hope Society")])
        ngo(db, n1, org_name="Anna Daanam Trust", registration_no="KL/2015/001", address="Edappally, Kochi",
            district="Ernakulam", latitude=10.0261, longitude=76.3125, capacity_kg=120, status=NgoStatus.VERIFIED)
        ngo(db, n2, org_name="Thrissur Care Foundation", registration_no="KL/2018/044", address="Round South, Thrissur",
            district="Thrissur", latitude=10.5276, longitude=76.2144, capacity_kg=80, veg_only=True,
            status=NgoStatus.VERIFIED)
        ngo(db, n3, org_name="Pending Hope Society", registration_no="KL/2024/310", address="Kakkanad, Kochi",
            district="Ernakulam", latitude=10.0159, longitude=76.3419, capacity_kg=50, status=NgoStatus.PENDING)
        db.flush()
        if not db.scalar(select(Donation)):
            now = utcnow()
            for title, kg, veg, hrs, lat, lng, addr in [
                ("Veg biryani, 40 portions", 16, True, 3, 9.9816, 76.2999, "MG Road, Kochi"),
                ("Chicken curry & rice", 22, False, 2.5, 9.9312, 76.2673, "Fort Kochi"),
                ("Bread and buns", 9, True, 20, 10.0, 76.31, "Vyttila, Kochi"),
            ]:
                db.add(Donation(donor_id=d1.id, title=title, food_type="cooked_meal" if hrs < 10 else "bakery",
                                quantity_kg=kg, prepared_at=now - timedelta(hours=1), expires_at=now + timedelta(hours=hrs),
                                storage="hot_held" if hrs < 10 else "room_temp", allergens=[], is_veg=veg,
                                address=addr, district="Ernakulam", latitude=lat, longitude=lng))
        db.commit()
    print("Seeded. Demo password for donor1/ngo1/ngo2/ngo3 @example.com:", PW)


if __name__ == "__main__":
    main()
