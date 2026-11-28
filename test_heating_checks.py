"""Independent physical checks for the winter-system screening calculations."""

import unittest

from heating_checks import (CP_AIR, CP_WATER, daily_balance, interpolate,
                            mixed_volume, pipe_loss, temperature_derating,
                            transfer_check, water_energy, water_flow_l_h)


class HeatingSystemChecks(unittest.TestCase):
    def test_hot_water_mixing_conserves_energy(self):
        mixed = mixed_volume(400, 55, 10, 40)
        self.assertEqual(mixed, 600)
        self.assertAlmostEqual(water_energy(400, 10, 55), water_energy(mixed, 10, 40))

    def test_confirmed_high_daily_use(self):
        self.assertAlmostEqual(water_energy(300, 10, 40), 10.465)
        self.assertAlmostEqual(water_energy(300, 10, 40)+.066*24, 12.049)

    def test_water_flow_returns_original_heat(self):
        q = water_flow_l_h(4798.9)
        self.assertAlmostEqual(q*CP_WATER*5, 4798.9)

    def test_temperature_derating_is_unity_at_reference(self):
        self.assertAlmostEqual(temperature_derating(45, 40), 1)
        self.assertLess(temperature_derating(40, 35), 1)
        self.assertGreater(temperature_derating(40, 35), .7)
        with self.assertRaises(ValueError):
            temperature_derating(25, 20)

    def test_lg_interpolation_does_not_extrapolate(self):
        self.assertAlmostEqual(interpolate([(-15, 5), (-5, 6)], -10), 5.5)
        self.assertAlmostEqual(interpolate([(-15, 5), (-5, 6)], -5), 6)
        with self.assertRaises(ValueError):
            interpolate([(-15, 5), (-5, 6)], -20)

    def test_daily_space_and_dhw_time_budget(self):
        r = daily_balance(4, 5, 4, 8)
        self.assertEqual(r["charging_h"], 2)
        self.assertEqual(r["space_kwh"], 96)
        self.assertEqual(r["space_backup_kwh"], 0)
        r = daily_balance(4.8, 5, 4, 12)
        self.assertAlmostEqual(r["space_backup_kwh"], 10.2)

    def test_no_transfer_heat_at_equal_temperature(self):
        r = transfer_check(800, 20, incoming_flow=160, target_c=20)
        self.assertEqual(r["air_gain_w"], 0)
        self.assertEqual(r["unexplained_w"], 800)
        self.assertIsNone(r["required_internal_conductance_w_k"])

    def test_lower_hall_temperature_does_not_invent_heat(self):
        r = transfer_check(800, 20, incoming_flow=160, target_c=18)
        self.assertEqual(r["loss_w"], 760)
        self.assertAlmostEqual(r["air_gain_w"], CP_AIR*160*2)
        self.assertAlmostEqual(r["unexplained_w"]+r["air_gain_w"], r["loss_w"])

    def test_laminar_pipe_drop_is_linear(self):
        one = pipe_loss(20, .016, 10)
        two = pipe_loss(40, .016, 10)
        self.assertLess(two["reynolds"], 2300)
        self.assertAlmostEqual(two["drop_kpa"], 2*one["drop_kpa"])
        self.assertEqual(pipe_loss(0, .016, 10)["drop_kpa"], 0)

    def test_turbulent_route_pressure_increases_with_length_and_flow(self):
        one = pipe_loss(948, .026, 20)
        two = pipe_loss(948, .026, 40)
        more = pipe_loss(1200, .026, 20)
        self.assertAlmostEqual(two["drop_kpa"], 2*one["drop_kpa"])
        self.assertGreater(more["drop_kpa"], one["drop_kpa"])
        self.assertGreater(one["reynolds"], 4000)

    def test_invalid_physical_inputs_rejected(self):
        for call in (lambda: water_energy(-1, 10, 40), lambda: water_flow_l_h(50, 0),
                     lambda: mixed_volume(400, 55, 10, 5), lambda: pipe_loss(100, 0, 10),
                     lambda: daily_balance(4, 5, 0, 8)):
            with self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
