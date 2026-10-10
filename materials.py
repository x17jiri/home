"""Shared structural timber grades for IFC schedules and roof calculations.

No IFC, plotting or solver dependencies. Strengths are characteristic values;
stiffnesses are mean values. Project loads, selected grades and drawing styles
belong to their callers, not this registry. The mean density below is used for
connection slip calculations, NOT as a replacement for configured self-weight.

Solid timber: EN 338:2016. Glulam: EN 14080:2013. Recommended gamma_M:
EN 1995-1-1. Published tables: Swedish Wood, Design of timber structures,
Volume 2 (2022), Tables 3.1, 3.3 and 3.4:
https://www.swedishwood.com/siteassets/5-publikationer/pdfer/sw-design-of-timber-structures-vol2-2022.pdf
"""

from dataclasses import dataclass
from types import MappingProxyType


TIMBER_MATERIAL_PARTIAL_FACTOR = 1.30


@dataclass(frozen=True)
class TimberGrade:
    name: str
    elastic_modulus_gpa: float
    bending_strength_mpa: float
    shear_strength_mpa: float
    compression_parallel_mpa: float
    compression_perpendicular_mpa: float
    material_partial_factor: float = TIMBER_MATERIAL_PARTIAL_FACTOR
    # Optional for backwards-compatible custom grades used in 2D checks.
    shear_modulus_gpa: float | None = None
    perpendicular_modulus_mpa: float | None = None
    mean_density_kg_m3: float | None = None

    @property
    def elastic_modulus_pa(self) -> float:
        return self.elastic_modulus_gpa * 1e9

    @property
    def shear_modulus_pa(self) -> float:
        if self.shear_modulus_gpa is None:
            raise ValueError(f"shear modulus is not defined for {self.name}")
        return self.shear_modulus_gpa * 1e9

    @property
    def perpendicular_modulus_pa(self) -> float:
        if self.perpendicular_modulus_mpa is None:
            raise ValueError(f"perpendicular modulus is not defined for {self.name}")
        return self.perpendicular_modulus_mpa * 1e6


TIMBER_GRADES = MappingProxyType({
    "c16": TimberGrade("C16", 8.0, 16.0, 3.2, 17.0, 2.2,
                       shear_modulus_gpa=0.50, perpendicular_modulus_mpa=270,
                       mean_density_kg_m3=370),
    "c18": TimberGrade("C18", 9.0, 18.0, 3.4, 18.0, 2.2,
                       shear_modulus_gpa=0.56, perpendicular_modulus_mpa=300,
                       mean_density_kg_m3=380),
    "c20": TimberGrade("C20", 9.5, 20.0, 3.6, 19.0, 2.3,
                       shear_modulus_gpa=0.59, perpendicular_modulus_mpa=320,
                       mean_density_kg_m3=400),
    "c22": TimberGrade("C22", 10.0, 22.0, 3.8, 20.0, 2.4,
                       shear_modulus_gpa=0.63, perpendicular_modulus_mpa=330,
                       mean_density_kg_m3=410),
    "c24": TimberGrade("C24", 11.0, 24.0, 4.0, 21.0, 2.5,
                       shear_modulus_gpa=0.69, perpendicular_modulus_mpa=370,
                       mean_density_kg_m3=420),
    "gl24c": TimberGrade("GL24c", 11.0, 24.0, 3.5, 21.5, 2.5, 1.25,
                         shear_modulus_gpa=0.65, perpendicular_modulus_mpa=300,
                         mean_density_kg_m3=400),
    "gl24h": TimberGrade("GL24h", 11.5, 24.0, 3.5, 24.0, 2.5, 1.25,
                         shear_modulus_gpa=0.65, perpendicular_modulus_mpa=300,
                         mean_density_kg_m3=420),
    "gl28c": TimberGrade("GL28c", 12.5, 28.0, 3.5, 24.0, 2.5, 1.25,
                         shear_modulus_gpa=0.65, perpendicular_modulus_mpa=300,
                         mean_density_kg_m3=420),
    "gl28h": TimberGrade("GL28h", 12.6, 28.0, 3.5, 28.0, 2.5, 1.25,
                         shear_modulus_gpa=0.65, perpendicular_modulus_mpa=300,
                         mean_density_kg_m3=460),
})
TIMBER_GRADE_NAMES = tuple(grade.name for grade in TIMBER_GRADES.values())


def resolve_timber_grade(material: str | TimberGrade) -> TimberGrade:
    """Resolve a case-insensitive registry key/name, or retain a custom grade."""
    if isinstance(material, TimberGrade):
        return material
    if not isinstance(material, str):
        choices = ", ".join(repr(name) for name in sorted(TIMBER_GRADES))
        raise TypeError(f"material must be {choices}, or a TimberGrade")
    try:
        return TIMBER_GRADES[material.strip().lower()]
    except KeyError as error:
        choices = ", ".join(sorted(TIMBER_GRADES))
        raise ValueError(f"unknown timber material; choose {choices}") from error
