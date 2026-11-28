"""Analytical heat-budget checks, independent of the project model geometry."""

from dataclasses import replace
import unittest

from shapely.geometry import box
from shapely.ops import unary_union

from heating_loss import (Assumptions, calculate, emitter_budgets, partition_plan,
                          roof_areas, wall_area)


class Inputs:
    def get(self, key):
        return {
            "INSULATION_LAMBDA_D_MAX": dict(roof_wool=.04, facade_wool=.04,
                floor_eps=.04, floor_wool=.04, stair_floor_wool=.04),
            "FACADE_INSULATION_THICKNESS": .20,
            "RAFTER_HEIGHT": .20, "THERMAL_INSULATION_UNDER_RAFTERS": .20,
            "GROUND_FLOOR_INSULATION_THICKNESS": .15,
            "GROUND_STAIR_OPENING_INSULATION_THICKNESS": .20,
        }[key]


def room_geometry(**overrides):
    data = dict(name="Test", wall_net_m2=20, window_m2=2, door_m2=1,
                roof_sloped_m2=0, roof_flat_m2=10, floor_regular_m2=8,
                floor_stair_m2=2, wall_gross_m2=23, gross_volume_m3=30,
                clear_floor_area_m2=10)
    return dict(data, **overrides)


class HeatingLossTests(unittest.TestCase):
    def test_rectangular_and_gabled_wall_areas(self):
        envelope = box(0, 0, 4, 3)
        self.assertAlmostEqual(wall_area(envelope, 4, 3, 0, [(0, 3), (4, 3)]), 42)
        # 2 side walls 3×2 + 2 gables (4×2 + 4×2/2).
        self.assertAlmostEqual(wall_area(envelope, 4, 3, 0, [(0, 2), (2, 4), (4, 2)]), 36)

    def test_roof_uses_actual_slope_without_overhangs(self):
        sloped, flat = roof_areas(box(0, 0, 6, 3), [(0, 1), (2, 2.5), (4, 2.5), (6, 1)], 3)
        self.assertAlmostEqual(sloped, 15)
        self.assertAlmostEqual(flat, 6)

    def test_partition_conserves_area_and_does_not_overlap(self):
        envelope = box(0, 0, 5, 4)
        zones = partition_plan({"a": box(.2, .2, 2.4, 3.8),
                                "b": box(2.6, .2, 4.8, 3.8)}, envelope, .20)
        self.assertAlmostEqual(sum(z.area for z in zones.values()), 20)
        self.assertAlmostEqual(unary_union(list(zones.values())).area, 20)
        self.assertAlmostEqual(zones["a"].intersection(zones["b"]).area, 0)
        self.assertLess(abs(zones["a"].area-zones["b"].area), .25)

    def test_partition_rejects_overlapping_rooms(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            partition_plan({"a": box(0, 0, 3, 4), "b": box(2, 0, 5, 4)}, box(0, 0, 5, 4))

    def test_known_steady_state_budget(self):
        geometry = dict(inputs=Inputs(), rooms={"0.01": room_geometry()})
        result = calculate(geometry, Assumptions(infiltration_ach=0, bridge_delta_u=0,
                                               ventilation_m3_h=0, timber_fraction=0))
        expected = 35*(20/(5+.17) + 2*1.2 + 1*1.5 + 10/(5+.14)
                       + 8/(.15/.04+.34) + 2/(5+.34))
        self.assertAlmostEqual(result["total_w"], expected)

    def test_basement_temperature_changes_only_floor_conduction(self):
        geometry = dict(inputs=Inputs(), rooms={"0.01": room_geometry()})
        cold = calculate(geometry)
        warm = calculate(geometry, replace(Assumptions(), basement_c=5))
        for key, value in cold["components_w"].items():
            if key.startswith("floor_"):
                self.assertAlmostEqual(warm["components_w"][key], value*15/35)
            else:
                self.assertAlmostEqual(warm["components_w"][key], value)

    def test_ventilation_counted_once_at_supply_not_extract(self):
        rooms = {r: room_geometry() for r in ("0.01", "0.02", "0.03", "0.05", "1.01", "1.02", "1.03")}
        result = calculate(dict(inputs=Inputs(), rooms=rooms))
        self.assertAlmostEqual(result["components_w"]["ventilation"], .34*240*.23*35)
        self.assertEqual(result["rooms"]["0.05"]["components_w"]["ventilation"], 0)

    def test_windows_replace_opaque_wall_rather_than_add_to_it(self):
        opaque = room_geometry(wall_net_m2=23, window_m2=0, door_m2=0)
        glazed = room_geometry(wall_net_m2=21, window_m2=2, door_m2=0)
        one = calculate(dict(inputs=Inputs(), rooms={"0.01": opaque}))
        two = calculate(dict(inputs=Inputs(), rooms={"0.01": glazed}))
        self.assertAlmostEqual(two["total_w"]-one["total_w"], 2*35*(1.2-one["u_w_m2k"]["wall"]))

    def test_emitter_allocation_conserves_common_space_losses(self):
        rooms = {r: room_geometry() for r in ("0.01", "0.02", "0.03", "0.04", "0.05", "1.01", "1.02", "1.03")}
        geometry = dict(inputs=Inputs(), rooms=rooms)
        result = calculate(geometry)
        budgets = emitter_budgets(geometry, result)
        self.assertAlmostEqual(sum(b["budget_w"] for b in budgets.values()), result["total_w"])
        self.assertAlmostEqual(sum(b["water_l_h"] for b in budgets.values()), result["total_w"]*.86/5)

    def test_invalid_inputs_rejected(self):
        for change in (dict(recovery=1.1), dict(infiltration_ach=-.1), dict(window_u=0),
                       dict(basement_c=21), dict(timber_fraction=1)):
            with self.assertRaises(ValueError):
                Assumptions(**change)


if __name__ == "__main__":
    unittest.main()
