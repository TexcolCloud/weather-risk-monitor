import unittest

from qweather_none_agent.selectors import select_top_rooms


class SelectorsTest(unittest.TestCase):
    def test_top_rooms_are_not_evenly_capped_at_three_per_county(self):
        rooms = [{"name": f"A{i}", "county": "A", "tmax": 41, "maxCont37": 8} for i in range(8)] + [
            {"name": f"B{i}", "county": "B", "tmax": 38, "maxCont37": 2} for i in range(8)
        ]
        focus_counties = [{"name": "A"}, {"name": "B"}]

        selected = select_top_rooms(rooms, focus_counties)

        self.assertEqual(10, len(selected))
        self.assertGreater(sum(1 for room in selected if room["county"] == "A"), 3)


if __name__ == "__main__":
    unittest.main()
