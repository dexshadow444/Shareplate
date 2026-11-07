import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import settings
from .database import Base, SessionLocal, engine
from .models import Role, User
from .routers import admin, auth, donations, misc, ngo
from .security import hash_password

log = logging.getLogger("shareplate")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def bootstrap_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.role == Role.ADMIN)) is None:
            db.add(User(email=settings.ADMIN_EMAIL.lower(), full_name="Administrator",
                        hashed_password=hash_password(settings.ADMIN_PASSWORD), role=Role.ADMIN))
            db.commit()
            log.warning("Created bootstrap admin %s - change its password / set SHAREPLATE_ADMIN_PASSWORD",
                        settings.ADMIN_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.USING_DEFAULT_SECRET:
        log.warning("Using the default development SECRET_KEY. Set SHAREPLATE_SECRET before deploying.")
    Base.metadata.create_all(engine)
    bootstrap_admin()
    yield


app = FastAPI(
    title="SharePlate",
    description="Intelligent surplus food redistribution across Kerala",
    version="1.0.0",
    lifespan=lifespan,
)

for r in (auth.router, donations.router, ngo.router, admin.router, misc.router):
    app.include_router(r)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
