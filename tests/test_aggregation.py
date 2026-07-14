import unittest

from weather_analysis.aggregation import CountyAggregator, find_rain_dates


class CountyAggregatorTest(unittest.TestCase):
    def test_rain_dates_come_from_the_room_that_produced_the_maximum(self):
        locations = [
            {"name": "A", "county": "C", "lon": 1, "lat": 1},
            {"name": "B", "county": "C", "lon": 2, "lat": 2},
        ]
        rooms = [
            {
                "name": "A",
                "county": "C",
                "tmax": 38,
                "tmin": 20,
                "maxPrecip": 1,
                "maxRainHours": 1,
                "dailySummary": [{"date": "2026-07-14", "precip": 1}],
            },
            {
                "name": "B",
                "county": "C",
                "tmax": 38,
                "tmin": 20,
                "maxPrecip": 10,
                "maxRainHours": 9,
                "dailySummary": [{"date": "2026-07-16", "precip": 10}],
            },
        ]

        county = CountyAggregator(locations).aggregate(rooms)[0]

        self.assertEqual(["2026-07-16"], find_rain_dates(county))


if __name__ == "__main__":
    unittest.main()
