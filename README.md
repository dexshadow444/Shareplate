# SharePlate - Intelligent Surplus Food Redistribution (Kerala)

Connects food donors with **verified NGOs**, ranks every donation for each NGO with a matching algorithm
(distance, deadline urgency, remaining capacity), and keeps a full audit trail.

**Stack:** Python, FastAPI, SQLAlchemy 2, SQLite (dev) / PostgreSQL (production), JWT auth, vanilla JS + Leaflet/OpenStreetMap frontend.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py                                          # optional demo data
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 (app) and http://127.0.0.1:8000/docs (interactive API docs).

Demo logins after `python seed.py` (password `Demo@1234`): `donor1@example.com`, `ngo1@example.com`,
`ngo2@example.com` (vegetarian only), `ngo3@example.com` (pending verification).
Admin: `admin@example.com` / `ChangeMe@123` - **change these** with the environment variables below.

## Configuration (environment variables)

| Variable | Purpose | Default |
|---|---|---|
| `SHAREPLATE_SECRET` | JWT signing key - **set a long random value in production** | dev key (warning logged) |
| `SHAREPLATE_DB` | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pw@host/shareplate` | `sqlite:///./shareplate.db` |
| `SHAREPLATE_ADMIN_EMAIL` / `SHAREPLATE_ADMIN_PASSWORD` | Bootstrap admin created on first start | `admin@example.com` / `ChangeMe@123` |
| `SHAREPLATE_TOKEN_MINUTES` | Login token lifetime | `480` |

The PostgreSQL driver is included in `requirements.txt`.

## Deploy to Vercel

Vercel detects the FastAPI app in `app/main.py`; no separate frontend build is required.

1. Push this project to GitHub and import the repository in Vercel.
2. Create a persistent PostgreSQL database with a provider of your choice. Do not use the default SQLite database on Vercel: function filesystems are ephemeral, so data can be lost between invocations.
3. Add these environment variables in the Vercel project settings for **Production** (and Preview if needed):
   - `SHAREPLATE_DB`: your PostgreSQL connection URL, using the `postgresql+psycopg://` scheme.
   - `SHAREPLATE_SECRET`: a unique, long random value (for example, generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
   - `SHAREPLATE_ADMIN_EMAIL` and `SHAREPLATE_ADMIN_PASSWORD`: credentials for the initial administrator. Set these before the first deployment; the bootstrap admin is only created when no admin account exists.
4. Deploy. Vercel installs dependencies from `requirements.txt`; check the deployment logs and then open `/api/health`.

Never run `python seed.py` against the production database: it creates public demo accounts with a shared, hard-coded password. The seed script is for a local development database only.

## How it works

1. **Donor** posts food (type, kg, prepared time, deadline, storage, allergens, veg/non-veg, map location).
   Food-safety rules reject unsafe combinations (e.g. cooked food at room temperature kept more than 4 h).
2. **Matching engine** (`app/matching.py`) first applies hard constraints, then scores what is left:
   - within 50 km, quantity fits the NGO's *remaining* capacity (capacity minus food already claimed),
   - NGO can physically reach it before the deadline (travel time + 30 min handover),
   - vegetarian-only and excluded-allergen preferences respected.
   - Score = 0.40 x distance + 0.35 x urgency + 0.25 x capacity fit. Weights are constants at the top of the file.
3. Eligible verified NGOs are **notified** and see ranked matches with a score breakdown.
4. An NGO **claims** (atomic compare-and-set, so two NGOs can never claim the same donation), then marks
   **collected** or **releases** it. Uncollected food past its deadline is auto-marked **EXPIRED**.
5. **Admin** verifies/rejects organisations, monitors donations, manages users, reads the audit log and impact stats.

Roles: `donor`, `ngo` (must be verified to see matches or claim), `admin`. Nobody can self-register as admin.
Every state change writes an `audit_logs` row.

## Project layout

```
app/matching.py     matching engine (pure Python)       app/food_safety.py  safety rules (editable table)
app/models.py       SQLAlchemy models                   app/security.py     PBKDF2 hashing + JWT
app/deps.py         auth + role-based access control    app/services.py     audit, notifications, expiry sweep
app/routers/        auth, donations, ngo, admin, misc   static/index.html   frontend
tests/test_core.py  matching/safety/security tests      tests/test_api.py   end-to-end API tests
```

## Tests

```bash
python -m unittest tests.test_core     # no extra packages needed
pytest -q                              # full suite incl. API flow (needs requirements.txt)
```

## Before real-world use

- The food-safety hour limits in `app/food_safety.py` are conservative prototype defaults. Have a food-safety
  professional review them against FSSAI guidance.
- `KG_PER_MEAL = 0.4` in `app/config.py` is only an estimate used for the "meals" impact figure.
- Verification here means an admin reviews the registration details; add document upload and a real
  check against NGO registries before relying on it.
- Add HTTPS, a production secret, rate limiting on login, and a migration tool (Alembic) for schema changes.

## Ideas to extend

WebSocket/SSE live notifications, SMS/WhatsApp alerts, route optimisation for multi-pickup, donor/NGO ratings,
photo upload of food, analytics dashboards (waste saved per district), mobile app, scheduled recurring donations.
