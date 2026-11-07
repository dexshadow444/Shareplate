"""Framework-free tests for the matching engine, food-safety rules and security helpers.
Run with:  python -m unittest tests.test_core   (or pytest)"""
import unittest
from datetime import datetime, timedelta

from app import food_safety, matching, security
from app.matching import DonationInfo, NgoInfo

KOCHI = (9.9312, 76.2673)
THRISSUR = (10.5276, 76.2144)


def donation(**kw):
    base = dict(id=1, quantity_kg=10, hours_left=5, latitude=KOCHI[0], longitude=KOCHI[1], is_veg=True, allergens=frozenset())
    base.update(kw)
    return DonationInfo(**base)


def ngo(**kw):
    base = dict(id=1, latitude=10.0261, longitude=76.3125, available_capacity_kg=100)
    base.update(kw)
    return NgoInfo(**base)


class HaversineTests(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(matching.haversine_km(*KOCHI, *KOCHI), 0.0, places=6)

    def test_kochi_to_thrissur_is_about_65km(self):
        d = matching.haversine_km(*KOCHI, *THRISSUR)
        self.assertTrue(60 < d < 75, d)


class MatchingTests(unittest.TestCase):
    def test_nearby_donation_is_eligible(self):
        r = matching.evaluate(donation(), ngo())
        self.assertTrue(r.eligible, r.reasons)
        self.assertTrue(0 < r.score <= 1)

    def test_too_far_is_rejected(self):
        r = matching.evaluate(donation(latitude=THRISSUR[0], longitude=THRISSUR[1]), ngo(latitude=KOCHI[0], longitude=KOCHI[1]))
        self.assertFalse(r.eligible)
        self.assertTrue(any("too far" in x for x in r.reasons))

    def test_capacity_limit(self):
        r = matching.evaluate(donation(quantity_kg=50), ngo(available_capacity_kg=20))
        self.assertFalse(r.eligible)

    def test_cannot_arrive_before_deadline(self):
        r = matching.evaluate(donation(hours_left=0.3), ngo())  # 18 min left, needs travel + 30 min buffer
        self.assertFalse(r.eligible)

    def test_expired_is_rejected(self):
        self.assertFalse(matching.evaluate(donation(hours_left=-1), ngo()).eligible)

    def test_veg_only_blocks_non_veg(self):
        self.assertFalse(matching.evaluate(donation(is_veg=False), ngo(veg_only=True)).eligible)
        self.assertTrue(matching.evaluate(donation(is_veg=True), ngo(veg_only=True)).eligible)

    def test_allergen_overlap_blocks_case_insensitively(self):
        r = matching.evaluate(donation(allergens=frozenset({"Peanuts"})), ngo(excluded_allergens=frozenset({"peanuts"})))
        self.assertFalse(r.eligible)

    def test_more_urgent_scores_higher_all_else_equal(self):
        urgent = matching.evaluate(donation(hours_left=2), ngo())
        relaxed = matching.evaluate(donation(hours_left=20), ngo())
        self.assertGreater(urgent.score, relaxed.score)

    def test_closer_scores_higher_all_else_equal(self):
        near = matching.evaluate(donation(latitude=10.0261, longitude=76.3125), ngo())
        far = matching.evaluate(donation(latitude=9.8, longitude=76.3), ngo())
        self.assertGreater(near.score, far.score)

    def test_ranking_orders_best_first_and_drops_ineligible(self):
        ds = [donation(id=1, hours_left=20), donation(id=2, hours_left=2), donation(id=3, is_veg=False)]
        ranked = matching.rank_donations_for_ngo(ds, ngo(veg_only=True))
        self.assertEqual([r.donation_id for r in ranked], [2, 1])

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(matching.WEIGHTS.values()), 1.0)


class FoodSafetyTests(unittest.TestCase):
    now = datetime(2026, 10, 15, 12, 0)

    def check(self, food, storage, prep_h_ago, expires_in_h):
        return food_safety.validate(food, storage, self.now - timedelta(hours=prep_h_ago), self.now + timedelta(hours=expires_in_h), self.now)

    def test_reasonable_cooked_meal_passes(self):
        self.assertEqual(self.check("cooked_meal", "hot_held", 1, 3), [])

    def test_room_temp_cooked_over_four_hours_fails(self):
        self.assertTrue(self.check("cooked_meal", "room_temp", 1, 6))

    def test_future_preparation_fails(self):
        self.assertTrue(self.check("cooked_meal", "hot_held", -2, 3))

    def test_too_little_time_left_fails(self):
        self.assertTrue(self.check("cooked_meal", "hot_held", 1, 0.5))

    def test_unknown_type_is_reported(self):
        self.assertTrue(self.check("magic", "hot_held", 1, 3))


class SecurityTests(unittest.TestCase):
    def test_password_roundtrip(self):
        h = security.hash_password("Correct#Horse1")
        self.assertTrue(security.verify_password("Correct#Horse1", h))
        self.assertFalse(security.verify_password("wrong", h))
        self.assertNotEqual(h, security.hash_password("Correct#Horse1"))  # salted

    def test_garbage_hash_is_rejected(self):
        self.assertFalse(security.verify_password("x", "not-a-hash"))

    def test_token_roundtrip_and_tamper(self):
        t = security.create_token(42, "donor")
        self.assertEqual(security.decode_token(t), 42)
        self.assertIsNone(security.decode_token(t[:-3] + "abc"))
        self.assertIsNone(security.decode_token("garbage"))

    def test_default_db_url_is_writable_on_vercel(self):
        import os
        os.environ["VERCEL"] = "1"
        from importlib import reload
        import app.config as config_module
        reload(config_module)
        self.assertEqual(config_module._default_db_url(), "sqlite:////tmp/shareplate.db")
        os.environ.pop("VERCEL", None)


if __name__ == "__main__":
    unittest.main()
