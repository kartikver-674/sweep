"""The default seniority cut follows the résumé's years (2026-11-20)."""
import unittest

import make_profile as m


class TestLevelsFor(unittest.TestCase):

    def test_a_fresher_keeps_internships_and_junior_roles(self):
        cut = m.levels_for(0)
        for kept in ("intern", "fresher", "trainee", "new grad", "junior"):
            self.assertNotIn(kept, cut)
        self.assertIn("director", cut)

    def test_two_years_drops_internships_and_the_top_not_junior(self):
        cut = m.levels_for(2)
        self.assertIn("intern", cut)
        self.assertIn("principal", cut)
        self.assertNotIn("junior", cut)

    def test_mid_career_drops_entry_and_top(self):
        cut = m.levels_for(4)
        self.assertIn("new grad", cut)
        self.assertIn("vp", cut)
        self.assertNotIn("manager", cut)

    def test_seven_years_is_the_old_list(self):
        self.assertEqual(m.levels_for(7), m.levels_for(None))
        self.assertIn("junior", m.levels_for(7))

    def test_staff_and_senior_are_never_hard_dropped(self):
        """"staff" would delete "Member of Technical Staff"; "senior" and
        "lead" are down-ranked by config's soft_drop_terms instead."""
        for years in (None, 0, 1, 2, 3, 5, 7, 15):
            for term in ("staff", "senior", "sr", "lead"):
                self.assertNotIn(term, m.levels_for(years), (years, term))

    def test_a_person_s_own_choice_wins(self):
        prefs = {"exclude_levels": ["contract"]}
        self.assertEqual(m.with_levels(prefs, 1), prefs)
        self.assertEqual(m.with_levels({"exclude_levels": None}, 1)["exclude_levels"],
                         m.levels_for(1))


if __name__ == "__main__":
    unittest.main()
