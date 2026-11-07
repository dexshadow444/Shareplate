"""End-to-end API tests (need the packages in requirements.txt):  pytest -q"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

_tmp = tempfile.mkdtemp()
os.environ["SHAREPLATE_DB"] = f"sqlite:///{_tmp}/test.db"
os.environ["SHAREPLATE_ADMIN_EMAIL"] = "admin@example.com"
os.environ["SHAREPLATE_ADMIN_PASSWORD"] = "Admin@12345"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, email, password):
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def iso(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def donation_body(**kw):
    body = dict(title="Veg meals", food_type="cooked_meal", quantity_kg=15, prepared_at=iso(-1), expires_at=iso(3),
                storage="hot_held", allergens=["Nuts"], is_veg=True, address="MG Road", district="Ernakulam",
                latitude=9.9816, longitude=76.2999)
    body.update(kw)
    return body


def register_ngo(client, email, **kw):
    ngo = dict(org_name="Test Trust", registration_no="KL/1/1", address="Edappally", district="Ernakulam",
               latitude=10.0261, longitude=76.3125, capacity_kg=100, veg_only=False, excluded_allergens=[])
    ngo.update(kw)
    r = client.post("/api/auth/register", json=dict(email=email, password="Password@1", full_name="NGO Admin", role="ngo", ngo=ngo))
    assert r.status_code == 201, r.text
    return r.json()


def test_full_flow(client):
    # donor registers
    r = client.post("/api/auth/register", json=dict(email="d@example.com", password="Password@1", full_name="Donor One", role="donor"))
    assert r.status_code == 201
    dh = login(client, "d@example.com", "Password@1")

    # NGO registers and is blocked until verified
    ngo_user = register_ngo(client, "n@example.com")
    nh = login(client, "n@example.com", "Password@1")
    assert client.get("/api/ngo/matches", headers=nh).status_code == 403

    # admin verifies
    ah = login(client, "admin@example.com", "Admin@12345")
    ngo_id = ngo_user["ngo_profile"]["id"]
    r = client.post(f"/api/admin/ngos/{ngo_id}/review", json={"decision": "verify"}, headers=ah)
    assert r.status_code == 200 and r.json()["status"] == "VERIFIED"

    # donor posts; NGO is notified and sees it ranked
    r = client.post("/api/donations", json=donation_body(), headers=dh)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert any("New donation" in n["message"] for n in client.get("/api/notifications", headers=nh).json())
    matches = client.get("/api/ngo/matches", headers=nh).json()
    assert [m["donation"]["id"] for m in matches] == [did]

    # claim, then a second claim conflicts
    assert client.post(f"/api/ngo/donations/{did}/claim", headers=nh).status_code == 200
    assert client.post(f"/api/ngo/donations/{did}/claim", headers=nh).status_code == 409

    # collect
    r = client.post(f"/api/ngo/donations/{did}/collect", headers=nh)
    assert r.status_code == 200 and r.json()["status"] == "COLLECTED"

    # audit trail has the whole story
    actions = {a["action"] for a in client.get("/api/admin/audit", headers=ah).json()}
    assert {"donation.created", "donation.claimed", "donation.collected", "ngo.verify"} <= actions
    assert client.get("/api/impact").json()["kg_rescued"] >= 15


def test_rbac(client):
    dh = login(client, "d@example.com", "Password@1")
    nh = login(client, "n@example.com", "Password@1")
    assert client.get("/api/admin/stats", headers=dh).status_code == 403
    assert client.post("/api/donations", json=donation_body(), headers=nh).status_code == 403
    assert client.get("/api/donations/mine").status_code == 401


def test_food_safety_and_validation(client):
    dh = login(client, "d@example.com", "Password@1")
    r = client.post("/api/donations", json=donation_body(storage="room_temp", expires_at=iso(8)), headers=dh)
    assert r.status_code == 422
    r = client.post("/api/donations", json=donation_body(latitude=28.6, longitude=77.2), headers=dh)  # Delhi
    assert r.status_code == 422


def test_cannot_self_register_as_admin(client):
    r = client.post("/api/auth/register", json=dict(email="x@example.com", password="Password@1", full_name="Evil", role="admin"))
    assert r.status_code == 422


def test_ineligible_claim_is_refused(client):
    dh = login(client, "d@example.com", "Password@1")
    register_ngo(client, "veg@example.com", org_name="Veg Only", veg_only=True)
    ah = login(client, "admin@example.com", "Admin@12345")
    pid = [n for n in client.get("/api/admin/ngos", headers=ah).json() if n["org_name"] == "Veg Only"][0]["id"]
    client.post(f"/api/admin/ngos/{pid}/review", json={"decision": "verify"}, headers=ah)
    vh = login(client, "veg@example.com", "Password@1")
    did = client.post("/api/donations", json=donation_body(is_veg=False, title="Chicken"), headers=dh).json()["id"]
    assert client.post(f"/api/ngo/donations/{did}/claim", headers=vh).status_code == 422
