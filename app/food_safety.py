"""Food-safety checks applied when a donation is posted (pure Python).

The hour limits below are conservative DEFAULTS for a prototype. Before a real
deployment they should be reviewed and set by a food-safety professional against
FSSAI guidance. They live in one table so they are easy to change.
"""
from datetime import datetime
from typing import List

FOOD_TYPES = ["cooked_meal", "raw_produce", "bakery", "dairy", "packaged", "beverage", "other"]
STORAGE_TYPES = ["hot_held", "room_temp", "refrigerated", "frozen"]

# max hours between preparation and the pickup deadline, by (food_type, storage)
MAX_AGE_HOURS = {
    ("cooked_meal", "hot_held"): 6,
    ("cooked_meal", "room_temp"): 4,
    ("cooked_meal", "refrigerated"): 24,
    ("cooked_meal", "frozen"): 72,
    ("dairy", "room_temp"): 2,
    ("dairy", "hot_held"): 2,
    ("dairy", "refrigerated"): 48,
    ("dairy", "frozen"): 24 * 30,
    ("bakery", "room_temp"): 48,
    ("bakery", "refrigerated"): 96,
    ("raw_produce", "room_temp"): 72,
    ("raw_produce", "refrigerated"): 120,
    ("beverage", "room_temp"): 24 * 7,
    ("beverage", "refrigerated"): 24 * 7,
    ("packaged", "room_temp"): 24 * 30,
    ("packaged", "refrigerated"): 24 * 30,
}
DEFAULT_MAX_AGE_HOURS = 24
MIN_REMAINING_MINUTES = 60  # a donation must leave at least this long to be collected


def validate(food_type: str, storage: str, prepared_at: datetime, expires_at: datetime, now: datetime) -> List[str]:
    errors: List[str] = []
    if food_type not in FOOD_TYPES:
        errors.append(f"food_type must be one of {FOOD_TYPES}")
    if storage not in STORAGE_TYPES:
        errors.append(f"storage must be one of {STORAGE_TYPES}")
    if prepared_at > now:
        errors.append("prepared_at cannot be in the future")
    if expires_at <= prepared_at:
        errors.append("expires_at must be after prepared_at")
    remaining_min = (expires_at - now).total_seconds() / 60
    if remaining_min < MIN_REMAINING_MINUTES:
        errors.append(f"at least {MIN_REMAINING_MINUTES} minutes must remain before the deadline")
    limit = MAX_AGE_HOURS.get((food_type, storage), DEFAULT_MAX_AGE_HOURS)
    age_at_deadline_h = (expires_at - prepared_at).total_seconds() / 3600
    if age_at_deadline_h > limit:
        errors.append(
            f"{food_type.replace('_', ' ')} kept {storage.replace('_', ' ')} should be consumed within "
            f"{limit} h of preparation; shorten the deadline"
        )
    return errors
