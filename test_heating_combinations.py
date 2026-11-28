"""Energy conservation and fixed-reference checks for the FCU alternatives."""

import unittest

from heating_combinations import TEMPERATURES, output_w, ventilation_loads


class MixedRoomChecks(unittest.TestCase):
    def test_uniform_temperatures_recover_original_ventilation_loss(self):
        result = ventilation_loads({r: 25 for r in TEMPERATURES})
        self.assertAlmostEqual(result["total_w"], .34*240*.23*40)
        self.assertAlmostEqual(result["rooms_w"]["0.04"], 0)

    def test_mixed_airflow_energy_balance_includes_room_transfers(self):
        result = ventilation_loads(TEMPERATURES)
        self.assertAlmostEqual(result["extract_c"], 23.75)
        self.assertAlmostEqual(result["total_w"], .34*240*.23*38.75)
        self.assertAlmostEqual(sum(result["rooms_w"].values()), result["total_w"])
        self.assertAlmostEqual(result["rooms_w"]["0.04"], -204)
        self.assertAlmostEqual(result["rooms_w"]["0.05"], 102)
        self.assertAlmostEqual(result["rooms_w"]["1.02"], 68)

    def test_reference_temperature_difference_is_fixed(self):
        self.assertAlmostEqual(output_w("SL600", "low", 45, 40, 20), 1200)
        self.assertAlmostEqual(output_w("SL600", "low", 50, 45, 25), 1200)
        self.assertLess(output_w("SL600", "low", 45, 40, 25), 1200)

    def test_small_water_room_difference_reduces_output(self):
        value = output_w("SL600", "low", 40, 35, 25)
        self.assertAlmostEqual(value, 660.4076558558502)
        with self.assertRaises(ValueError):
            output_w("SL600", "low", 30, 25, 25)


if __name__ == "__main__":
    unittest.main()
