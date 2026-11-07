"""Application settings, read from environment variables with safe-for-dev defaults."""
import os

_DEFAULT_SECRET = "dev-only-secret-change-me-before-deploying-0123456789"


class Settings:
    # --- security ---
    SECRET_KEY: str = os.getenv("SHAREPLATE_SECRET", _DEFAULT_SECRET)
    TOKEN_MINUTES: int = int(os.getenv("SHAREPLATE_TOKEN_MINUTES", "480"))
    USING_DEFAULT_SECRET: bool = SECRET_KEY == _DEFAULT_SECRET

    # --- database (SQLite for dev; set a postgresql+psycopg://... URL for production) ---
    DATABASE_URL: str = os.getenv("SHAREPLATE_DB", "sqlite:///./shareplate.db")

    # --- bootstrap admin (created on first start if missing) ---
    ADMIN_EMAIL: str = os.getenv("SHAREPLATE_ADMIN_EMAIL", "admin@example.com")
    ADMIN_PASSWORD: str = os.getenv("SHAREPLATE_ADMIN_PASSWORD", "ChangeMe@123")

    # --- service area: bounding box for Kerala (south, north, west, east) ---
    LAT_MIN: float = 8.0
    LAT_MAX: float = 12.95
    LNG_MIN: float = 74.8
    LNG_MAX: float = 77.6

    # --- impact estimate: kg of food per meal (approximation, adjust as needed) ---
    KG_PER_MEAL: float = 0.4


settings = Settings()
