"""Independent coordinate, clearance and level checks for the C drawings."""

from math import sqrt
import unittest
import xml.etree.ElementTree as ET

from shapely.geometry import LineString, Point, box

from cadastral_situation import NorthUpFrame
from cadastral_shading import roof_and_chimney_checks
from site_plan_annotations import boundary_setbacks, dimension_svg, forest_reference_edge, house_site_data, model_map_point
from survey_points import HOUSE_PLACEMENT, SurveyAxes, SurveyFrame, named_survey_groups, read_survey_groups


class SiteAnnotationTests(unittest.TestCase):
    def axes(self):
        groups=named_survey_groups(read_survey_groups('points.txt'))
        return SurveyAxes.from_polylines(groups['street'],groups['neighbour'])

    def test_facade_corners_match_survey_rectangle_in_rotated_map_frame(self):
        axes=self.axes()
        frame=NorthUpFrame(-588800,-1144300,.106)
        levels=house_site_data(axes,frame)
        w,d=levels['width_m'],levels['depth_m']
        outside=(HOUSE_PLACEMENT.width-w)/2
        coordinates=((-outside,-outside),(w+outside,-outside),(w+outside,d+outside),(-outside,d+outside))
        for model,cartesian in zip(coordinates,HOUSE_PLACEMENT.corners(axes)):
            sy,sx=axes.frame.to_survey(*cartesian)
            expected=frame.to_local(-sy,-sx)
            actual=model_map_point(*model,axes,frame,w,d)
            for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=7)

    def test_minimum_setback_uses_sloped_boundary_not_its_bounding_box(self):
        house=box(0,0,4,3)
        result=boundary_setbacks(house,{'west':LineString([(-5,-10),(-5,10)]),
                                      'diagonal':LineString([(-10,22),(20,-8)])})
        self.assertAlmostEqual(result[0]['distance_m'],5)
        self.assertAlmostEqual(result[1]['distance_m'],5/sqrt(2))
        self.assertAlmostEqual(sum(result[1]['endpoints_local_m'][1]),12)

    def test_forest_distance_uses_cadastral_edge_beside_reference_points(self):
        forest=box(10,-20,30,20)
        edge=forest_reference_edge(forest,[Point(10.7,-10),Point(10.5,-8)])
        # The survey references are beside the boundary, not on it.
        self.assertAlmostEqual(box(0,0,4,4).distance(edge),6)
        self.assertTrue(all(x==10 for x,y in edge.coords))
        with self.assertRaises(ValueError):
            forest_reference_edge(forest,[Point(-50,-50),Point(-49,-49)])

    def test_levels_agree_with_independent_full_roof_and_chimney_geometry(self):
        axes=self.axes();frame=NorthUpFrame(-588800,-1144300,.106)
        levels=house_site_data(axes,frame)
        roof=roof_and_chimney_checks(axes)
        self.assertAlmostEqual(levels['floor_elevation_bpv'],roof['floor_elevation_bpv'])
        self.assertAlmostEqual(levels['ridge_elevation_bpv'],max(p[2] for face in roof['roof_top_polygons'] for p in face))
        self.assertAlmostEqual(levels['chimney_elevation_bpv'],max(p[2] for p in roof['chimney_top_polygon']))

    def test_dimension_retains_endpoints_and_renders_readable_reversed_label(self):
        root=ET.fromstring(dimension_svg((40,40),(10,0),'10,00',identifier='test'))
        line=root.find('path')
        self.assertEqual(line.get('d'),'M40.0000,40.0000L10.0000,0.0000')
        text=root.find('text')
        self.assertEqual(text.text,'10,00')
        angle=float(text.get('transform').split('(')[1].split()[0])
        self.assertGreaterEqual(angle,-90);self.assertLessEqual(angle,90)


if __name__=='__main__':unittest.main()
