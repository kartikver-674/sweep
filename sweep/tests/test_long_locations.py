"""A remote job open to almost every country is worldwide, and a long place
list never fills a results card (2026-11-20: a Himalayas posting named 202
countries, was filed under onsite-in-India and printed all 202)."""
import unittest

import enrich
from sources import feeds
from sweep.logic import short_places


class HimalayasLongLists(unittest.TestCase):

    def location(self, places):
        row = {}
        feeds._himalayas_extras({"locationRestrictions": places}, row)
        return row["Location"]

    def test_a_list_of_most_countries_reads_as_worldwide(self):
        places = [f"Country {i}" for i in range(202)]
        loc = self.location(places)
        self.assertEqual(loc, "Worldwide (202 countries)")
        # The scraper stamps feed rows ", Remote"; that must read worldwide.
        scoped = enrich.enrich({"Location": loc + ", Remote", "Title": "Engineer",
                                "Description": "We hire in US, LATAM, Europe, India."})
        self.assertEqual(scoped["remote_scope"], "worldwide")

    def test_a_short_list_is_still_a_real_restriction(self):
        self.assertEqual(self.location(["India", "Spain"]), "India, Spain")
        self.assertEqual(self.location([]), "Worldwide")


class ShortPlaces(unittest.TestCase):

    def test_long_lists_are_cut_with_a_count(self):
        loc = ", ".join(f"P{i}" for i in range(50))
        self.assertEqual(short_places(loc), "P0, P1, P2 and 47 more")

    def test_ordinary_locations_are_untouched(self):
        for loc in ("Bengaluru, Karnataka, India", "Remote", "", None,
                    "A, B, C, D, E, F"):
            self.assertEqual(short_places(loc), loc or "")


if __name__ == "__main__":
    unittest.main()
