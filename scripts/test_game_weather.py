"""Tests for game_weather — venue/weather context (no network; ESPN/Open-Meteo
payloads are supplied directly, matching the codebase's debug-time API ban)."""
import unittest

from game_weather import classify_impact, venue_from_espn, weather_from_forecast


class TestVenueFromEspn(unittest.TestCase):
    def test_dome_short_circuits_no_geocode_needed(self):
        v = venue_from_espn({"fullName": "Mercedes-Benz Stadium",
                              "address": {"city": "Atlanta", "state": "GA"}, "indoor": True})
        self.assertTrue(v["indoor"])
        self.assertEqual(v["city"], "Atlanta")

    def test_outdoor_keeps_city_state_for_geocoding(self):
        v = venue_from_espn({"fullName": "Lumen Field",
                              "address": {"city": "Seattle", "state": "WA"}, "indoor": False})
        self.assertFalse(v["indoor"])
        self.assertEqual(v["city"], "Seattle")
        self.assertEqual(v["state"], "WA")

    def test_missing_venue_raises(self):
        with self.assertRaises(KeyError):
            venue_from_espn({})


class TestWeatherFromForecast(unittest.TestCase):
    def _hourly(self, times, temps, winds, precips):
        return {"time": times, "temperature_2m": temps, "wind_speed_10m": winds,
                "precipitation_probability": precips}

    def test_picks_closest_hour_to_kickoff(self):
        hourly = self._hourly(
            ["2026-09-07T17:00", "2026-09-07T18:00", "2026-09-07T19:00"],
            [70.0, 68.0, 65.0], [5.0, 12.0, 20.0], [0, 10, 40])
        w = weather_from_forecast(hourly, "2026-09-07T18:05Z")
        self.assertEqual(w["temp_f"], 68.0)
        self.assertEqual(w["wind_mph"], 12.0)
        self.assertEqual(w["precip_pct"], 10)

    def test_kickoff_outside_forecast_window_returns_none(self):
        hourly = self._hourly(["2026-09-07T17:00"], [70.0], [5.0], [0])
        w = weather_from_forecast(hourly, "2026-09-20T18:00Z")
        self.assertIsNone(w)

    def test_indoor_venue_returns_none_no_fetch_needed(self):
        # caller contract: dome games skip forecast entirely (see venue_from_espn)
        self.assertIsNone(weather_from_forecast(None, "2026-09-07T18:00Z"))


class TestClassifyImpact(unittest.TestCase):
    def test_dome_is_no_impact(self):
        note = classify_impact({"indoor": True})
        self.assertEqual(note["level"], "NONE")

    def test_calm_conditions_no_impact(self):
        note = classify_impact({"indoor": False, "wind_mph": 6, "temp_f": 65, "precip_pct": 5})
        self.assertEqual(note["level"], "NONE")

    def test_high_wind_flags_kicking_and_passing(self):
        note = classify_impact({"indoor": False, "wind_mph": 22, "temp_f": 55, "precip_pct": 10})
        self.assertEqual(note["level"], "HIGH")
        self.assertIn("wind", note["note"].lower())

    def test_freezing_temp_flags_cold_weather_game(self):
        note = classify_impact({"indoor": False, "wind_mph": 8, "temp_f": 18, "precip_pct": 0})
        self.assertIn(note["level"], ("MODERATE", "HIGH"))
        self.assertIn("cold", note["note"].lower())

    def test_heavy_precip_flags_ball_security(self):
        note = classify_impact({"indoor": False, "wind_mph": 8, "temp_f": 50, "precip_pct": 75})
        self.assertIn(note["level"], ("MODERATE", "HIGH"))
        self.assertIn("precip", note["note"].lower())

    def test_missing_weather_is_unknown_not_none(self):
        note = classify_impact({"indoor": False, "wind_mph": None, "temp_f": None, "precip_pct": None})
        self.assertEqual(note["level"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
