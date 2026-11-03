"""HEB section geometry, in metres (nominal sizes supplied in millimetres).

Source: ArcelorMittal Orange Book, HE B section dimensions.
https://orangebook.arcelormittal.com/node/16
"""

from dataclasses import dataclass
from math import isfinite
import re


@dataclass(frozen=True)
class HEBSection:
    nominal: int
    height: float
    width: float
    web: float
    flange: float
    radius: float

    @property
    def name(self):
        return f"HEB{self.nominal}"


# Nominal: (overall depth, flange width, web, flange, root radius), all in mm.
_HEB_MM = {
    100: (100, 100, 6, 10, 12),
    120: (120, 120, 6.5, 11, 12),
    140: (140, 140, 7, 12, 12),
    160: (160, 160, 8, 13, 15),
    180: (180, 180, 8.5, 14, 15),
    200: (200, 200, 9, 15, 18),
    220: (220, 220, 9.5, 16, 18),
    240: (240, 240, 10, 17, 21),
    260: (260, 260, 10, 17.5, 24),
    280: (280, 280, 10.5, 18, 24),
    300: (300, 300, 11, 19, 27),
    320: (320, 300, 11.5, 20.5, 27),
    340: (340, 300, 12, 21.5, 27),
    360: (360, 300, 12.5, 22.5, 27),
    400: (400, 300, 13.5, 24, 27),
    450: (450, 300, 14, 26, 27),
    500: (500, 300, 14.5, 28, 27),
    550: (550, 300, 15, 29, 27),
    600: (600, 300, 15.5, 30, 27),
    650: (650, 300, 16, 31, 27),
    700: (700, 300, 17, 32, 27),
    800: (800, 300, 17.5, 33, 30),
    900: (900, 300, 18.5, 35, 30),
    1000: (1000, 300, 19, 36, 30),
}
HEB_SECTIONS = {size: HEBSection(size, *(value/1000 for value in dimensions))
                for size, dimensions in _HEB_MM.items()}


def heb_section(value: int | float | str) -> HEBSection:
    """Resolve a nominal size, e.g. 180, 'HEB180' or 'HE 180 B'."""
    if isinstance(value, str):
        match = re.fullmatch(r"(?:HEB\s*(\d+)|HE\s*(\d+)\s*B|(\d+))", value.strip(), re.IGNORECASE)
        if match is None:
            raise ValueError("heb must be a nominal size such as 180 or 'HEB180'")
        size = int(next(group for group in match.groups() if group is not None))
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("heb must be a nominal size in millimetres or an HEB name")
    elif not isfinite(value) or not float(value).is_integer():
        raise ValueError("heb must be a finite, whole nominal size in millimetres")
    else:
        size = int(value)
    if size not in HEB_SECTIONS:
        raise ValueError(f"unsupported HEB size {size}; choose {', '.join(map(str, HEB_SECTIONS))}")
    return HEB_SECTIONS[size]


def heb_profile(model, section: HEBSection):
    """Create a centred native IFC I-section, including root fillets."""
    return model.create_entity(
        "IfcIShapeProfileDef", ProfileType="AREA", ProfileName=section.name,
        OverallWidth=section.width, OverallDepth=section.height,
        WebThickness=section.web, FlangeThickness=section.flange,
        FilletRadius=section.radius,
    )
