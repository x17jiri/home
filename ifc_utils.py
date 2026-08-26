"""Minimal helpers for describing a house as an IFC model.

The public API uses metres and a conventional right-handed coordinate system:
X and Y lie in the floor plane and Z points upwards.  A wall's axis follows the
line between its two supplied points, and its construction is positioned
relative to that axis.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from difflib import get_close_matches
from html import escape
import json
from math import atan2, cos, hypot, isfinite, radians, sin
from os import PathLike, environ
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Literal, Sequence, TypeAlias

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.document
import ifcopenshell.api.drawing
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.group
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.api.type
import ifcopenshell.api.unit
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import ifcopenshell.util.type
from ifcopenshell.util.shape_builder import ShapeBuilder
import numpy as np


__all__ = [
    "AssetCatalog",
    "AssetInfo",
    "Beam",
    "Chimney",
    "Drawing",
    "FacadeLayer",
    "HorizontalFrame",
    "House",
    "MiakoSlab",
    "Roof",
    "RoofLayer",
    "RoofPlane",
    "Stair",
    "Storey",
    "VerticalFrame",
    "Wall",
    "generate_plan",
    "offset_plane",
]

Number: TypeAlias = int | float
Point: TypeAlias = tuple[Number, Number]
Point3D: TypeAlias = tuple[Number, Number, Number]
DrawingView: TypeAlias = Literal["plan", "elevation"]
WallSide: TypeAlias = Literal["left", "right"]
PlaneCut: TypeAlias = tuple[Point3D, Point3D, Point3D]
WallCut: TypeAlias = PlaneCut
Layer: TypeAlias = tuple[str, Number]
LayerItem: TypeAlias = Layer | Literal["axis"]
DoorOperation: TypeAlias = Literal[
    "SINGLE_SWING_LEFT",
    "SINGLE_SWING_RIGHT",
    "DOUBLE_SWING_RIGHT",
    "DOUBLE_SWING_LEFT",
    "DOUBLE_DOOR_SINGLE_SWING",
    "DOUBLE_DOOR_DOUBLE_SWING",
    "SLIDING_TO_LEFT",
    "SLIDING_TO_RIGHT",
    "DOUBLE_DOOR_SLIDING",
]
WindowPartition: TypeAlias = Literal[
    "SINGLE_PANEL",
    "DOUBLE_PANEL_HORIZONTAL",
    "DOUBLE_PANEL_VERTICAL",
    "TRIPLE_PANEL_BOTTOM",
    "TRIPLE_PANEL_TOP",
    "TRIPLE_PANEL_LEFT",
    "TRIPLE_PANEL_RIGHT",
    "TRIPLE_PANEL_HORIZONTAL",
    "TRIPLE_PANEL_VERTICAL",
]
WindowAlignment: TypeAlias = Literal["axis", "inside"]
FurnitureKind: TypeAlias = Literal[
    "CHAIR",
    "TABLE",
    "DESK",
    "BED",
    "FILECABINET",
    "SHELF",
    "SOFA",
    "USERDEFINED",
    "NOTDEFINED",
]


@dataclass(frozen=True)
class AssetInfo:
    """A discoverable object type in the configured IFC asset library."""

    alias: str
    type_name: str
    category: str
    ifc_class: str
    ifc_type_class: str


_ASSET_PRIMARY_ALIASES = {
    "Neufert Toilet with Cistern": "toilet_with_cistern",
    "Generic Toilet without Cistern": "toilet_without_cistern",
    "Neufert Extra Small Basin": "basin_extra_small",
    "Neufert Small Basin": "basin_small",
    "Neufert Medium Basin": "basin_medium",
    "Neufert Large Basin": "basin_large",
    "Neufert Small Bathtub": "bathtub_small",
    "Neufert Medium Bathtub": "bathtub_medium",
    "Neufert Large Bathtub": "bathtub_large",
    "Neufert Dishwasher": "dishwasher",
    "Neufert Washing Machine": "washing_machine",
    "Neufert Drier": "dryer",
    "Generic Small Fridge Zone": "fridge_small",
    "Generic Medium Fridge Zone": "fridge_medium",
    "Generic Large Fridge Zone": "fridge_large",
    "Neufert Small Kitchen Bench": "kitchen_bench_small",
    "Neufert Medium Kitchen Bench": "kitchen_bench_medium",
    "Neufert Large Kitchen Bench": "kitchen_bench_large",
}

_ASSET_SYNONYMS = {
    "basin": "basin_medium",
    "cooker": "cooktop_58x51",
    "drier": "dryer",
    "fridge": "fridge_medium",
    "sink": "sink_86x44",
    "toilet": "toilet_with_cistern",
    "washbasin": "basin_medium",
    "wc": "toilet_with_cistern",
}


def _asset_alias(type_name: str) -> str:
    alias = type_name
    for prefix in ("Generic ", "Neufert "):
        if alias.startswith(prefix):
            alias = alias[len(prefix) :]
            break
    alias = re.sub(r"[^a-z0-9]+", "_", alias.casefold()).strip("_")
    return _ASSET_PRIMARY_ALIASES.get(type_name, alias)


def _asset_category(type_name: str, ifc_type_class: str) -> str:
    if ifc_type_class == "IfcSanitaryTerminalType":
        return "sanitary"
    if ifc_type_class == "IfcElectricApplianceType":
        return "appliances"

    name = type_name.casefold()
    if any(word in name for word in ("bed", "wardrobe")):
        return "bedroom"
    if any(word in name for word in ("kitchen", "cupboard", "island", "laundry")):
        return "kitchen"
    if "desk" in name:
        return "office"
    if any(word in name for word in ("chair", "stool", "sofa")):
        return "seating"
    if "table" in name:
        return "tables"
    return "furniture"


def _find_bonsai_furniture_library() -> Path:
    configured = environ.get("BONSAI_FURNITURE_LIBRARY")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return path
        raise FileNotFoundError(
            f"BONSAI_FURNITURE_LIBRARY does not name a file: {path}"
        )

    filename = "IFC4 Furniture Library.ifc"
    candidates = [Path(__file__).resolve().parent / filename]
    candidates.extend(
        Path.home().glob(
            ".config/blender/*/extensions/.local/lib/python*/site-packages/"
            f"bonsai/bim/data/libraries/{filename}"
        )
    )
    existing = [path for path in candidates if path.is_file()]
    if existing:
        return max(existing, key=lambda path: path.stat().st_mtime)
    raise FileNotFoundError(
        "Bonsai's IFC4 Furniture Library.ifc was not found. Install Bonsai, "
        "pass asset_library=... to House(), or set BONSAI_FURNITURE_LIBRARY."
    )


class AssetCatalog:
    """Search and import plan-ready object types from a Bonsai IFC library."""

    def __init__(
        self,
        house: House,
        library_path: str | PathLike[str] | None = None,
    ) -> None:
        self._house = house
        self._configured_path = (
            None if library_path is None else Path(library_path).expanduser()
        )
        self._path: Path | None = None
        self._library: ifcopenshell.file | None = None
        self._entries: tuple[AssetInfo, ...] | None = None
        self._source_types: dict[str, ifcopenshell.entity_instance] = {}
        self._imported_types: dict[str, ifcopenshell.entity_instance] = {}
        self._reuse_identities: dict[int, ifcopenshell.entity_instance] = {}
        self._bounds: dict[str, tuple[float, float, float, float, float, float]] = {}

    @property
    def path(self) -> Path:
        """Return the automatically discovered or explicitly configured library path."""
        self._load()
        assert self._path is not None
        return self._path

    def list(self, *, category: str | None = None) -> tuple[AssetInfo, ...]:
        """List available assets, optionally limited to a category."""
        self._load()
        assert self._entries is not None
        if category is None:
            return self._entries
        category_name = _name(category, "category").casefold()
        return tuple(
            entry for entry in self._entries if entry.category == category_name
        )

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
    ) -> tuple[AssetInfo, ...]:
        """Find assets by friendly alias, synonym, or original library name."""
        query_text = _name(query, "query").casefold()
        query_alias = query_text.replace("-", "_").replace(" ", "_")
        normalised_query = query_text.replace("_", " ").replace("-", " ")
        entries = self.list(category=category)
        terms = normalised_query.split()

        def aliases_for(entry: AssetInfo) -> tuple[str, ...]:
            synonyms = tuple(
                synonym
                for synonym, target in _ASSET_SYNONYMS.items()
                if target == entry.alias
            )
            return (entry.alias, *synonyms)

        matches = []
        for entry in entries:
            aliases = aliases_for(entry)
            haystack = " ".join((*aliases, entry.type_name.casefold())).replace(
                "_", " "
            )
            if not all(term in haystack for term in terms):
                continue
            exact_alias = query_alias in aliases
            prefix_alias = any(alias.startswith(query_alias) for alias in aliases)
            name_position = haystack.find(normalised_query)
            matches.append(
                (
                    0 if exact_alias else 1 if prefix_alias else 2,
                    name_position if name_position >= 0 else len(haystack),
                    entry.alias,
                    entry,
                )
            )
        return tuple(item[-1] for item in sorted(matches))

    def _load(self) -> None:
        if self._library is not None:
            return
        path = self._configured_path or _find_bonsai_furniture_library()
        if not path.is_file():
            raise FileNotFoundError(f"asset library does not exist: {path}")
        library = ifcopenshell.open(path)
        if library.schema != self._house.model.schema:
            raise ValueError(
                f"asset library uses {library.schema}; house uses {self._house.model.schema}"
            )

        entries = []
        used_aliases: set[str] = set()
        for source_type in library.by_type("IfcTypeProduct"):
            type_name = source_type.Name
            if not type_name:
                continue
            occurrence_classes = ifcopenshell.util.type.get_applicable_entities(
                source_type.is_a(), self._house.model.schema
            )
            occurrence_class = next(
                (
                    ifc_class
                    for ifc_class in occurrence_classes
                    if ifc_class != "IfcSpace"
                ),
                None,
            )
            if occurrence_class is None:
                continue
            has_plan_body = any(
                representation_map.MappedRepresentation.ContextOfItems.ContextType
                == "Plan"
                and representation_map.MappedRepresentation.ContextOfItems.ContextIdentifier
                == "Body"
                for representation_map in source_type.RepresentationMaps or ()
            )
            if not has_plan_body:
                continue

            base_alias = _asset_alias(type_name)
            alias = base_alias
            suffix = 2
            while alias in used_aliases:
                alias = f"{base_alias}_{suffix}"
                suffix += 1
            used_aliases.add(alias)
            entry = AssetInfo(
                alias=alias,
                type_name=type_name,
                category=_asset_category(type_name, source_type.is_a()),
                ifc_class=occurrence_class,
                ifc_type_class=source_type.is_a(),
            )
            entries.append(entry)
            self._source_types[type_name] = source_type

        self._path = path.resolve()
        self._library = library
        self._entries = tuple(sorted(entries, key=lambda entry: entry.alias))

    def _resolve(
        self,
        *,
        asset: str | AssetInfo | None,
        type_name: str | None,
    ) -> AssetInfo:
        if (asset is None) == (type_name is None):
            raise TypeError("supply exactly one of asset or type_name")
        self._load()
        assert self._entries is not None

        if isinstance(asset, AssetInfo):
            type_name = asset.type_name
            asset = None
        if type_name is not None:
            requested_type = _name(type_name, "type_name")
            entry = next(
                (
                    candidate
                    for candidate in self._entries
                    if candidate.type_name.casefold() == requested_type.casefold()
                ),
                None,
            )
            if entry is None:
                choices = [candidate.type_name for candidate in self._entries]
                suggestions = get_close_matches(requested_type, choices, n=3)
                hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
                raise ValueError(f'unknown asset type_name "{requested_type}".{hint}')
            return entry

        if not isinstance(asset, str):
            raise TypeError("asset must be a string or AssetInfo")
        requested_alias = _name(asset, "asset").casefold().replace("-", "_")
        requested_alias = _ASSET_SYNONYMS.get(requested_alias, requested_alias)
        entry = next(
            (
                candidate
                for candidate in self._entries
                if candidate.alias == requested_alias
            ),
            None,
        )
        if entry is not None:
            return entry

        choices = [candidate.alias for candidate in self._entries]
        suggestions = get_close_matches(requested_alias, choices, n=3)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        raise ValueError(
            f'unknown asset "{asset}".{hint} Use house.assets.search(...) to browse.'
        )

    def _import_type(self, entry: AssetInfo) -> ifcopenshell.entity_instance:
        imported = self._imported_types.get(entry.type_name)
        if imported is not None:
            return imported
        self._load()
        assert self._library is not None
        imported = ifcopenshell.api.project.append_asset(
            self._house.model,
            library=self._library,
            element=self._source_types[entry.type_name],
            reuse_identities=self._reuse_identities,
        )
        self._imported_types[entry.type_name] = imported
        return imported

    def _local_bounds(
        self,
        entry: AssetInfo,
        occurrence: ifcopenshell.entity_instance,
    ) -> tuple[float, float, float, float, float, float]:
        bounds = self._bounds.get(entry.type_name)
        if bounds is not None:
            return bounds
        try:
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), occurrence
            )
            vertices = shape.geometry.verts
            coordinates = tuple(zip(vertices[::3], vertices[1::3], vertices[2::3]))
            if not coordinates:
                raise ValueError("empty body")
            bounds = (
                min(point[0] for point in coordinates),
                min(point[1] for point in coordinates),
                min(point[2] for point in coordinates),
                max(point[0] for point in coordinates),
                max(point[1] for point in coordinates),
                max(point[2] for point in coordinates),
            )
        except (RuntimeError, ValueError) as error:
            raise RuntimeError(
                f'asset "{entry.alias}" has no usable 3D body'
            ) from error
        self._bounds[entry.type_name] = bounds
        return bounds


_DOOR_OVERHEAD_LINE = re.compile(
    r'(?P<indent>^[ \t]*)<line\b(?P<attrs>[^>\n]*\bdoor-overhead\b[^>\n]*)/>[ \t]*$',
    re.MULTILINE,
)

_SVG_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_DIMENSION_LABEL = re.compile(
    rf'(?P<prefix><line\b(?P<line_attrs>[^>\n]*\bPredefinedType-DIMENSION\b[^>\n]*)/>'
    rf'\s*<text\b[^>\n]*\btransform="translate\()'
    rf'(?P<text_x>{_SVG_NUMBER}),\s*(?P<text_y>{_SVG_NUMBER})'
    rf'(?P<suffix>\)\s*rotate\([^"\n]+\)"[^>\n]*>)'
)


def _overhead_mask_global_ids(
    model: ifcopenshell.file,
    cut_z: float,
) -> set[str]:
    """Return overhead annotations whose openings intersect the plan cut."""
    result = set()
    tolerance = 1e-9
    for annotation in model.by_type("IfcAnnotation"):
        properties = ifcopenshell.util.element.get_pset(
            annotation, "EPset_Annotation"
        )
        classes = properties.get("Classes", "") if properties else ""
        if "door-overhead" not in classes.split():
            continue
        bottom = properties.get("OpeningBottom")
        top = properties.get("OpeningTop")
        if bottom is None or top is None:
            # Preserve the masking behaviour of IFC files created before the
            # opening elevations were recorded on their annotations.
            result.add(annotation.GlobalId)
            continue
        placement = ifcopenshell.util.placement.get_local_placement(
            annotation.ObjectPlacement
        )
        opening_bottom = float(placement[2, 3]) + float(bottom)
        opening_top = float(placement[2, 3]) + float(top)
        if (
            opening_bottom - tolerance
            <= cut_z
            <= opening_top + tolerance
        ):
            result.add(annotation.GlobalId)
    return result


def _postprocess_miako_reinforcement_overlays(svg_path: Path) -> None:
    """Draw cut MIAKO reinforcement above its filled concrete cover."""
    svg = svg_path.read_text(encoding="utf-8")
    if '<g class="miako-reinforcement-overlays' in svg:
        return

    reinforcement_sources: dict[
        str,
        tuple[int, re.Match[str], dict[str, str]],
    ] = {}
    for match in re.finditer(r'<g\b(?P<attrs>[^>\n]*)>', svg):
        attributes = dict(
            re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"])
        )
        classes = set(attributes.get("class", "").split())
        if "material-MIAKOreinforcement" not in classes:
            continue
        view_class = "cut" if "cut" in classes else "projection"
        if view_class not in classes:
            continue
        source_key = (
            attributes.get("ifc:guid")
            or attributes.get("ifc:name")
            or attributes.get("id")
            or str(match.start())
        )
        priority = 2 if view_class == "cut" else 1
        existing = reinforcement_sources.get(source_key)
        if existing is None or priority > existing[0]:
            reinforcement_sources[source_key] = (
                priority,
                match,
                attributes,
            )

    reinforcement_ids = []
    id_insertions = []
    for index, (_, match, attributes) in enumerate(
        reinforcement_sources.values(),
        start=1,
    ):
        element_id = attributes.get("id")
        if element_id is None:
            element_id = f"miako-reinforcement-overlay-source-{index}"
            id_insertions.append((match.end() - 1, f' id="{element_id}"'))
        reinforcement_ids.append(element_id)

    for offset, identifier in reversed(id_insertions):
        svg = f"{svg[:offset]}{identifier}{svg[offset:]}"

    closing_svg = svg.rfind("</svg>")
    if not reinforcement_ids or closing_svg < 0:
        return
    uses = "\n".join(
        f'    <use href="#{element_id}" xlink:href="#{element_id}"/>'
        for element_id in reinforcement_ids
    )
    overlays = (
        '<g class="miako-reinforcement-overlays '
        'target-view-ELEVATIONVIEW">\n'
        f"{uses}\n"
        "  </g>\n"
    )
    svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
    svg_path.write_text(svg, encoding="utf-8")


def _postprocess_vapour_barrier_overlays(svg_path: Path) -> None:
    """Draw sectioned vapour barriers above coincident insulation edges."""
    svg = svg_path.read_text(encoding="utf-8")
    if '<g class="vapour-barrier-overlays' in svg:
        return

    candidates = []
    for match in re.finditer(r'<g\b(?P<attrs>[^>\n]*)>', svg):
        attributes = dict(
            re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"])
        )
        classes = set(attributes.get("class", "").split())
        if "material-Vapourbarrier" not in classes:
            continue
        if "cut" in classes:
            priority = 2
        elif "projection" in classes:
            priority = 1
        else:
            continue
        candidates.append((priority, match, attributes))

    if not candidates:
        return
    highest_priority = max(priority for priority, _, _ in candidates)
    sources = [
        (match, attributes)
        for priority, match, attributes in candidates
        if priority == highest_priority
    ]
    source_ids = []
    id_insertions = []
    for index, (match, attributes) in enumerate(sources, start=1):
        element_id = attributes.get("id")
        if element_id is None:
            element_id = f"vapour-barrier-overlay-source-{index}"
            id_insertions.append((match.end() - 1, f' id="{element_id}"'))
        source_ids.append(element_id)

    for offset, identifier in reversed(id_insertions):
        svg = f"{svg[:offset]}{identifier}{svg[offset:]}"

    closing_svg = svg.rfind("</svg>")
    if closing_svg < 0:
        return
    uses = "\n".join(
        f'    <use href="#{element_id}" xlink:href="#{element_id}"/>'
        for element_id in source_ids
    )
    overlays = (
        '<g class="vapour-barrier-overlays '
        'target-view-ELEVATIONVIEW">\n'
        f"{uses}\n"
        "  </g>\n"
    )
    svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
    svg_path.write_text(svg, encoding="utf-8")


def _convex_hull_2d(
    points: set[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return the counter-clockwise convex hull of at least three 2D points."""
    ordered = sorted(points)
    if len(ordered) < 3:
        return []

    def cross(
        origin: tuple[float, float],
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> float:
        return (
            (first[0] - origin[0]) * (second[1] - origin[1])
            - (first[1] - origin[1]) * (second[0] - origin[0])
        )

    lower: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _section_shape_points(
    shape: object,
    *,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
    world_to_camera: np.ndarray,
) -> set[tuple[float, float]]:
    """Intersect a triangulated IFC shape with a camera section plane."""
    geometry = shape.geometry
    vertices = [
        np.array(geometry.verts[index : index + 3], dtype=float)
        for index in range(0, len(geometry.verts), 3)
    ]
    faces = [
        geometry.faces[index : index + 3]
        for index in range(0, len(geometry.faces), 3)
    ]
    tolerance = 1e-7
    points: set[tuple[float, float]] = set()
    for face in faces:
        triangle = [vertices[index] for index in face]
        distances = [
            float(np.dot(point - plane_origin, plane_normal))
            for point in triangle
        ]
        for first_index, second_index in ((0, 1), (1, 2), (2, 0)):
            first = triangle[first_index]
            second = triangle[second_index]
            first_distance = distances[first_index]
            second_distance = distances[second_index]
            intersections: list[np.ndarray] = []
            if abs(first_distance) <= tolerance:
                intersections.append(first)
            if abs(second_distance) <= tolerance:
                intersections.append(second)
            if first_distance * second_distance < -(tolerance * tolerance):
                fraction = first_distance / (first_distance - second_distance)
                intersections.append(first + fraction * (second - first))
            for intersection in intersections:
                camera_point = world_to_camera @ np.array(
                    (*intersection, 1.0), dtype=float
                )
                points.add(
                    (
                        round(float(camera_point[0]), 9),
                        round(float(camera_point[1]), 9),
                    )
                )
    return points


def _postprocess_elevation_opening_overlays(
    svg_path: Path,
    model: ifcopenshell.file,
    drawing: ifcopenshell.entity_instance,
) -> None:
    """Restore voids hidden by Bonsai's late elevation wall-layer fills."""
    svg = svg_path.read_text(encoding="utf-8")
    if '<g class="section-opening-overlays' in svg:
        return

    root = re.search(r"<svg\b(?P<attrs>[^>]*)>", svg)
    if root is None:
        return
    attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', root["attrs"]))
    try:
        view_box = tuple(
            float(value)
            for value in re.split(r"[,\s]+", attributes["viewBox"].strip())
        )
    except (KeyError, ValueError):
        return
    if len(view_box) != 4:
        return
    scale_match = re.fullmatch(
        r"\s*1\s*[:/]\s*(?P<denominator>[0-9]+(?:\.[0-9]+)?)\s*",
        attributes.get("data-scale", ""),
    )
    if scale_match is None:
        return
    scale_denominator = float(scale_match["denominator"])
    if scale_denominator <= 0:
        return
    svg_units_per_metre = 1000.0 / scale_denominator
    view_x, view_y, view_width, view_height = view_box
    view_center_x = view_x + view_width / 2
    view_center_y = view_y + view_height / 2

    camera_to_world = ifcopenshell.util.placement.get_local_placement(
        drawing.ObjectPlacement
    )
    world_to_camera = np.linalg.inv(camera_to_world)
    plane_origin = camera_to_world[:3, 3]
    plane_normal = camera_to_world[:3, 2]
    geometry_settings = ifcopenshell.geom.settings()
    geometry_settings.set(geometry_settings.USE_WORLD_COORDS, True)
    wall_ranges: dict[int, tuple[float, float] | None] = {}
    face_on_walls: dict[int, bool] = {}
    polygons: list[tuple[str, str, list[tuple[float, float]]]] = []
    tolerance = 1e-7
    face_on_dot_tolerance = sin(radians(5))

    for opening in model.by_type("IfcOpeningElement"):
        void_relationships = list(opening.VoidsElements or ())
        if not void_relationships:
            continue
        wall = void_relationships[0].RelatingBuildingElement
        if not wall.is_a("IfcWall"):
            continue
        wall_is_face_on = face_on_walls.get(wall.id())
        if wall_is_face_on is None:
            try:
                wall_placement = ifcopenshell.util.placement.get_local_placement(
                    wall.ObjectPlacement
                )
                wall_axis = wall_placement[:3, 0]
                wall_axis /= np.linalg.norm(wall_axis)
                wall_is_face_on = bool(
                    abs(float(np.dot(wall_axis, plane_normal)))
                    <= face_on_dot_tolerance
                )
            except (AttributeError, TypeError, ValueError):
                # This overlay is only a drawing repair.  If the wall axis is
                # unavailable, avoid risking a mask on an edge-on wall.
                wall_is_face_on = False
            face_on_walls[wall.id()] = wall_is_face_on
        if not wall_is_face_on:
            continue
        wall_range = wall_ranges.get(wall.id())
        if wall.id() not in wall_ranges:
            try:
                wall_shape = ifcopenshell.geom.create_shape(
                    geometry_settings, wall
                )
                wall_vertices = np.array(
                    wall_shape.geometry.verts, dtype=float
                ).reshape((-1, 3))
                wall_distances = (
                    (wall_vertices - plane_origin) @ plane_normal
                )
                wall_range = (
                    float(np.min(wall_distances)),
                    float(np.max(wall_distances)),
                )
            except (RuntimeError, ValueError):
                wall_range = None
            wall_ranges[wall.id()] = wall_range
        if (
            wall_range is None
            or wall_range[0] >= -tolerance
            or wall_range[1] <= tolerance
        ):
            # The wall is only projected, or the plane merely touches its face.
            continue
        try:
            opening_shape = ifcopenshell.geom.create_shape(
                geometry_settings, opening
            )
        except (RuntimeError, ValueError):
            continue
        section_points = _section_shape_points(
            opening_shape,
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            world_to_camera=world_to_camera,
        )
        hull = _convex_hull_2d(section_points)
        if not hull:
            continue
        svg_hull = [
            (
                view_center_x + x * svg_units_per_metre,
                view_center_y - y * svg_units_per_metre,
            )
            for x, y in hull
        ]
        if (
            max(x for x, _ in svg_hull) < view_x
            or min(x for x, _ in svg_hull) > view_x + view_width
            or max(y for _, y in svg_hull) < view_y
            or min(y for _, y in svg_hull) > view_y + view_height
        ):
            continue
        polygons.append((opening.GlobalId, opening.Name or "Opening", svg_hull))

    closing_svg = svg.rfind("</svg>")
    if not polygons or closing_svg < 0:
        return
    polygon_svg = "\n".join(
        (
            f'    <polygon class="section-opening-mask" '
            f'ifc:guid="{global_id}" ifc:name="{escape(name, quote=True)}" points="'
            + " ".join(f"{x:.6g},{y:.6g}" for x, y in points)
            + '"/>'
        )
        for global_id, name, points in polygons
    )
    overlays = (
        '<g class="section-opening-overlays target-view-ELEVATIONVIEW">\n'
        f"{polygon_svg}\n"
        "  </g>\n"
    )
    svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
    svg_path.write_text(svg, encoding="utf-8")


def _postprocess_projection_hull_fills(
    svg_path: Path,
    *,
    required_classes: set[str],
    fill_class: str,
) -> None:
    """Add a filled hull behind matching groups of open projection paths."""
    svg = svg_path.read_text(encoding="utf-8")
    if f'class="{fill_class}"' in svg:
        return

    simple_group = re.compile(
        r'(?P<open><g\b(?P<attrs>[^>]*)>)'
        r'(?P<body>(?:(?!<g\b).)*?)'
        r'(?P<close></g>)',
        re.DOTALL,
    )
    coordinate = re.compile(rf'({_SVG_NUMBER})[,\s]+({_SVG_NUMBER})')

    def add_fill(match: re.Match[str]) -> str:
        attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"]))
        classes = set(attributes.get("class", "").split())
        if not required_classes <= classes:
            return match.group(0)
        points: set[tuple[float, float]] = set()
        for path_data in re.findall(
            r'<path\b[^>]*\bd="([^"]+)"', match["body"]
        ):
            points.update(
                (float(x), float(y))
                for x, y in coordinate.findall(path_data)
            )
        hull = _convex_hull_2d(points)
        if not hull:
            return match.group(0)
        point_text = " ".join(f"{x:g},{y:g}" for x, y in hull)
        indentation = "  "
        indentation_match = re.match(r'\n([ \t]+)', match["body"])
        if indentation_match is not None:
            indentation = indentation_match.group(1)
        polygon = (
            f'\n{indentation}<polygon class="{fill_class}" '
            f'points="{point_text}"/>'
        )
        return (
            f'{match["open"]}{polygon}{match["body"]}{match["close"]}'
        )

    processed_svg = simple_group.sub(add_fill, svg)
    if processed_svg != svg:
        svg_path.write_text(processed_svg, encoding="utf-8")


def _postprocess_projected_wood_fills(svg_path: Path) -> None:
    """Add a filled hull behind open projected-wood edge paths in plans."""
    _postprocess_projection_hull_fills(
        svg_path,
        required_classes={"IfcBeam", "material-Wood", "projection"},
        fill_class="projected-wood-fill",
    )


def _postprocess_projected_chimney_fills(svg_path: Path) -> None:
    """Mask merged elevation surfaces behind projected chimney outlines."""
    _postprocess_projection_hull_fills(
        svg_path,
        required_classes={"IfcChimney", "projection"},
        fill_class="projected-chimney-fill",
    )


_DRAWING_PATTERN_IDS: frozenset[str] | None = None


def _drawing_pattern_ids() -> frozenset[str]:
    """Return pattern identifiers available to drawing material legends."""
    global _DRAWING_PATTERN_IDS
    if _DRAWING_PATTERN_IDS is None:
        patterns_path = (
            Path(__file__).resolve().parent
            / "drawings"
            / "assets"
            / "patterns.svg"
        )
        patterns = patterns_path.read_text(encoding="utf-8")
        _DRAWING_PATTERN_IDS = frozenset(
            re.findall(r'<pattern\s+id="([^"]+)"', patterns)
        )
    return _DRAWING_PATTERN_IDS


def _material_legend_svg(
    table: Mapping[str, object],
    *,
    x: float,
    y: float,
    width: float,
    units_per_mm: float,
    layout_scale: float | None = None,
) -> tuple[str, float]:
    """Return one material-legend SVG table and its height in SVG units."""
    title = str(table.get("title", "MATERIAL LEGEND"))
    supplied_items = table.get("items", [])
    items = supplied_items if isinstance(supplied_items, list) else []
    width_mm = width / units_per_mm
    # A 90 mm-wide table is the reference size.  Narrower panels scale the
    # whole legend uniformly instead of squeezing full-size text into them.
    if layout_scale is None:
        layout_scale = min(1.0, width_mm / 90.0)
    description_font_size_mm = 4.4 * layout_scale
    swatch_width_mm = 18.0 * layout_scale
    padding_mm = 2.0 * layout_scale
    header_height_mm = 12.0 * layout_scale
    line_height_mm = 5.4 * layout_scale
    minimum_row_height_mm = 12.0 * layout_scale
    normalised_items: list[tuple[str, list[str], float]] = []
    for supplied_item in items:
        if not isinstance(supplied_item, dict):
            continue
        pattern = str(supplied_item.get("pattern", ""))
        description = str(supplied_item.get("description", ""))
        lines = description.splitlines() or [""]
        row_height_mm = max(
            minimum_row_height_mm,
            2 * padding_mm + len(lines) * line_height_mm,
        )
        normalised_items.append((pattern, lines, row_height_mm))

    u = units_per_mm
    header_height = header_height_mm * u
    swatch_width = swatch_width_mm * u
    padding = padding_mm * u
    line_height = line_height_mm * u
    row_heights = [row_height_mm * u for _, _, row_height_mm in normalised_items]
    height = header_height + sum(row_heights)
    right = x + width
    header_bottom = y + header_height
    parts = [
        '<g class="right-panel-table material-legend">',
        (
            f'<rect class="right-panel-table-outline" x="{x:.6g}" '
            f'y="{y:.6g}" width="{width:.6g}" height="{height:.6g}"/>'
        ),
        (
            f'<text class="right-panel-table-title" x="{x + width / 2:.6g}" '
            f'y="{y + header_height / 2:.6g}" text-anchor="middle" '
            f'dominant-baseline="middle" '
            f'style="font-size:{5.5 * layout_scale:.6g}px">'
            f'{escape(title)}</text>'
        ),
        (
            f'<line class="right-panel-table-grid" x1="{x:.6g}" '
            f'y1="{header_bottom:.6g}" x2="{right:.6g}" '
            f'y2="{header_bottom:.6g}"/>'
        ),
    ]
    if normalised_items:
        swatch_right = x + swatch_width
        parts.append(
            f'<line class="right-panel-table-grid" x1="{swatch_right:.6g}" '
            f'y1="{header_bottom:.6g}" x2="{swatch_right:.6g}" '
            f'y2="{y + height:.6g}"/>'
        )

    row_y = header_bottom
    available_patterns = _drawing_pattern_ids()
    for (pattern, lines, _), row_height in zip(normalised_items, row_heights):
        fill = f"url(#{pattern})" if pattern in available_patterns else "white"
        parts.append(
            f'<rect class="material-legend-swatch" x="{x:.6g}" '
            f'y="{row_y:.6g}" width="{swatch_width:.6g}" '
            f'height="{row_height:.6g}" fill="{fill}"/>'
        )
        text_x = x + swatch_width + padding
        text_block_height = (len(lines) - 1) * line_height
        first_baseline = (
            row_y
            + (row_height - text_block_height) / 2
            + 1.35 * layout_scale * u
        )
        description_font_size = description_font_size_mm
        tspans = "".join(
            (
                f'<tspan x="{text_x:.6g}" '
                f'y="{first_baseline + index * line_height:.6g}" '
                f'style="font-size:{description_font_size:.6g}px">'
                f'{escape(line)}</tspan>'
            )
            for index, line in enumerate(lines)
        )
        parts.append(
            f'<text class="material-legend-description" '
            f'style="font-size:{description_font_size:.6g}px">'
            f'{tspans}</text>'
        )
        row_y += row_height
        if row_y < y + height - 1e-9:
            parts.append(
                f'<line class="right-panel-table-grid" x1="{x:.6g}" '
                f'y1="{row_y:.6g}" x2="{right:.6g}" y2="{row_y:.6g}"/>'
            )
    parts.append("</g>")
    return "\n    ".join(parts), height


def _postprocess_right_panel(
    svg_path: Path,
    drawing_properties: Mapping[str, object],
) -> None:
    """Expand a drawing sheet and append its persisted right-side tables."""
    try:
        panel_width_mm = float(drawing_properties.get("RightPanelWidth", 0))
    except (TypeError, ValueError):
        return
    if panel_width_mm <= 0:
        return

    svg = svg_path.read_text(encoding="utf-8")
    if 'class="right-side-panel"' in svg:
        return
    root = re.search(r"<svg\b(?P<attrs>[^>]*)>", svg)
    if root is None:
        return
    attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', root["attrs"]))
    try:
        view_x, view_y, view_width, view_height = (
            float(value)
            for value in re.split(r"[,\s]+", attributes["viewBox"].strip())
        )
    except (KeyError, TypeError, ValueError):
        return
    width_match = re.fullmatch(
        rf"\s*(?P<value>{_SVG_NUMBER})mm\s*",
        attributes.get("width", ""),
    )
    if width_match is None:
        return
    physical_width_mm = float(width_match["value"])
    if physical_width_mm <= 0 or view_width <= 0:
        return
    units_per_mm = view_width / physical_width_mm
    panel_width = panel_width_mm * units_per_mm
    horizontal_margin_mm = 2.0
    vertical_margin_mm = 5.0
    horizontal_margin = horizontal_margin_mm * units_per_mm
    vertical_margin = vertical_margin_mm * units_per_mm
    table_gap = 5.0 * units_per_mm
    panel_x = view_x + view_width
    table_x = panel_x + horizontal_margin
    table_width = panel_width - 2 * horizontal_margin
    legend_scale = min(
        1.0,
        max(0.0, (panel_width_mm - 10.0) / 90.0),
    )

    try:
        tables = json.loads(
            str(drawing_properties.get("RightPanelTables", "[]"))
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        tables = []
    if not isinstance(tables, list):
        tables = []
    table_y = view_y + vertical_margin
    table_parts = []
    for table in tables:
        if not isinstance(table, dict) or table.get("kind") != "material_legend":
            continue
        table_svg, table_height = _material_legend_svg(
            table,
            x=table_x,
            y=table_y,
            width=table_width,
            units_per_mm=units_per_mm,
            layout_scale=legend_scale,
        )
        table_parts.append(table_svg)
        table_y += table_height + table_gap

    required_height = (
        table_y - table_gap + vertical_margin
        if table_parts
        else view_y + view_height
    )
    new_view_height = max(view_height, required_height - view_y)
    new_physical_height_mm = new_view_height / units_per_mm
    new_physical_width_mm = physical_width_mm + panel_width_mm
    new_view_width = view_width + panel_width

    updated_root = root.group(0)
    updated_root = re.sub(
        r'\bwidth="[^"]*"',
        f'width="{new_physical_width_mm:g}mm"',
        updated_root,
        count=1,
    )
    updated_root = re.sub(
        r'\bheight="[^"]*"',
        f'height="{new_physical_height_mm:g}mm"',
        updated_root,
        count=1,
    )
    updated_root = re.sub(
        r'\bviewBox="[^"]*"',
        f'viewBox="{view_x:g} {view_y:g} {new_view_width:g} {new_view_height:g}"',
        updated_root,
        count=1,
    )
    svg = f"{svg[:root.start()]}{updated_root}{svg[root.end():]}"

    closing_svg = svg.rfind("</svg>")
    if closing_svg < 0:
        return
    tables_svg = "\n    ".join(table_parts)
    panel = (
        '  <g class="right-side-panel">\n'
        f'    <rect class="right-side-panel-background" x="{panel_x:.6g}" '
        f'y="{view_y:.6g}" width="{panel_width:.6g}" '
        f'height="{new_view_height:.6g}"/>\n'
        f'    <line class="right-side-panel-separator" x1="{panel_x:.6g}" '
        f'y1="{view_y:.6g}" x2="{panel_x:.6g}" '
        f'y2="{view_y + new_view_height:.6g}"/>\n'
        f'    {tables_svg}\n'
        "  </g>\n"
    )
    svg = f"{svg[:closing_svg]}{panel}{svg[closing_svg:]}"
    svg_path.write_text(svg, encoding="utf-8")


def _postprocess_door_overheads(
    svg_path: Path,
    *,
    mask_global_ids: set[str] | None = None,
) -> None:
    """Apply the final wall, reinforcement, symbol, and label drawing order."""
    _postprocess_miako_reinforcement_overlays(svg_path)
    svg = svg_path.read_text(encoding="utf-8")
    changed = False

    def center_dimension_label(match: re.Match[str]) -> str:
        nonlocal changed
        attributes = dict(
            re.findall(r'([\w:-]+)="([^"]*)"', match["line_attrs"])
        )
        try:
            start_x, start_y, end_x, end_y = (
                float(attributes[name]) for name in ("x1", "y1", "x2", "y2")
            )
        except (KeyError, ValueError):
            return match.group(0)
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        squared_length = delta_x * delta_x + delta_y * delta_y
        if squared_length == 0:
            return match.group(0)
        midpoint_x = (start_x + end_x) / 2
        midpoint_y = (start_y + end_y) / 2
        text_x = float(match["text_x"])
        text_y = float(match["text_y"])
        along_line = (
            (text_x - midpoint_x) * delta_x
            + (text_y - midpoint_y) * delta_y
        ) / squared_length
        if abs(along_line) <= 1e-12:
            return match.group(0)
        centered_x = text_x - along_line * delta_x
        centered_y = text_y - along_line * delta_y
        changed = True
        return (
            f'{match["prefix"]}{centered_x:.12g}, {centered_y:.12g}'
            f'{match["suffix"]}'
        )

    svg = _DIMENSION_LABEL.sub(center_dimension_label, svg)

    if '<polygon class="door-overhead-mask"' not in svg:
        line_groups: dict[str, list[re.Match[str]]] = {}
        for match in _DOOR_OVERHEAD_LINE.finditer(svg):
            attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"]))
            global_id = next(
                (
                    token
                    for token in attributes.get("class", "").split()
                    if token.startswith("GlobalId-")
                ),
                None,
            )
            if global_id is not None:
                if (
                    mask_global_ids is not None
                    and global_id.removeprefix("GlobalId-") not in mask_global_ids
                ):
                    continue
                line_groups.setdefault(global_id, []).append(match)

        insertions = []
        for lines in line_groups.values():
            if len(lines) != 2:
                continue
            first = dict(re.findall(r'([\w:-]+)="([^"]*)"', lines[0]["attrs"]))
            second = dict(re.findall(r'([\w:-]+)="([^"]*)"', lines[1]["attrs"]))
            coordinate_names = ("x1", "y1", "x2", "y2")
            if any(
                name not in first or name not in second
                for name in coordinate_names
            ):
                continue
            points = " ".join(
                (
                    f'{first["x1"]},{first["y1"]}',
                    f'{first["x2"]},{first["y2"]}',
                    f'{second["x2"]},{second["y2"]}',
                    f'{second["x1"]},{second["y1"]}',
                )
            )
            polygon = (
                f'{lines[0]["indent"]}<polygon class="door-overhead-mask" '
                f'points="{points}"/>\n'
            )
            insertions.append((lines[0].start(), polygon))

        for offset, polygon in reversed(insertions):
            svg = f"{svg[:offset]}{polygon}{svg[offset:]}"
        changed = changed or bool(insertions)

    if '<g class="door-dimension-overlays">' not in svg:
        separators = [
            match.group(0).strip()
            for match in re.finditer(
                r"^[ \t]*<line\b[^>\n]*\bdoor-dimension-separator\b[^>\n]*/>[ \t]*$",
                svg,
                re.MULTILINE,
            )
        ]
        closing_svg = svg.rfind("</svg>")
        if separators and closing_svg >= 0:
            lines = "\n".join(f"    {separator}" for separator in separators)
            overlays = (
                '  <g class="door-dimension-overlays">\n'
                f"{lines}\n"
                "  </g>\n"
            )
            svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
            changed = True

    if '<g class="door-symbol-overlays">' not in svg:
        door_ids = []
        for match in re.finditer(r'<g\b(?P<attrs>[^>\n]*)>', svg):
            attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"]))
            classes = set(attributes.get("class", "").split())
            element_id = attributes.get("id")
            if element_id and {"IfcDoor", "projection"} <= classes:
                door_ids.append(element_id)
        closing_svg = svg.rfind("</svg>")
        if door_ids and closing_svg >= 0:
            uses = "\n".join(
                f'    <use href="#{element_id}" xlink:href="#{element_id}"/>'
                for element_id in door_ids
            )
            overlays = (
                '  <g class="door-symbol-overlays">\n'
                f"{uses}\n"
                "  </g>\n"
            )
            svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
            changed = True

    if '<g class="furniture-symbol-overlays">' not in svg:
        furniture_ids = []
        furniture_classes = {
            "IfcFurniture",
            "IfcSanitaryTerminal",
            "IfcElectricAppliance",
        }
        for match in re.finditer(r'<g\b(?P<attrs>[^>\n]*)>', svg):
            attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"]))
            classes = set(attributes.get("class", "").split())
            element_id = attributes.get("id")
            if (
                element_id
                and furniture_classes & classes
                and {"projection", "cut"} & classes
            ):
                furniture_ids.append(element_id)
        closing_svg = svg.rfind("</svg>")
        if furniture_ids and closing_svg >= 0:
            uses = "\n".join(
                f'    <use href="#{element_id}" xlink:href="#{element_id}"/>'
                for element_id in furniture_ids
            )
            overlays = (
                '  <g class="furniture-symbol-overlays">\n'
                f"{uses}\n"
                "  </g>\n"
            )
            svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
            changed = True

    if '<g class="furniture-label-overlays">' not in svg:
        furniture_labels = [
            match.group(0).strip()
            for match in re.finditer(r"<text\b[^>]*>.*?</text>", svg, re.DOTALL)
            if "furniture-label" in match.group(0)
        ]
        closing_svg = svg.rfind("</svg>")
        if furniture_labels and closing_svg >= 0:
            labels = "\n".join(
                "    " + label.replace("\n", "\n    ")
                for label in furniture_labels
            )
            overlays = (
                '  <g class="furniture-label-overlays">\n'
                f"{labels}\n"
                "  </g>\n"
            )
            svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
            changed = True

    if changed:
        svg_path.write_text(svg, encoding="utf-8")


BeamKind: TypeAlias = Literal[
    "BEAM",
    "JOIST",
    "HOLLOWCORE",
    "LINTEL",
    "SPANDREL",
    "T_BEAM",
    "RAFTER",
    "PURLIN",
    "USERDEFINED",
    "NOTDEFINED",
]
MiakoStructureItem: TypeAlias = Literal["beam", "wide", "narrow"]

_COLOR_NAMES = {
    "black": "#000000",
    "blue": "#0000FF",
    "brown": "#A52A2A",
    "gray": "#808080",
    "grey": "#808080",
    "green": "#008000",
    "orange": "#FFA500",
    "red": "#FF0000",
    "white": "#FFFFFF",
    "yellow": "#FFFF00",
}

_DOOR_OPERATIONS = {
    "SINGLE_SWING_LEFT",
    "SINGLE_SWING_RIGHT",
    "DOUBLE_SWING_RIGHT",
    "DOUBLE_SWING_LEFT",
    "DOUBLE_DOOR_SINGLE_SWING",
    "DOUBLE_DOOR_DOUBLE_SWING",
    "SLIDING_TO_LEFT",
    "SLIDING_TO_RIGHT",
    "DOUBLE_DOOR_SLIDING",
}
_WINDOW_PARTITIONS = {
    "SINGLE_PANEL",
    "DOUBLE_PANEL_HORIZONTAL",
    "DOUBLE_PANEL_VERTICAL",
    "TRIPLE_PANEL_BOTTOM",
    "TRIPLE_PANEL_TOP",
    "TRIPLE_PANEL_LEFT",
    "TRIPLE_PANEL_RIGHT",
    "TRIPLE_PANEL_HORIZONTAL",
    "TRIPLE_PANEL_VERTICAL",
}
_WINDOW_ALIGNMENTS = {"AXIS", "INSIDE"}
_FURNITURE_KINDS = {
    "CHAIR",
    "TABLE",
    "DESK",
    "BED",
    "FILECABINET",
    "SHELF",
    "SOFA",
    "USERDEFINED",
    "NOTDEFINED",
}
_BEAM_KINDS = {
    "BEAM",
    "JOIST",
    "HOLLOWCORE",
    "LINTEL",
    "SPANDREL",
    "T_BEAM",
    "RAFTER",
    "PURLIN",
    "USERDEFINED",
    "NOTDEFINED",
}
_MIAKO_WIDTHS = {
    "beam": 0.17,
    "wide": 0.455,
    "narrow": 0.33,
}


def _name(value: str, argument: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{argument} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{argument} must not be empty")
    return value


def _number(value: Number, argument: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{argument} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{argument} must be a number") from error
    if not isfinite(result):
        raise ValueError(f"{argument} must be finite")
    return result


def _point(value: Point, argument: str) -> tuple[float, float]:
    try:
        x, y = value
    except (TypeError, ValueError) as error:
        raise TypeError(f"{argument} must contain exactly two coordinates") from error
    return _number(x, f"{argument} x"), _number(y, f"{argument} y")


def _point_3d(value: Point3D, argument: str) -> tuple[float, float, float]:
    try:
        x, y, z = value
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{argument} must contain exactly three coordinates"
        ) from error
    return (
        _number(x, f"{argument} x"),
        _number(y, f"{argument} y"),
        _number(z, f"{argument} z"),
    )


def offset_plane(
    point_1: Point3D,
    point_2: Point3D,
    point_3: Point3D,
    offset: Number,
) -> PlaneCut:
    """Shift a three-point plane along its upward-facing unit normal.

    Positive offsets move towards positive global Z and negative offsets move
    in the opposite direction.  Vertical planes are rejected because neither
    perpendicular direction points upwards.
    """
    points = np.array(
        (
            _point_3d(point_1, "point_1"),
            _point_3d(point_2, "point_2"),
            _point_3d(point_3, "point_3"),
        ),
        dtype=float,
    )
    offset = _number(offset, "offset")
    normal = np.cross(points[1] - points[0], points[2] - points[0])
    normal_length = float(np.linalg.norm(normal))
    if normal_length <= 1e-9:
        raise ValueError("plane points must not be collinear")
    normal /= normal_length
    if abs(float(normal[2])) <= 1e-9:
        raise ValueError("plane must not be vertical")
    if normal[2] < 0:
        normal *= -1
    shifted_points = points + normal * offset
    return tuple(
        tuple(float(coordinate) for coordinate in point)
        for point in shifted_points
    )


def _plane_cuts(
    value: Sequence[PlaneCut] | None,
    argument: str = "cuts",
) -> tuple[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
    ...,
]:
    """Validate global three-point clipping planes without choosing a side."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{argument} must be a sequence of three-point planes")
    try:
        supplied_cuts = list(value)
    except TypeError as error:
        raise TypeError(
            f"{argument} must be a sequence of three-point planes"
        ) from error

    result = []
    for cut_index, supplied_cut in enumerate(supplied_cuts, start=1):
        if isinstance(supplied_cut, (str, bytes)):
            raise TypeError(f"cut {cut_index} must contain exactly three points")
        try:
            supplied_points = list(supplied_cut)
        except TypeError as error:
            raise TypeError(
                f"cut {cut_index} must contain exactly three points"
            ) from error
        if len(supplied_points) != 3:
            raise TypeError(f"cut {cut_index} must contain exactly three points")
        points = tuple(
            _point_3d(point, f"cut {cut_index} point {point_index}")
            for point_index, point in enumerate(supplied_points, start=1)
        )
        normal = np.cross(
            np.array(points[1], dtype=float) - np.array(points[0], dtype=float),
            np.array(points[2], dtype=float) - np.array(points[0], dtype=float),
        )
        if float(np.linalg.norm(normal)) <= 1e-9:
            raise ValueError(f"cut {cut_index} points must not be collinear")
        result.append(points)
    return tuple(result)


def _local_clippings(
    cuts: Sequence[PlaneCut],
    placement: np.ndarray,
    retained_point: Sequence[Number],
) -> list[dict[str, tuple[float, float, float]]]:
    """Convert global planes to a product frame, retaining its centre side."""
    world_to_local = np.linalg.inv(placement)
    retained_point_vector = np.array(retained_point, dtype=float)
    result = []
    for cut_index, cut in enumerate(cuts, start=1):
        local_points = [
            (world_to_local @ np.array((*point, 1.0), dtype=float))[:3]
            for point in cut
        ]
        normal = np.cross(
            local_points[1] - local_points[0],
            local_points[2] - local_points[0],
        )
        normal /= np.linalg.norm(normal)
        centre_side = float(
            np.dot(normal, retained_point_vector - local_points[0])
        )
        if abs(centre_side) <= 1e-9:
            raise ValueError(
                f"cut {cut_index} passes through the element centre; "
                "the retained side is ambiguous"
            )
        if centre_side > 0:
            normal *= -1
        result.append(
            {
                "location": tuple(float(value) for value in local_points[0]),
                "normal": tuple(float(value) for value in normal),
            }
        )
    return result


def _clip_body_representation(
    model: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    body: ifcopenshell.entity_instance,
    clippings: Sequence[dict[str, tuple[float, float, float]]],
) -> None:
    """Apply ordered half-space cuts and persist their boolean identifiers."""
    if not clippings:
        return
    item = body.Items[0]
    clipping_ids = []
    for clipping in clippings:
        item = ifcopenshell.api.geometry.clip_solid(
            model,
            item=item,
            location=clipping["location"],
            normal=clipping["normal"],
        )
        clipping_ids.append(item.id())
    body.Items = [item]
    body.RepresentationType = "Clipping"
    boolean_pset = ifcopenshell.api.pset.add_pset(
        model,
        product=element,
        name="BBIM_Boolean",
    )
    ifcopenshell.api.pset.edit_pset(
        model,
        pset=boolean_pset,
        properties={"Data": json.dumps(clipping_ids)},
    )


def _enum(value: str, argument: str, allowed: set[str]) -> str:
    value = _name(value, argument).upper()
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{argument} must be one of: {choices}")
    return value


def _color(value: str, argument: str) -> tuple[float, float, float]:
    value = _name(value, argument)
    value = _COLOR_NAMES.get(value.lower(), value)
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if len(value) != 6:
        raise ValueError(f"{argument} must be a named color or #RGB/#RRGGBB")
    try:
        channels = tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
    except ValueError as error:
        raise ValueError(
            f"{argument} must be a named color or #RGB/#RRGGBB"
        ) from error
    return channels


def _rotate_items_about_z(
    model: ifcopenshell.file,
    items: Sequence[ifcopenshell.entity_instance],
    *,
    angle: float,
    pivot: tuple[float, float],
) -> None:
    """Rigidly rotate positioned representation items in their local XY plane."""
    angle = radians(angle)
    rotation = np.eye(4)
    rotation[0, 0] = cos(angle)
    rotation[0, 1] = -sin(angle)
    rotation[1, 0] = sin(angle)
    rotation[1, 1] = cos(angle)
    to_pivot = np.eye(4)
    to_pivot[0, 3], to_pivot[1, 3] = pivot
    from_pivot = np.eye(4)
    from_pivot[0, 3], from_pivot[1, 3] = -pivot[0], -pivot[1]
    transform = to_pivot @ rotation @ from_pivot

    for item in items:
        position = getattr(item, "Position", None)
        if position is None or not position.is_a("IfcAxis2Placement3D"):
            raise TypeError(f"cannot rotate unpositioned {item.is_a()} door geometry")
        placement = transform @ ifcopenshell.util.placement.get_axis2placement(position)
        position.Location.Coordinates = tuple(float(value) for value in placement[:3, 3])
        position.Axis = model.createIfcDirection(
            tuple(float(value) for value in placement[:3, 2])
        )
        position.RefDirection = model.createIfcDirection(
            tuple(float(value) for value in placement[:3, 0])
        )


def _rotate_door_framing(
    model: ifcopenshell.file,
    door: ifcopenshell.entity_instance,
    *,
    operation: str,
    angle: float,
    reverse_swing: bool,
    width: float,
    panel_offset_x: float,
    pivot_y: float,
) -> None:
    """Rotate the movable 3D framing items of ``door`` around their hinges."""
    if angle == 0 or "SLIDING" in operation:
        return

    framing = next(
        (
            aspect
            for aspect in door.Representation.HasShapeAspects
            if aspect.Name == "Framing"
        ),
        None,
    )
    if framing is None:
        raise RuntimeError(f'door "{door.Name or door.GlobalId}" has no framing')
    items = [
        item
        for representation in framing.ShapeRepresentations
        if representation.ContextOfItems.ContextType == "Model"
        and representation.ContextOfItems.ContextIdentifier == "Body"
        and representation.ContextOfItems.TargetView == "MODEL_VIEW"
        for item in representation.Items
    ]
    if not items:
        raise RuntimeError(
            f'door "{door.Name or door.GlobalId}" has no 3D framing geometry'
        )

    swing_sign = -1 if reverse_swing else 1
    if operation.startswith("DOUBLE_DOOR"):
        half = len(items) // 2
        _rotate_items_about_z(
            model,
            items[:half],
            angle=swing_sign * angle,
            pivot=(panel_offset_x, pivot_y),
        )
        _rotate_items_about_z(
            model,
            items[half:],
            angle=-swing_sign * angle,
            pivot=(width - panel_offset_x, pivot_y),
        )
    else:
        is_left_hinged = operation.endswith("LEFT")
        _rotate_items_about_z(
            model,
            items,
            angle=(
                swing_sign * angle
                if is_left_hinged
                else -swing_sign * angle
            ),
            pivot=(
                panel_offset_x if is_left_hinged else width - panel_offset_x,
                pivot_y,
            ),
        )


def _close_door_bodies(model: ifcopenshell.file) -> int:
    """Undo stored door opening rotations and return the number closed."""
    closed = 0
    for door in model.by_type("IfcDoor"):
        properties = ifcopenshell.util.element.get_pset(door, "EPset_Door")
        if not properties:
            continue
        try:
            open_angle = float(properties["OpenAngle"])
            reverse_swing = bool(properties["ReverseSwing"])
            panel_offset_x = float(properties["PanelOffsetX"])
            pivot_y = float(properties["BodyPivotY"])
        except (KeyError, TypeError, ValueError):
            continue
        operation = door.OperationType or "NOTDEFINED"
        if open_angle == 0 or "SLIDING" in operation:
            continue
        _rotate_door_framing(
            model,
            door,
            operation=operation,
            angle=-open_angle,
            reverse_swing=reverse_swing,
            width=float(door.OverallWidth),
            panel_offset_x=panel_offset_x,
            pivot_y=pivot_y,
        )
        closed += 1
    return closed


def generate_plan(
    ifc: str | PathLike[str],
    output: str | PathLike[str],
    *,
    x: Number,
    y: Number,
    z: Number,
    radius: Number,
    png: bool = False,
    blender: str | PathLike[str] = "blender",
    inkscape: str | PathLike[str] = "inkscape",
    stylesheet: str | PathLike[str] | None = None,
) -> Path:
    """Generate a square Bonsai plan from an IFC file.

    ``z`` is the horizontal cut-plane elevation.  The orthographic camera is
    centred on ``(x, y, z)`` and covers ``2 * radius`` metres in both X and Y.
    Set ``png=True`` to rasterise the resulting SVG with Inkscape as a second
    output.

    Bonsai's drawing operators currently require a live 3D viewport.  Blender
    therefore runs with its normal interface, performs the drawing unattended,
    and closes itself when finished.
    """
    ifc_path = Path(ifc).resolve()
    if not ifc_path.exists():
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")
    if not ifc_path.is_file():
        raise IsADirectoryError(f"IFC input is not a file: {ifc_path}")

    output_path = Path(output)
    if output_path.suffix.lower() != ".svg":
        raise ValueError("plan output must use the .svg extension")
    x = _number(x, "x")
    y = _number(y, "y")
    z = _number(z, "z")
    radius = _number(radius, "radius")
    if radius <= 0:
        raise ValueError("radius must be greater than zero")
    if not isinstance(png, bool):
        raise TypeError("png must be a boolean")

    blender_command = shutil.which(str(blender))
    if blender_command is None:
        raise FileNotFoundError(f"Blender executable not found: {blender}")

    script_path = Path(__file__).resolve().parent / "bonsai_scripts" / "generate_plan.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"Bonsai plan script not found: {script_path}")
    stylesheet_path = (
        Path(stylesheet)
        if stylesheet is not None
        else script_path.parent / "assets" / "plan.css"
    ).resolve()
    if not stylesheet_path.is_file():
        raise FileNotFoundError(f"plan stylesheet not found: {stylesheet_path}")

    absolute_output = output_path.resolve()
    absolute_output.parent.mkdir(parents=True, exist_ok=True)
    if absolute_output.exists():
        if not absolute_output.is_file():
            raise IsADirectoryError(f"plan output is not a file: {absolute_output}")
        absolute_output.unlink()

    command = [
        blender_command,
        "--python-exit-code",
        "1",
        "--python",
        str(script_path),
        "--",
        "--ifc",
        str(ifc_path),
        "--output",
        str(absolute_output),
        "--stylesheet",
        str(stylesheet_path),
        "--x",
        str(x),
        "--y",
        str(y),
        "--z",
        str(z),
        "--radius",
        str(radius),
    ]
    subprocess.run(command, check=True)

    if not absolute_output.is_file() or absolute_output.stat().st_size == 0:
        raise RuntimeError(f"Bonsai did not create the SVG plan: {absolute_output}")
    model = ifcopenshell.open(str(ifc_path))
    _postprocess_door_overheads(
        absolute_output,
        mask_global_ids=_overhead_mask_global_ids(model, z),
    )

    if png:
        inkscape_command = shutil.which(str(inkscape))
        if inkscape_command is None:
            raise FileNotFoundError(f"Inkscape executable not found: {inkscape}")
        png_output = absolute_output.with_suffix(".png")
        if png_output.exists():
            if not png_output.is_file():
                raise IsADirectoryError(f"PNG output is not a file: {png_output}")
            png_output.unlink()
        subprocess.run(
            [
                inkscape_command,
                str(absolute_output),
                f"--export-filename={png_output}",
                "--export-dpi=200",
                "--export-background=white",
                "--export-background-opacity=255",
            ],
            check=True,
        )
        if not png_output.is_file() or png_output.stat().st_size == 0:
            raise RuntimeError(f"Inkscape did not create the PNG plan: {png_output}")

    return output_path


def _render_existing_drawing(
    ifc: Path,
    drawing_guid: str,
    output: str | PathLike[str],
    *,
    png: bool,
    png_dpi: Number,
    blender: str | PathLike[str],
    inkscape: str | PathLike[str],
) -> Path:
    """Render a persisted Bonsai drawing from an IFC file."""
    output_path = Path(output)
    if output_path.suffix.lower() != ".svg":
        raise ValueError("drawing output must use the .svg extension")
    if not isinstance(png, bool):
        raise TypeError("png must be a boolean")
    png_dpi = _number(png_dpi, "png_dpi")
    if png_dpi <= 0:
        raise ValueError("png_dpi must be greater than zero")

    blender_command = shutil.which(str(blender))
    if blender_command is None:
        raise FileNotFoundError(f"Blender executable not found: {blender}")
    script_path = Path(__file__).resolve().parent / "bonsai_scripts" / "render_drawing.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"Bonsai drawing script not found: {script_path}")

    absolute_output = output_path.resolve()
    absolute_output.parent.mkdir(parents=True, exist_ok=True)
    if absolute_output.exists():
        if not absolute_output.is_file():
            raise IsADirectoryError(f"drawing output is not a file: {absolute_output}")
        absolute_output.unlink()

    model = ifcopenshell.open(str(ifc))
    drawing = model.by_guid(drawing_guid)
    drawing_properties = ifcopenshell.util.element.get_pset(
        drawing,
        "EPset_Drawing",
    )
    target_view = drawing_properties.get("TargetView") if drawing_properties else None
    render_ifc = Path(ifc).resolve()
    temporary_directory: TemporaryDirectory[str] | None = None
    if target_view == "ELEVATION_VIEW" and bool(
        drawing_properties.get("DoorsClosed", False)
    ):
        temporary_directory = TemporaryDirectory(prefix="ifc-closed-doors-")
        render_ifc = Path(temporary_directory.name) / Path(ifc).name
        closed_doors = _close_door_bodies(model)
        model.write(str(render_ifc))
        print(
            f"[drawing render] Closed {closed_doors} door bodies in temporary "
            f"elevation model",
            flush=True,
        )

    command = [
        blender_command,
        "--python-exit-code",
        "1",
        "--python",
        str(script_path),
        "--",
        "--ifc",
        str(render_ifc),
        "--drawing-guid",
        drawing_guid,
        "--output",
        str(absolute_output),
    ]
    print(
        f"[drawing render] Launching Blender/Bonsai for {drawing_guid}; "
        f"output={absolute_output}",
        flush=True,
    )
    render_started_at = monotonic()
    try:
        result = subprocess.run(command, check=True)
    except BaseException:
        print(
            f"[drawing render] Blender/Bonsai aborted after "
            f"{monotonic() - render_started_at:.2f}s",
            flush=True,
        )
        raise
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()
    print(
        f"[drawing render] Blender/Bonsai exited with code "
        f"{result.returncode} after {monotonic() - render_started_at:.2f}s",
        flush=True,
    )
    if not absolute_output.is_file() or absolute_output.stat().st_size == 0:
        raise RuntimeError(f"Bonsai did not create the SVG drawing: {absolute_output}")
    if target_view == "PLAN_VIEW":
        cut_z = float(
            ifcopenshell.util.placement.get_local_placement(
                drawing.ObjectPlacement
            )[2, 3]
        )
        _postprocess_projected_wood_fills(absolute_output)
        _postprocess_door_overheads(
            absolute_output,
            mask_global_ids=_overhead_mask_global_ids(model, cut_z),
        )
    else:
        _postprocess_projected_chimney_fills(absolute_output)
        _postprocess_elevation_opening_overlays(
            absolute_output,
            model,
            drawing,
        )
        _postprocess_miako_reinforcement_overlays(absolute_output)
        _postprocess_vapour_barrier_overlays(absolute_output)
    _postprocess_right_panel(
        absolute_output,
        drawing_properties or {},
    )

    if png:
        inkscape_command = shutil.which(str(inkscape))
        if inkscape_command is None:
            raise FileNotFoundError(f"Inkscape executable not found: {inkscape}")
        png_output = absolute_output.with_suffix(".png")
        if png_output.exists():
            if not png_output.is_file():
                raise IsADirectoryError(f"PNG output is not a file: {png_output}")
        with TemporaryDirectory(
            prefix=f".{png_output.stem}-raster-",
            dir=png_output.parent,
        ) as raster_directory:
            temporary_png = Path(raster_directory) / png_output.name
            subprocess.run(
                [
                    inkscape_command,
                    str(absolute_output),
                    f"--export-filename={temporary_png}",
                    f"--export-dpi={png_dpi:g}",
                    "--export-area-page",
                    "--batch-process",
                    "--export-background=white",
                    "--export-background-opacity=255",
                ],
                check=True,
            )
            if not temporary_png.is_file() or temporary_png.stat().st_size == 0:
                raise RuntimeError(
                    f"Inkscape did not create the PNG drawing: {png_output}"
                )
            png_size = temporary_png.stat().st_size
            temporary_png.replace(png_output)
        print(
            f"[drawing render] Inkscape PNG created: {png_output} "
            f"({png_size} bytes)",
            flush=True,
        )

    return output_path


class House:
    """An IFC project containing one site and one building.

    All public coordinates and dimensions are expressed in metres.  The
    underlying IFC file also uses metres, which keeps generated values easy to
    inspect while remaining compatible with IFC viewers such as Bonsai.
    ``colors`` may define default 3D colors for ``"beam"``, ``"block"``,
    ``"chimney"``, ``"wall"``, ``"door"``, ``"furniture"`, ``"slab"``,
    ``"stair"``, and ``"window"`` elements using named colors or
    ``#RGB``/``#RRGGBB`` values.  ``asset_library`` may override the
    automatically discovered Bonsai furniture-library IFC path.
    """

    def __init__(
        self,
        name: str,
        *,
        colors: Mapping[str, str] | None = None,
        asset_library: str | PathLike[str] | None = None,
    ) -> None:
        self.name = _name(name, "name")
        if colors is None:
            colors = {}
        elif not isinstance(colors, Mapping):
            raise TypeError("colors must be a mapping")
        allowed_colors = {
            "beam",
            "block",
            "chimney",
            "wall",
            "door",
            "furniture",
            "slab",
            "stair",
            "window",
        }
        self._default_colors: dict[str, tuple[float, float, float]] = {}
        for category, color in colors.items():
            if not isinstance(category, str):
                raise TypeError("color category names must be strings")
            category = category.strip().lower()
            if category not in allowed_colors:
                choices = ", ".join(sorted(allowed_colors))
                raise ValueError(f"color category must be one of: {choices}")
            self._default_colors[category] = _color(color, f"{category} color")
        self.model = ifcopenshell.api.project.create_file(version="IFC4")

        self.project = ifcopenshell.api.root.create_entity(
            self.model, ifc_class="IfcProject", name=self.name
        )
        units = [
            ifcopenshell.api.unit.add_si_unit(
                self.model, unit_type="LENGTHUNIT"
            ),
            ifcopenshell.api.unit.add_si_unit(self.model, unit_type="AREAUNIT"),
            ifcopenshell.api.unit.add_si_unit(self.model, unit_type="VOLUMEUNIT"),
        ]
        ifcopenshell.api.unit.assign_unit(self.model, units=units)

        model_context = ifcopenshell.api.context.add_context(
            self.model, context_type="Model"
        )
        self._body_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=model_context,
        )
        plan_context = ifcopenshell.api.context.add_context(
            self.model, context_type="Plan"
        )
        self._axis_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Plan",
            context_identifier="Axis",
            target_view="GRAPH_VIEW",
            parent=plan_context,
        )
        self._plan_body_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Plan",
            context_identifier="Body",
            target_view="PLAN_VIEW",
            parent=plan_context,
        )
        self._annotation_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Plan",
            context_identifier="Annotation",
            target_view="PLAN_VIEW",
            parent=plan_context,
        )

        self.site = ifcopenshell.api.root.create_entity(
            self.model, ifc_class="IfcSite", name="Site"
        )
        self.building = ifcopenshell.api.root.create_entity(
            self.model, ifc_class="IfcBuilding", name=self.name
        )
        ifcopenshell.api.aggregate.assign_object(
            self.model, products=[self.site], relating_object=self.project
        )
        ifcopenshell.api.aggregate.assign_object(
            self.model, products=[self.building], relating_object=self.site
        )
        ifcopenshell.api.geometry.edit_object_placement(
            self.model, product=self.site
        )
        ifcopenshell.api.geometry.edit_object_placement(
            self.model, product=self.building
        )

        self._storeys: list[Storey] = []
        self._drawings: list[Drawing] = []
        self._plan_annotations: list[ifcopenshell.entity_instance] = []
        self._materials: dict[str, ifcopenshell.entity_instance] = {}
        self._wall_type_layouts: dict[int, tuple[float, float]] = {}
        self._wall_type_styles: dict[int, ifcopenshell.entity_instance | None] = {}
        self._horizontal_frame_count = 0
        self._vertical_frame_count = 0
        self._facade_layer_count = 0
        self._surface_styles: dict[
            tuple[tuple[float, float, float], float],
            ifcopenshell.entity_instance,
        ] = {}
        self._miako_component_types: dict[
            tuple[object, ...], ifcopenshell.entity_instance
        ] = {}
        self._ifc_path: Path | None = None
        self.assets = AssetCatalog(self, asset_library)

    def _surface_style(
        self,
        category: Literal[
            "beam",
            "block",
            "chimney",
            "wall",
            "door",
            "furniture",
            "slab",
            "stair",
            "window",
        ],
        *,
        color: str | None,
        transparency: Number,
    ) -> ifcopenshell.entity_instance | None:
        transparency = _number(transparency, "transparency")
        if not 0 <= transparency <= 1:
            raise ValueError("transparency must be between 0 and 1")
        rgb = self._default_colors.get(category) if color is None else _color(
            color, "color"
        )
        if rgb is None:
            return None
        key = (rgb, transparency)
        style = self._surface_styles.get(key)
        if style is not None:
            return style
        style = ifcopenshell.api.style.add_style(
            self.model,
            name=(
                f"3D {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} "
                f"alpha {1 - transparency:.3f}"
            ),
        )
        ifcopenshell.api.style.add_surface_style(
            self.model,
            style=style,
            ifc_class="IfcSurfaceStyleShading",
            attributes={
                "SurfaceColour": {
                    "Name": None,
                    "Red": rgb[0],
                    "Green": rgb[1],
                    "Blue": rgb[2],
                },
                "Transparency": transparency,
            },
        )
        self._surface_styles[key] = style
        return style

    def _add_frame_insulation_blocks(
        self,
        *,
        wall: Wall,
        frame_name: str,
        side: WallSide,
        offset: float,
        depth: float,
        bays: Sequence[tuple[float, float, float, float]],
        material_name: str,
        color: str | None,
        transparency: float,
        trim_openings: bool,
        space_before_openings: float = 0,
        space_after_openings: float = 0,
        space_below_openings: float = 0,
        space_above_openings: float = 0,
    ) -> tuple[ifcopenshell.entity_instance, ...]:
        """Create one opening-aware insulation element for every frame bay."""
        model = self.model
        surface_style = self._surface_style(
            "block",
            color=color,
            transparency=transparency,
        )
        ifc_material = self._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category="insulation",
            )
            self._materials[material_name] = ifc_material

        if side == "left":
            body_offset = wall.body_offset + wall.thickness + offset
        else:
            body_offset = wall.body_offset - offset - depth
        opening_overlap = 0.01
        blocks: list[ifcopenshell.entity_instance] = []
        for bay_index, (bay_start, bay_end, bay_bottom, bay_top) in enumerate(
            bays, start=1
        ):
            bay_width = bay_end - bay_start
            bay_height = bay_top - bay_bottom
            if bay_width <= 1e-9 or bay_height <= 1e-9:
                continue
            block_name = f"{frame_name} Insulation {bay_index}"
            block = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcBuildingElementPart",
                name=block_name,
                predefined_type="USERDEFINED",
            )
            block.ObjectType = "FACADE_INSULATION"
            ifcopenshell.api.spatial.assign_container(
                model,
                products=[block],
                relating_structure=wall.storey.element,
            )
            placement = wall._placement(bay_start, bay_bottom)
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=block,
                matrix=placement,
                is_si=True,
            )
            body = ifcopenshell.api.geometry.add_wall_representation(
                model,
                context=self._body_context,
                length=bay_width,
                height=bay_height,
                thickness=depth,
                offset=body_offset,
            )
            clippings = _local_clippings(
                wall.cuts,
                placement,
                (bay_width / 2, body_offset + depth / 2, bay_height / 2),
            )
            _clip_body_representation(model, block, body, clippings)
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=block,
                representation=body,
            )
            if surface_style is not None:
                ifcopenshell.api.style.assign_representation_styles(
                    model,
                    shape_representation=body,
                    styles=[surface_style],
                )
            ifcopenshell.api.material.assign_material(
                model,
                products=[block],
                type="IfcMaterial",
                material=ifc_material,
            )

            if trim_openings:
                for opening_index, (
                    opening_start,
                    opening_end,
                    opening_bottom,
                    opening_top,
                ) in enumerate(wall._openings, start=1):
                    cut_start = opening_start - space_before_openings
                    cut_end = opening_end + space_after_openings
                    cut_bottom = opening_bottom - space_below_openings
                    cut_top = opening_top + space_above_openings
                    if (
                        bay_start >= cut_end - 1e-9
                        or cut_start >= bay_end - 1e-9
                        or bay_bottom >= cut_top - 1e-9
                        or cut_bottom >= bay_top - 1e-9
                    ):
                        continue
                    opening = ifcopenshell.api.root.create_entity(
                        model,
                        ifc_class="IfcOpeningElement",
                        name=f"{block_name} Opening {opening_index}",
                        predefined_type="OPENING",
                    )
                    opening_body = ifcopenshell.api.geometry.add_wall_representation(
                        model,
                        context=self._body_context,
                        length=cut_end - cut_start,
                        height=cut_top - cut_bottom,
                        thickness=depth + 2 * opening_overlap,
                        offset=body_offset - opening_overlap,
                    )
                    ifcopenshell.api.geometry.assign_representation(
                        model,
                        product=opening,
                        representation=opening_body,
                    )
                    ifcopenshell.api.feature.add_feature(
                        model,
                        feature=opening,
                        element=block,
                    )
                    opening_placement = wall._placement(cut_start, cut_bottom)
                    ifcopenshell.api.geometry.edit_object_placement(
                        model,
                        product=opening,
                        matrix=opening_placement,
                        is_si=True,
                    )

            block_pset = ifcopenshell.api.pset.add_pset(
                model,
                product=block,
                name="BBIM_FrameInsulation",
            )
            ifcopenshell.api.pset.edit_pset(
                model,
                pset=block_pset,
                properties={
                    "BayIndex": bay_index,
                    "BayStart": bay_start,
                    "BayEnd": bay_end,
                    "Bottom": bay_bottom,
                    "Top": bay_top,
                    "Depth": depth,
                },
            )
            blocks.append(block)
        return tuple(blocks)

    def wall_type(
        self,
        name: str,
        *,
        layers: Sequence[LayerItem],
        color: str | None = None,
        transparency: Number = 0,
    ) -> ifcopenshell.entity_instance:
        """Create a reusable wall type from ordered material layers.

        Each layer is a ``(material_name, thickness)`` pair.  Thicknesses are
        expressed in metres and their sum defines the thickness of every wall
        occurrence using this type.  Looking from ``start`` towards ``end``,
        layers are ordered from left to right (local positive Y to negative Y).
        An optional ``"axis"`` item places the wall's reference line at that
        boundary.  Without it, the construction is centred on the reference
        line.  ``color`` and ``transparency`` set the default 3D appearance of
        wall occurrences using this type.
        """
        type_name = _name(name, "name")
        if isinstance(layers, (str, bytes)):
            raise TypeError("layers must be a sequence of layer pairs")
        try:
            supplied_layers = list(layers)
        except TypeError as error:
            raise TypeError("layers must be a sequence of layer pairs") from error
        if not supplied_layers:
            raise ValueError("layers must contain at least one layer")

        normalised_layers: list[tuple[str, float]] = []
        axis_distance: float | None = None
        for index, supplied_layer in enumerate(supplied_layers, start=1):
            if isinstance(supplied_layer, str):
                if supplied_layer.strip().lower() != "axis":
                    raise ValueError(f'layer {index} string item must be "axis"')
                if axis_distance is not None:
                    raise ValueError("layers must contain at most one axis")
                axis_distance = sum(thickness for _, thickness in normalised_layers)
                continue
            try:
                material_name, thickness = supplied_layer
            except (TypeError, ValueError) as error:
                raise TypeError(
                    f"layer {index} must contain a material name and thickness"
                ) from error
            material_name = _name(material_name, f"layer {index} material name")
            thickness = _number(thickness, f"layer {index} thickness")
            if thickness <= 0:
                raise ValueError(f"layer {index} thickness must be greater than zero")
            normalised_layers.append((material_name, thickness))
        if not normalised_layers:
            raise ValueError("layers must contain at least one material layer")

        wall_type = ifcopenshell.api.root.create_entity(
            self.model,
            ifc_class="IfcWallType",
            name=type_name,
        )
        layer_set = ifcopenshell.api.material.add_material_set(
            self.model,
            name=type_name,
            set_type="IfcMaterialLayerSet",
        )
        for material_name, thickness in normalised_layers:
            material = self._materials.get(material_name)
            if material is None:
                material = ifcopenshell.api.material.add_material(
                    self.model,
                    name=material_name,
                )
                self._materials[material_name] = material
            layer = ifcopenshell.api.material.add_layer(
                self.model,
                layer_set=layer_set,
                material=material,
                name=material_name,
            )
            ifcopenshell.api.material.edit_layer(
                self.model,
                layer=layer,
                attributes={"LayerThickness": thickness},
            )
        ifcopenshell.api.material.assign_material(
            self.model,
            products=[wall_type],
            type="IfcMaterialLayerSet",
            material=layer_set,
        )
        total_thickness = sum(thickness for _, thickness in normalised_layers)
        left_thickness = (
            axis_distance if axis_distance is not None else total_thickness / 2
        )
        right_thickness = total_thickness - left_thickness
        self._wall_type_layouts[wall_type.id()] = (
            -right_thickness,
            left_thickness,
        )
        self._wall_type_styles[wall_type.id()] = self._surface_style(
            "wall",
            color=color,
            transparency=transparency,
        )
        return wall_type

    def add_vertical_frame(
        self,
        wall: Wall,
        *,
        offset: Number,
        width: Number,
        height: Number,
        depth: Number,
        gap: Number,
        lath_offsets: Sequence[Number],
        start_height: Number | None = None,
        side: WallSide = "right",
        material: str = "Wood",
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
        trim_openings: bool = True,
        space_before_openings: Number = 0,
        space_after_openings: Number = 0,
        space_above_openings: Number = 0,
        space_below_openings: Number = 0,
        insulation_material: str | None = None,
        insulation_color: str | None = None,
        insulation_transparency: Number = 0,
    ) -> VerticalFrame:
        """Add a regularly spaced frame of vertical laths beside ``wall``.

        ``side`` is viewed while looking from the wall's ``start`` towards
        its ``end``.  ``offset`` is measured outwards from that finished wall
        face to the inner face of every lath, and ``depth`` continues in the
        same outward direction.  ``start_height`` is measured above the host
        wall's storey elevation; when omitted it uses the wall's own bottom.

        ``lath_offsets`` contains mandatory lath start positions measured from
        the wall start.  Between each consecutive pair, additional laths are
        inserted with ``gap`` clear space between their edges; the final space
        before each mandatory position may be smaller.  Wall clipping planes
        are inherited, and laths are split around existing openings unless
        ``trim_openings`` is false.  ``space_before_openings``,
        ``space_after_openings``, ``space_above_openings``, and
        ``space_below_openings`` expand the clearance around each opening in
        wall-relative directions.  When
        ``insulation_material`` is supplied, one insulation block fills each
        bay between consecutive laths and inherits the opening cuts.  Add the
        returned assembly to an artificial visibility storey with
        :meth:`Storey.add` when desired.
        """
        if not isinstance(wall, Wall):
            raise TypeError("wall must be a Wall created by Storey.wall")
        if wall.file is not self.model or wall.storey.house is not self:
            raise ValueError("wall must belong to this house")
        side = _enum(side, "side", {"LEFT", "RIGHT"}).lower()
        offset = _number(offset, "offset")
        width = _number(width, "width")
        height = _number(height, "height")
        depth = _number(depth, "depth")
        gap = _number(gap, "gap")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if depth <= 0:
            raise ValueError("depth must be greater than zero")
        if gap <= 0:
            raise ValueError("gap must be greater than zero")
        if isinstance(lath_offsets, (str, bytes)):
            raise TypeError("lath_offsets must be a sequence of numbers")
        try:
            supplied_lath_offsets = list(lath_offsets)
        except TypeError as error:
            raise TypeError(
                "lath_offsets must be a sequence of numbers"
            ) from error
        if len(supplied_lath_offsets) < 2:
            raise ValueError("lath_offsets must contain at least two positions")
        normalised_lath_offsets = tuple(
            _number(value, f"lath_offsets position {index}")
            for index, value in enumerate(supplied_lath_offsets, start=1)
        )
        for index, lath_offset in enumerate(normalised_lath_offsets):
            if (
                lath_offset < -1e-9
                or lath_offset + width > wall.length + 1e-9
            ):
                raise ValueError(
                    f"lath_offsets position {index + 1} must be within the wall length"
                )
            if index and lath_offset <= normalised_lath_offsets[index - 1] + 1e-9:
                raise ValueError("lath_offsets must be strictly increasing")
        if start_height is None:
            resolved_start_height = wall.start_height
        else:
            resolved_start_height = _number(start_height, "start_height")
            if resolved_start_height < 0:
                raise ValueError("start_height must not be negative")
        space_before_openings = _number(
            space_before_openings, "space_before_openings"
        )
        space_after_openings = _number(
            space_after_openings, "space_after_openings"
        )
        space_above_openings = _number(
            space_above_openings, "space_above_openings"
        )
        space_below_openings = _number(
            space_below_openings, "space_below_openings"
        )
        if space_before_openings < 0:
            raise ValueError("space_before_openings must not be negative")
        if space_after_openings < 0:
            raise ValueError("space_after_openings must not be negative")
        if space_above_openings < 0:
            raise ValueError("space_above_openings must not be negative")
        if space_below_openings < 0:
            raise ValueError("space_below_openings must not be negative")
        if not isinstance(trim_openings, bool):
            raise TypeError("trim_openings must be a boolean")
        material_name = _name(material, "material")
        resolved_insulation_material = (
            _name(insulation_material, "insulation_material")
            if insulation_material is not None
            else None
        )
        insulation_transparency = _number(
            insulation_transparency, "insulation_transparency"
        )
        if not 0 <= insulation_transparency <= 1:
            raise ValueError("insulation_transparency must be between 0 and 1")
        transparency = _number(transparency, "transparency")
        if not 0 <= transparency <= 1:
            raise ValueError("transparency must be between 0 and 1")

        lath_positions: list[float] = [normalised_lath_offsets[0]]
        lath_pitch = width + gap
        for segment_start, segment_end in zip(
            normalised_lath_offsets, normalised_lath_offsets[1:]
        ):
            position = segment_start + lath_pitch
            while position < segment_end - 1e-9:
                lath_positions.append(round(position, 12))
                position += lath_pitch
            lath_positions.append(segment_end)
        tangent = np.array(
            (
                (wall.end[0] - wall.start[0]) / wall.length,
                (wall.end[1] - wall.start[1]) / wall.length,
                0.0,
            ),
            dtype=float,
        )
        left_normal = np.array((-tangent[1], tangent[0], 0.0), dtype=float)
        if side == "left":
            outward = left_normal
            wall_face = wall.body_offset + wall.thickness
        else:
            outward = -left_normal
            wall_face = wall.body_offset
        wall_face_origin = np.array(
            (wall.start[0], wall.start[1], 0.0), dtype=float
        ) + wall_face * left_normal

        self._vertical_frame_count += 1
        frame_name = (
            _name(name, "name")
            if name is not None
            else f"Vertical Frame {self._vertical_frame_count}"
        )
        model = self.model
        assembly_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcElementAssembly",
            name=frame_name,
            predefined_type="USERDEFINED",
        )
        assembly_element.ObjectType = "FACADE_VERTICAL_FRAME"
        assembly_element.AssemblyPlace = "SITE"
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[assembly_element],
            relating_structure=wall.storey.element,
        )
        assembly_placement = np.eye(4)
        assembly_placement[2, 3] = wall.storey.elevation
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=assembly_element,
            matrix=assembly_placement,
            is_si=True,
        )

        resolved_color = color
        if (
            resolved_color is None
            and "beam" not in self._default_colors
            and material_name.casefold() == "wood"
        ):
            resolved_color = "#8B5A2B"
        surface_style = self._surface_style(
            "beam",
            color=resolved_color,
            transparency=transparency,
        )
        ifc_material = self._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category=material_name.casefold(),
            )
            self._materials[material_name] = ifc_material

        frame_bottom = resolved_start_height
        frame_top = resolved_start_height + height
        members: list[ifcopenshell.entity_instance] = []
        for lath_index, lath_start in enumerate(lath_positions):
            segments: list[tuple[float, float]] = [(frame_bottom, frame_top)]
            if trim_openings:
                lath_end = lath_start + width
                removed_intervals = sorted(
                    (
                        max(
                            frame_bottom,
                            opening_bottom - space_below_openings,
                        ),
                        min(
                            frame_top,
                            opening_top + space_above_openings,
                        ),
                    )
                    for (
                        opening_start,
                        opening_end,
                        opening_bottom,
                        opening_top,
                    ) in wall._openings
                    if lath_start
                    < opening_end + space_after_openings - 1e-9
                    and opening_start - space_before_openings
                    < lath_end - 1e-9
                    and frame_bottom
                    < opening_top + space_above_openings - 1e-9
                    and opening_bottom - space_below_openings
                    < frame_top - 1e-9
                )
                if removed_intervals:
                    merged_intervals: list[list[float]] = []
                    for interval_start, interval_end in removed_intervals:
                        if (
                            not merged_intervals
                            or interval_start > merged_intervals[-1][1] + 1e-9
                        ):
                            merged_intervals.append([interval_start, interval_end])
                        else:
                            merged_intervals[-1][1] = max(
                                merged_intervals[-1][1], interval_end
                            )
                    segments = []
                    cursor = frame_bottom
                    for interval_start, interval_end in merged_intervals:
                        if interval_start > cursor + 1e-9:
                            segments.append((cursor, interval_start))
                        cursor = max(cursor, interval_end)
                    if cursor < frame_top - 1e-9:
                        segments.append((cursor, frame_top))

            for segment_index, (segment_bottom, segment_top) in enumerate(
                segments, start=1
            ):
                segment_height = segment_top - segment_bottom
                member_name = f"{frame_name} Lath {lath_index + 1}"
                if len(segments) > 1:
                    member_name += f".{segment_index}"
                member = ifcopenshell.api.root.create_entity(
                    model,
                    ifc_class="IfcMember",
                    name=member_name,
                    predefined_type="STUD",
                )
                member.ObjectType = "FACADE_LATH"

                centre = (
                    wall_face_origin
                    + (lath_start + width / 2) * tangent
                    + (offset + depth / 2) * outward
                )
                placement = np.eye(4)
                placement[:3, 0] = (0.0, 0.0, 1.0)
                placement[:3, 2] = outward
                placement[:3, 1] = np.cross(
                    placement[:3, 2], placement[:3, 0]
                )
                placement[:2, 3] = centre[:2]
                placement[2, 3] = wall.storey.elevation + segment_bottom
                ifcopenshell.api.spatial.assign_container(
                    model,
                    products=[member],
                    relating_structure=wall.storey.element,
                )
                ifcopenshell.api.geometry.edit_object_placement(
                    model,
                    product=member,
                    matrix=placement,
                    is_si=True,
                )

                profile = model.createIfcRectangleProfileDef(
                    "AREA",
                    f"{member_name} Profile",
                    None,
                    width,
                    depth,
                )
                body = ifcopenshell.api.geometry.add_profile_representation(
                    model,
                    context=self._body_context,
                    profile=profile,
                    depth=segment_height,
                    cardinal_point="mid-depth centre",
                    placement_zx_axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                )
                clippings = _local_clippings(
                    wall.cuts,
                    placement,
                    (segment_height / 2, 0.0, 0.0),
                )
                _clip_body_representation(model, member, body, clippings)
                ifcopenshell.api.geometry.assign_representation(
                    model,
                    product=member,
                    representation=body,
                )
                if surface_style is not None:
                    ifcopenshell.api.style.assign_representation_styles(
                        model,
                        shape_representation=body,
                        styles=[surface_style],
                    )
                ifcopenshell.api.material.assign_material(
                    model,
                    products=[member],
                    type="IfcMaterial",
                    material=ifc_material,
                )
                common_pset = ifcopenshell.api.pset.add_pset(
                    model,
                    product=member,
                    name="Pset_MemberCommon",
                )
                ifcopenshell.api.pset.edit_pset(
                    model,
                    pset=common_pset,
                    properties={"LoadBearing": False},
                )
                members.append(member)

        insulation_blocks: tuple[ifcopenshell.entity_instance, ...] = ()
        if resolved_insulation_material is not None:
            insulation_bays = tuple(
                (
                    first_lath + width,
                    second_lath,
                    frame_bottom,
                    frame_top,
                )
                for first_lath, second_lath in zip(
                    lath_positions, lath_positions[1:]
                )
            )
            insulation_blocks = self._add_frame_insulation_blocks(
                wall=wall,
                frame_name=frame_name,
                side=side,
                offset=offset,
                depth=depth,
                bays=insulation_bays,
                material_name=resolved_insulation_material,
                color=insulation_color,
                transparency=insulation_transparency,
                trim_openings=trim_openings,
                space_before_openings=space_before_openings,
                space_after_openings=space_after_openings,
                space_below_openings=space_below_openings,
                space_above_openings=space_above_openings,
            )
        frame_elements = (*members, *insulation_blocks)
        if frame_elements:
            ifcopenshell.api.aggregate.assign_object(
                model,
                products=frame_elements,
                relating_object=assembly_element,
            )
        frame_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=assembly_element,
            name="BBIM_VerticalFrame",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=frame_pset,
            properties={
                "HostWall": wall.GlobalId,
                "Side": side,
                "Offset": offset,
                "Width": width,
                "Depth": depth,
                "StartHeight": resolved_start_height,
                "Height": height,
                "Gap": gap,
                "LathOffsets": json.dumps(normalised_lath_offsets),
                "LathPositions": json.dumps(lath_positions),
                "TrimOpenings": trim_openings,
                "SpaceBeforeOpenings": space_before_openings,
                "SpaceAfterOpenings": space_after_openings,
                "SpaceAboveOpenings": space_above_openings,
                "SpaceBelowOpenings": space_below_openings,
                "InsulationMaterial": resolved_insulation_material,
                "InsulationBlocks": json.dumps(
                    [block.GlobalId for block in insulation_blocks]
                ),
            },
        )
        return VerticalFrame(
            assembly_element,
            wall,
            side=side,
            offset=offset,
            width=width,
            depth=depth,
            start_height=resolved_start_height,
            height=height,
            gap=gap,
            lath_offsets=normalised_lath_offsets,
            lath_positions=tuple(lath_positions),
            space_before_openings=space_before_openings,
            space_after_openings=space_after_openings,
            space_above_openings=space_above_openings,
            space_below_openings=space_below_openings,
            insulation_material=resolved_insulation_material,
            insulation_blocks=insulation_blocks,
            members=tuple(members),
        )

    def add_horizontal_frame(
        self,
        wall: Wall,
        *,
        offset: Number,
        width: Number,
        depth: Number,
        gap: Number,
        lath_offsets: Sequence[Number],
        start_extension: Number = 0,
        end_extension: Number = 0,
        side: WallSide = "right",
        material: str = "Wood",
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
        trim_openings: bool = True,
        space_before_openings: Number = 0,
        space_after_openings: Number = 0,
        space_above_openings: Number = 0,
        space_below_openings: Number = 0,
        insulation_material: str | None = None,
        insulation_color: str | None = None,
        insulation_transparency: Number = 0,
    ) -> HorizontalFrame:
        """Add explicitly positioned horizontal laths beside ``wall``.

        ``side`` is viewed while looking from the wall's ``start`` towards
        its ``end``.  ``offset`` is measured outwards from that finished wall
        face to the inner face of every lath, and ``depth`` continues in the
        same outward direction.

        Each value in ``lath_offsets`` is the mandatory bottom of a lath,
        measured above the host wall's storey elevation.  Between each
        consecutive pair, additional laths are inserted with ``gap`` clear
        space between their edges; the final space before each mandatory
        position may be smaller.  ``width`` is the lath's vertical dimension.
        Every lath spans the wall from start to end, extended by
        ``start_extension`` before the start and ``end_extension`` beyond the
        end.  Laths are split around existing wall openings unless
        ``trim_openings`` is false.  ``space_before_openings``,
        ``space_after_openings``, ``space_above_openings``, and
        ``space_below_openings`` expand the clearance around each opening in
        wall-relative directions.  When ``insulation_material`` is supplied, one
        insulation block fills each bay between consecutive laths and inherits
        the opening cuts.  Add the returned assembly to an artificial
        visibility storey with :meth:`Storey.add` when desired.
        """
        if not isinstance(wall, Wall):
            raise TypeError("wall must be a Wall created by Storey.wall")
        if wall.file is not self.model or wall.storey.house is not self:
            raise ValueError("wall must belong to this house")
        side = _enum(side, "side", {"LEFT", "RIGHT"}).lower()
        offset = _number(offset, "offset")
        width = _number(width, "width")
        depth = _number(depth, "depth")
        gap = _number(gap, "gap")
        start_extension = _number(start_extension, "start_extension")
        end_extension = _number(end_extension, "end_extension")
        space_before_openings = _number(
            space_before_openings, "space_before_openings"
        )
        space_after_openings = _number(
            space_after_openings, "space_after_openings"
        )
        space_above_openings = _number(
            space_above_openings, "space_above_openings"
        )
        space_below_openings = _number(
            space_below_openings, "space_below_openings"
        )
        if offset < 0:
            raise ValueError("offset must not be negative")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if depth <= 0:
            raise ValueError("depth must be greater than zero")
        if gap <= 0:
            raise ValueError("gap must be greater than zero")
        if start_extension < 0:
            raise ValueError("start_extension must not be negative")
        if end_extension < 0:
            raise ValueError("end_extension must not be negative")
        if space_before_openings < 0:
            raise ValueError("space_before_openings must not be negative")
        if space_after_openings < 0:
            raise ValueError("space_after_openings must not be negative")
        if space_above_openings < 0:
            raise ValueError("space_above_openings must not be negative")
        if space_below_openings < 0:
            raise ValueError("space_below_openings must not be negative")
        if isinstance(lath_offsets, (str, bytes)):
            raise TypeError("lath_offsets must be a sequence of numbers")
        try:
            supplied_lath_offsets = list(lath_offsets)
        except TypeError as error:
            raise TypeError(
                "lath_offsets must be a sequence of numbers"
            ) from error
        if len(supplied_lath_offsets) < 2:
            raise ValueError("lath_offsets must contain at least two positions")
        normalised_lath_offsets = tuple(
            _number(value, f"lath_offsets position {index}")
            for index, value in enumerate(supplied_lath_offsets, start=1)
        )
        for index, lath_offset in enumerate(normalised_lath_offsets):
            if lath_offset < 0:
                raise ValueError("lath_offsets must not contain negative positions")
            if index and lath_offset <= normalised_lath_offsets[index - 1] + 1e-9:
                raise ValueError("lath_offsets must be strictly increasing")
        if not isinstance(trim_openings, bool):
            raise TypeError("trim_openings must be a boolean")
        material_name = _name(material, "material")
        resolved_insulation_material = (
            _name(insulation_material, "insulation_material")
            if insulation_material is not None
            else None
        )
        insulation_transparency = _number(
            insulation_transparency, "insulation_transparency"
        )
        if not 0 <= insulation_transparency <= 1:
            raise ValueError("insulation_transparency must be between 0 and 1")
        transparency = _number(transparency, "transparency")
        if not 0 <= transparency <= 1:
            raise ValueError("transparency must be between 0 and 1")

        lath_positions: list[float] = [normalised_lath_offsets[0]]
        lath_pitch = width + gap
        for segment_start, segment_end in zip(
            normalised_lath_offsets, normalised_lath_offsets[1:]
        ):
            position = segment_start + lath_pitch
            while position < segment_end - 1e-9:
                lath_positions.append(round(position, 12))
                position += lath_pitch
            lath_positions.append(segment_end)

        tangent = np.array(
            (
                (wall.end[0] - wall.start[0]) / wall.length,
                (wall.end[1] - wall.start[1]) / wall.length,
                0.0,
            ),
            dtype=float,
        )
        left_normal = np.array((-tangent[1], tangent[0], 0.0), dtype=float)
        if side == "left":
            outward = left_normal
            wall_face = wall.body_offset + wall.thickness
        else:
            outward = -left_normal
            wall_face = wall.body_offset
        wall_face_origin = np.array(
            (wall.start[0], wall.start[1], 0.0), dtype=float
        ) + wall_face * left_normal
        lath_length = wall.length + start_extension + end_extension

        self._horizontal_frame_count += 1
        frame_name = (
            _name(name, "name")
            if name is not None
            else f"Horizontal Frame {self._horizontal_frame_count}"
        )
        model = self.model
        assembly_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcElementAssembly",
            name=frame_name,
            predefined_type="USERDEFINED",
        )
        assembly_element.ObjectType = "FACADE_HORIZONTAL_FRAME"
        assembly_element.AssemblyPlace = "SITE"
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[assembly_element],
            relating_structure=wall.storey.element,
        )
        assembly_placement = np.eye(4)
        assembly_placement[2, 3] = wall.storey.elevation
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=assembly_element,
            matrix=assembly_placement,
            is_si=True,
        )

        resolved_color = color
        if (
            resolved_color is None
            and "beam" not in self._default_colors
            and material_name.casefold() == "wood"
        ):
            resolved_color = "#8B5A2B"
        surface_style = self._surface_style(
            "beam",
            color=resolved_color,
            transparency=transparency,
        )
        ifc_material = self._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category=material_name.casefold(),
            )
            self._materials[material_name] = ifc_material

        frame_start = -start_extension
        frame_end = wall.length + end_extension
        members: list[ifcopenshell.entity_instance] = []
        for lath_index, lath_offset in enumerate(lath_positions, start=1):
            lath_top = lath_offset + width
            segments: list[tuple[float, float]] = [(frame_start, frame_end)]
            if trim_openings:
                removed_intervals = sorted(
                    (
                        max(
                            frame_start,
                            opening_start - space_before_openings,
                        ),
                        min(
                            frame_end,
                            opening_end + space_after_openings,
                        ),
                    )
                    for (
                        opening_start,
                        opening_end,
                        opening_bottom,
                        opening_top,
                    ) in wall._openings
                    if frame_start
                    < opening_end + space_after_openings - 1e-9
                    and opening_start - space_before_openings
                    < frame_end - 1e-9
                    and lath_offset
                    < opening_top + space_above_openings - 1e-9
                    and opening_bottom - space_below_openings
                    < lath_top - 1e-9
                )
                if removed_intervals:
                    merged_intervals: list[list[float]] = []
                    for interval_start, interval_end in removed_intervals:
                        if (
                            not merged_intervals
                            or interval_start > merged_intervals[-1][1] + 1e-9
                        ):
                            merged_intervals.append([interval_start, interval_end])
                        else:
                            merged_intervals[-1][1] = max(
                                merged_intervals[-1][1], interval_end
                            )
                    segments = []
                    cursor = frame_start
                    for interval_start, interval_end in merged_intervals:
                        if interval_start > cursor + 1e-9:
                            segments.append((cursor, interval_start))
                        cursor = max(cursor, interval_end)
                    if cursor < frame_end - 1e-9:
                        segments.append((cursor, frame_end))

            for segment_index, (segment_start, segment_end) in enumerate(
                segments, start=1
            ):
                segment_length = segment_end - segment_start
                member_name = f"{frame_name} Lath {lath_index}"
                if len(segments) > 1:
                    member_name += f".{segment_index}"
                member = ifcopenshell.api.root.create_entity(
                    model,
                    ifc_class="IfcMember",
                    name=member_name,
                    predefined_type="MEMBER",
                )
                member.ObjectType = "FACADE_LATH"

                member_start = (
                    wall_face_origin
                    + segment_start * tangent
                    + (offset + depth / 2) * outward
                )
                placement = np.eye(4)
                placement[:3, 0] = tangent
                placement[:3, 1] = left_normal
                placement[:3, 2] = (0.0, 0.0, 1.0)
                placement[:2, 3] = member_start[:2]
                placement[2, 3] = (
                    wall.storey.elevation + lath_offset + width / 2
                )
                ifcopenshell.api.spatial.assign_container(
                    model,
                    products=[member],
                    relating_structure=wall.storey.element,
                )
                ifcopenshell.api.geometry.edit_object_placement(
                    model,
                    product=member,
                    matrix=placement,
                    is_si=True,
                )

                profile = model.createIfcRectangleProfileDef(
                    "AREA",
                    f"{member_name} Profile",
                    None,
                    depth,
                    width,
                )
                body = ifcopenshell.api.geometry.add_profile_representation(
                    model,
                    context=self._body_context,
                    profile=profile,
                    depth=segment_length,
                    cardinal_point="mid-depth centre",
                    placement_zx_axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                )
                ifcopenshell.api.geometry.assign_representation(
                    model,
                    product=member,
                    representation=body,
                )
                if surface_style is not None:
                    ifcopenshell.api.style.assign_representation_styles(
                        model,
                        shape_representation=body,
                        styles=[surface_style],
                    )
                ifcopenshell.api.material.assign_material(
                    model,
                    products=[member],
                    type="IfcMaterial",
                    material=ifc_material,
                )
                common_pset = ifcopenshell.api.pset.add_pset(
                    model,
                    product=member,
                    name="Pset_MemberCommon",
                )
                ifcopenshell.api.pset.edit_pset(
                    model,
                    pset=common_pset,
                    properties={"LoadBearing": False},
                )
                members.append(member)

        insulation_blocks: tuple[ifcopenshell.entity_instance, ...] = ()
        if resolved_insulation_material is not None:
            insulation_bays = tuple(
                (
                    frame_start,
                    frame_end,
                    first_lath + width,
                    second_lath,
                )
                for first_lath, second_lath in zip(
                    lath_positions, lath_positions[1:]
                )
            )
            insulation_blocks = self._add_frame_insulation_blocks(
                wall=wall,
                frame_name=frame_name,
                side=side,
                offset=offset,
                depth=depth,
                bays=insulation_bays,
                material_name=resolved_insulation_material,
                color=insulation_color,
                transparency=insulation_transparency,
                trim_openings=trim_openings,
                space_before_openings=space_before_openings,
                space_after_openings=space_after_openings,
                space_above_openings=space_above_openings,
                space_below_openings=space_below_openings,
            )
        frame_elements = (*members, *insulation_blocks)
        if frame_elements:
            ifcopenshell.api.aggregate.assign_object(
                model,
                products=frame_elements,
                relating_object=assembly_element,
            )
        frame_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=assembly_element,
            name="BBIM_HorizontalFrame",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=frame_pset,
            properties={
                "HostWall": wall.GlobalId,
                "Side": side,
                "Offset": offset,
                "Width": width,
                "Depth": depth,
                "Gap": gap,
                "Length": lath_length,
                "LathOffsets": json.dumps(normalised_lath_offsets),
                "LathPositions": json.dumps(lath_positions),
                "StartExtension": start_extension,
                "EndExtension": end_extension,
                "TrimOpenings": trim_openings,
                "SpaceBeforeOpenings": space_before_openings,
                "SpaceAfterOpenings": space_after_openings,
                "SpaceAboveOpenings": space_above_openings,
                "SpaceBelowOpenings": space_below_openings,
                "InsulationMaterial": resolved_insulation_material,
                "InsulationBlocks": json.dumps(
                    [block.GlobalId for block in insulation_blocks]
                ),
            },
        )
        return HorizontalFrame(
            assembly_element,
            wall,
            side=side,
            offset=offset,
            width=width,
            depth=depth,
            gap=gap,
            length=lath_length,
            lath_offsets=normalised_lath_offsets,
            lath_positions=tuple(lath_positions),
            start_extension=start_extension,
            end_extension=end_extension,
            trim_openings=trim_openings,
            space_before_openings=space_before_openings,
            space_after_openings=space_after_openings,
            space_above_openings=space_above_openings,
            space_below_openings=space_below_openings,
            insulation_material=resolved_insulation_material,
            insulation_blocks=insulation_blocks,
            members=tuple(members),
        )

    def add_facade_layer(
        self,
        wall: Wall,
        *,
        offset: Number,
        thickness: Number,
        side: WallSide = "right",
        start_height: Number | None = None,
        height: Number | None = None,
        start_extension: Number = 0,
        end_extension: Number = 0,
        material: str = "Cementovlaknita deska",
        name: str | None = None,
        color: str | None = "#ffffff",
        transparency: Number = 0,
        trim_openings: bool = True,
        opening_walls: Sequence[Wall] | None = None,
        space_before_openings: Number = 0,
        space_after_openings: Number = 0,
        space_above_openings: Number = 0,
        space_below_openings: Number = 0,
    ) -> FacadeLayer:
        """Add one solid façade covering beside ``wall``.

        The covering spans the wall plus the optional end extensions and is a
        single ``IfcCovering`` with type ``CLADDING``.  Existing wall openings
        are represented as real IFC voids instead of splitting the covering
        into panels.  ``opening_walls`` may contain aligned walls from other
        storeys; their openings are projected onto the host wall, which makes
        one tall covering capable of cutting upper-storey windows too.

        ``offset`` is measured from the selected finished wall face to the
        covering's inner face.  The four opening-space parameters expand each
        void in wall-relative and vertical directions.
        """
        if not isinstance(wall, Wall):
            raise TypeError("wall must be a Wall created by Storey.wall")
        if wall.file is not self.model or wall.storey.house is not self:
            raise ValueError("wall must belong to this house")
        side = _enum(side, "side", {"LEFT", "RIGHT"}).lower()
        offset = _number(offset, "offset")
        thickness = _number(thickness, "thickness")
        start_extension = _number(start_extension, "start_extension")
        end_extension = _number(end_extension, "end_extension")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        if start_extension < 0:
            raise ValueError("start_extension must not be negative")
        if end_extension < 0:
            raise ValueError("end_extension must not be negative")

        resolved_start_height = (
            wall.start_height
            if start_height is None
            else _number(start_height, "start_height")
        )
        if resolved_start_height < 0:
            raise ValueError("start_height must not be negative")
        resolved_height = (
            wall.end_height - resolved_start_height
            if height is None
            else _number(height, "height")
        )
        if resolved_height <= 0:
            raise ValueError("height must be greater than zero")

        space_before_openings = _number(
            space_before_openings, "space_before_openings"
        )
        space_after_openings = _number(
            space_after_openings, "space_after_openings"
        )
        space_above_openings = _number(
            space_above_openings, "space_above_openings"
        )
        space_below_openings = _number(
            space_below_openings, "space_below_openings"
        )
        for parameter_name, value in (
            ("space_before_openings", space_before_openings),
            ("space_after_openings", space_after_openings),
            ("space_above_openings", space_above_openings),
            ("space_below_openings", space_below_openings),
        ):
            if value < 0:
                raise ValueError(f"{parameter_name} must not be negative")
        if not isinstance(trim_openings, bool):
            raise TypeError("trim_openings must be a boolean")
        transparency = _number(transparency, "transparency")
        if not 0 <= transparency <= 1:
            raise ValueError("transparency must be between 0 and 1")
        material_name = _name(material, "material")

        if opening_walls is None:
            supplied_opening_walls: list[Wall] = []
        else:
            if isinstance(opening_walls, (str, bytes)):
                raise TypeError("opening_walls must be a sequence of Wall objects")
            try:
                supplied_opening_walls = list(opening_walls)
            except TypeError as error:
                raise TypeError(
                    "opening_walls must be a sequence of Wall objects"
                ) from error
        resolved_opening_walls = [wall]
        seen_walls = {wall.id()}
        host_tangent = np.array(
            (
                (wall.end[0] - wall.start[0]) / wall.length,
                (wall.end[1] - wall.start[1]) / wall.length,
            ),
            dtype=float,
        )
        host_normal = np.array((-host_tangent[1], host_tangent[0]), dtype=float)
        host_start = np.array(wall.start, dtype=float)
        for index, opening_wall in enumerate(supplied_opening_walls, start=1):
            if not isinstance(opening_wall, Wall):
                raise TypeError(f"opening_walls item {index} must be a Wall")
            if (
                opening_wall.file is not self.model
                or opening_wall.storey.house is not self
            ):
                raise ValueError(
                    f"opening_walls item {index} must belong to this house"
                )
            source_tangent = np.array(
                (
                    (opening_wall.end[0] - opening_wall.start[0])
                    / opening_wall.length,
                    (opening_wall.end[1] - opening_wall.start[1])
                    / opening_wall.length,
                ),
                dtype=float,
            )
            if abs(abs(float(np.dot(source_tangent, host_tangent))) - 1) > 1e-9:
                raise ValueError(
                    f"opening_walls item {index} must be parallel to the host wall"
                )
            line_distance = abs(
                float(
                    np.dot(
                        np.array(opening_wall.start, dtype=float) - host_start,
                        host_normal,
                    )
                )
            )
            if line_distance > 1e-9:
                raise ValueError(
                    f"opening_walls item {index} must be aligned with the host wall"
                )
            if opening_wall.id() not in seen_walls:
                resolved_opening_walls.append(opening_wall)
                seen_walls.add(opening_wall.id())

        projected_openings: list[tuple[float, float, float, float]] = []
        if trim_openings:
            for opening_wall in resolved_opening_walls:
                source_tangent = np.array(
                    (
                        (opening_wall.end[0] - opening_wall.start[0])
                        / opening_wall.length,
                        (opening_wall.end[1] - opening_wall.start[1])
                        / opening_wall.length,
                    ),
                    dtype=float,
                )
                source_start = np.array(opening_wall.start, dtype=float)
                elevation_delta = (
                    opening_wall.storey.elevation - wall.storey.elevation
                )
                for opening_start, opening_end, opening_bottom, opening_top in (
                    opening_wall._openings
                ):
                    world_start = source_start + opening_start * source_tangent
                    world_end = source_start + opening_end * source_tangent
                    projected_start = float(
                        np.dot(world_start - host_start, host_tangent)
                    )
                    projected_end = float(
                        np.dot(world_end - host_start, host_tangent)
                    )
                    projected_openings.append(
                        (
                            min(projected_start, projected_end)
                            - space_before_openings,
                            max(projected_start, projected_end)
                            + space_after_openings,
                            elevation_delta
                            + opening_bottom
                            - space_below_openings,
                            elevation_delta
                            + opening_top
                            + space_above_openings,
                        )
                    )

        self._facade_layer_count += 1
        layer_name = (
            _name(name, "name")
            if name is not None
            else f"Facade Layer {self._facade_layer_count}"
        )
        model = self.model
        element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcCovering",
            name=layer_name,
            predefined_type="CLADDING",
        )
        element.ObjectType = "FACADE_CLADDING"
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[element],
            relating_structure=wall.storey.element,
        )

        layer_start = -start_extension
        layer_length = wall.length + start_extension + end_extension
        placement = wall._placement(layer_start, resolved_start_height)
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=element,
            matrix=placement,
            is_si=True,
        )
        if side == "left":
            body_offset = wall.body_offset + wall.thickness + offset
        else:
            body_offset = wall.body_offset - offset - thickness
        body = ifcopenshell.api.geometry.add_wall_representation(
            model,
            context=self._body_context,
            length=layer_length,
            height=resolved_height,
            thickness=thickness,
            offset=body_offset,
        )
        clippings = _local_clippings(
            wall.cuts,
            placement,
            (layer_length / 2, body_offset + thickness / 2, resolved_height / 2),
        )
        _clip_body_representation(model, element, body, clippings)
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=element,
            representation=body,
        )
        surface_style = self._surface_style(
            "wall", color=color, transparency=transparency
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )
        ifc_material = self._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category="cladding",
            )
            self._materials[material_name] = ifc_material
        ifcopenshell.api.material.assign_material(
            model,
            products=[element],
            type="IfcMaterial",
            material=ifc_material,
        )

        opening_overlap = 0.01
        openings: list[ifcopenshell.entity_instance] = []
        layer_end = wall.length + end_extension
        layer_bottom = resolved_start_height
        layer_top = resolved_start_height + resolved_height
        for opening_index, (
            opening_start,
            opening_end,
            opening_bottom,
            opening_top,
        ) in enumerate(projected_openings, start=1):
            if (
                opening_start >= layer_end - 1e-9
                or layer_start >= opening_end - 1e-9
                or opening_bottom >= layer_top - 1e-9
                or layer_bottom >= opening_top - 1e-9
            ):
                continue
            opening = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcOpeningElement",
                name=f"{layer_name} Opening {opening_index}",
                predefined_type="OPENING",
            )
            opening_body = ifcopenshell.api.geometry.add_wall_representation(
                model,
                context=self._body_context,
                length=opening_end - opening_start,
                height=opening_top - opening_bottom,
                thickness=thickness + 2 * opening_overlap,
                offset=body_offset - opening_overlap,
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=opening,
                representation=opening_body,
            )
            ifcopenshell.api.feature.add_feature(
                model,
                feature=opening,
                element=element,
            )
            opening_placement = wall._placement(opening_start, opening_bottom)
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=opening,
                matrix=opening_placement,
                is_si=True,
            )
            openings.append(opening)

        layer_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=element,
            name="BBIM_FacadeLayer",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=layer_pset,
            properties={
                "HostWall": wall.GlobalId,
                "Side": side,
                "Offset": offset,
                "Thickness": thickness,
                "StartHeight": resolved_start_height,
                "Height": resolved_height,
                "Length": layer_length,
                "StartExtension": start_extension,
                "EndExtension": end_extension,
                "Material": material_name,
                "TrimOpenings": trim_openings,
                "OpeningWalls": json.dumps(
                    [opening_wall.GlobalId for opening_wall in resolved_opening_walls]
                ),
                "SpaceBeforeOpenings": space_before_openings,
                "SpaceAfterOpenings": space_after_openings,
                "SpaceAboveOpenings": space_above_openings,
                "SpaceBelowOpenings": space_below_openings,
            },
        )
        return FacadeLayer(
            element,
            wall,
            side=side,
            offset=offset,
            thickness=thickness,
            start_height=resolved_start_height,
            height=resolved_height,
            length=layer_length,
            start_extension=start_extension,
            end_extension=end_extension,
            material_name=material_name,
            trim_openings=trim_openings,
            opening_walls=tuple(resolved_opening_walls),
            space_before_openings=space_before_openings,
            space_after_openings=space_after_openings,
            space_above_openings=space_above_openings,
            space_below_openings=space_below_openings,
            openings=tuple(openings),
        )

    def storey(self, name: str, *, elevation: Number) -> Storey:
        """Create and return a building storey at ``elevation`` metres."""
        storey = Storey(self, _name(name, "name"), _number(elevation, "elevation"))
        self._storeys.append(storey)
        return storey

    def add_drawing(
        self,
        name: str,
        x: Number,
        y: Number,
        z: Number,
        radius: Number,
        *,
        view: DrawingView = "plan",
        direction: Point3D | None = None,
        storeys: Sequence[Storey] | None = None,
        door_annotations: bool = True,
        door_annotation_offset: Number = 0,
        doors_closed: bool = False,
        right_panel_width: Number = 0,
    ) -> Drawing:
        """Add a persisted square plan or elevation drawing to this IFC model.

        ``view="plan"`` preserves the existing downward-looking plan.  For a
        basic side view, use ``view="elevation"`` and supply a horizontal
        ``direction`` pointing from the camera toward the building, such as
        ``(0, 1, 0)``.  Elevations currently contain projected model geometry
        only; plan annotations and automatic door labels are omitted.
        ``storeys`` limits both model geometry and automatic plan annotations
        to the supplied building storeys.  When omitted, all storeys are
        included.  Drawing-specific annotations are always included.
        ``door_annotations`` automatically adds a width-over-height label to
        every included door; disable it to place selected labels manually with
        :meth:`Drawing.add_door_annotation`.  ``door_annotation_offset`` moves
        every automatic label farther into the door swing in metres.
        ``doors_closed`` renders the 3D door leaves closed in an elevation
        without changing their model geometry or plan swing symbols.
        ``right_panel_width`` adds paper space to the right of the camera view,
        measured in printed millimetres.  It does not resize or move the model
        view.  Use :meth:`Drawing.add_material_legend` to add the first
        supported optional table to that panel.
        """
        drawing_name = _name(name, "name")
        if any(drawing.name == drawing_name for drawing in self._drawings):
            raise ValueError(f'drawing name already exists: "{drawing_name}"')
        drawing = Drawing(
            self,
            drawing_name,
            x=x,
            y=y,
            z=z,
            radius=radius,
            view=view,
            direction=direction,
            storeys=storeys,
            door_annotations=door_annotations,
            door_annotation_offset=door_annotation_offset,
            doors_closed=doors_closed,
            right_panel_width=right_panel_width,
        )
        self._drawings.append(drawing)
        return drawing

    def write(self, path: str | PathLike[str]) -> Path:
        """Write the IFC model and return the output path."""
        output = Path(path)
        self.model.write(str(output))
        self._ifc_path = output.resolve()
        return output

    def generate_plan(
        self,
        output: str | PathLike[str],
        *,
        x: Number,
        y: Number,
        z: Number,
        radius: Number,
        png: bool = False,
        blender: str | PathLike[str] = "blender",
        inkscape: str | PathLike[str] = "inkscape",
        stylesheet: str | PathLike[str] | None = None,
    ) -> Path:
        """Generate a plan from this house's most recently written IFC path.

        This compatibility wrapper synchronises the live model to disk before
        delegating to the module-level :func:`generate_plan`.  New code may
        instead call ``generate_plan("house.ifc", "house.svg", ...)`` directly.
        """
        if self._ifc_path is None:
            raise RuntimeError("write the IFC model before generating a plan")
        self.model.write(str(self._ifc_path))
        return generate_plan(
            self._ifc_path,
            output,
            x=x,
            y=y,
            z=z,
            radius=radius,
            png=png,
            blender=blender,
            inkscape=inkscape,
            stylesheet=stylesheet,
        )


class Drawing:
    """A persisted Bonsai plan or elevation drawing belonging to a House."""

    def __init__(
        self,
        house: House,
        name: str,
        *,
        x: Number,
        y: Number,
        z: Number,
        radius: Number,
        view: DrawingView,
        direction: Point3D | None,
        storeys: Sequence[Storey] | None,
        door_annotations: bool,
        door_annotation_offset: Number,
        doors_closed: bool,
        right_panel_width: Number,
    ) -> None:
        self.house = house
        self.name = name
        self.x = _number(x, "x")
        self.y = _number(y, "y")
        self.z = _number(z, "z")
        self.radius = _number(radius, "radius")
        if self.radius <= 0:
            raise ValueError("radius must be greater than zero")
        self.view = _enum(view, "view", {"PLAN", "ELEVATION"}).lower()
        if self.view == "plan":
            if direction is not None:
                raise ValueError("direction is only supported for elevation drawings")
            self.direction = (0.0, 0.0, -1.0)
        else:
            if direction is None:
                raise ValueError("direction is required for elevation drawings")
            direction_x, direction_y, direction_z = _point_3d(
                direction, "direction"
            )
            if abs(direction_z) > 1e-9:
                raise ValueError("elevation direction must be horizontal")
            direction_length = hypot(direction_x, direction_y)
            if direction_length == 0:
                raise ValueError("elevation direction must not be zero")
            self.direction = (
                direction_x / direction_length,
                direction_y / direction_length,
                0.0,
            )
        self._batting_count = 0
        self._dimension_count = 0
        self._entrance_arrow_count = 0
        self._annotated_stairs: set[int] = set()
        self._annotated_chimneys: set[int] = set()
        self._annotated_doors: set[int] = set()
        if not isinstance(door_annotations, bool):
            raise TypeError("door_annotations must be a boolean")
        self._automatic_door_annotations = (
            door_annotations and self.view == "plan"
        )
        self._door_annotation_offset = _number(
            door_annotation_offset, "door_annotation_offset"
        )
        if not isinstance(doors_closed, bool):
            raise TypeError("doors_closed must be a boolean")
        if doors_closed and self.view != "elevation":
            raise ValueError("doors_closed is only supported for elevation drawings")
        self.doors_closed = doors_closed
        self.right_panel_width = _number(
            right_panel_width,
            "right_panel_width",
        )
        if self.right_panel_width < 0:
            raise ValueError("right_panel_width must not be negative")
        self._right_panel_tables: list[dict[str, object]] = []
        self._includes_all_storeys = storeys is None
        if storeys is None:
            self._storeys: tuple[Storey, ...] = ()
        else:
            if isinstance(storeys, (str, bytes)):
                raise TypeError("storeys must be a sequence of Storey objects")
            try:
                supplied_storeys = list(storeys)
            except TypeError as error:
                raise TypeError(
                    "storeys must be a sequence of Storey objects"
                ) from error
            normalised_storeys = []
            seen_storeys: set[int] = set()
            for index, storey in enumerate(supplied_storeys, start=1):
                if not isinstance(storey, Storey):
                    raise TypeError(f"storey {index} must be a Storey")
                if storey.house is not house:
                    raise ValueError(f"storey {index} must belong to this house")
                if storey.element.id() in seen_storeys:
                    raise ValueError(f"storey {index} is duplicated")
                seen_storeys.add(storey.element.id())
                normalised_storeys.append(storey)
            self._storeys = tuple(normalised_storeys)

        model = house.model
        self.element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=name,
            predefined_type="DRAWING",
        )

        placement = np.eye(4)
        if self.view == "elevation":
            direction_vector = np.array(self.direction)
            camera_z = -direction_vector
            camera_y = np.array((0.0, 0.0, 1.0))
            camera_x = np.cross(camera_y, camera_z)
            placement[:3, 0] = camera_x
            placement[:3, 1] = camera_y
            placement[:3, 2] = camera_z
        placement[0, 3] = self.x
        placement[1, 3] = self.y
        placement[2, 3] = self.z
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=self.element,
            matrix=placement,
            is_si=True,
        )

        # Bonsai persists an orthographic camera as a rectangular viewing box:
        # the local X/Y extents are its frame and local negative Z is its view
        # depth.  Loader.create_camera reconstructs the Blender camera from it.
        r = self.radius
        depth = (
            max(10.0, hypot(self.x, self.y) + 2 * self.radius)
            if self.view == "elevation"
            else max(10.0, abs(self.z) + 10.0)
        )
        vertices = [
            (-r, -r, -depth),
            (-r, -r, 0.0),
            (-r, r, -depth),
            (-r, r, 0.0),
            (r, -r, -depth),
            (r, -r, 0.0),
            (r, r, -depth),
            (r, r, 0.0),
        ]
        faces = [
            (0, 1, 3, 2),
            (2, 3, 7, 6),
            (6, 7, 5, 4),
            (4, 5, 1, 0),
            (2, 6, 4, 0),
            (7, 3, 1, 5),
        ]
        representation = ifcopenshell.api.geometry.add_mesh_representation(
            model,
            context=house._body_context,
            vertices=[vertices],
            faces=[faces],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=self.element,
            representation=representation,
        )

        self.group = ifcopenshell.api.group.add_group(model, name=name)
        ifcopenshell.api.group.edit_group(
            model,
            group=self.group,
            attributes={"Name": name, "ObjectType": "DRAWING"},
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[self.element],
        )
        plan_annotations = (
            [
                annotation
                for annotation in house._plan_annotations
                if self._includes_storey_element(
                    ifcopenshell.util.element.get_container(annotation)
                )
            ]
            if self.view == "plan"
            else []
        )
        if plan_annotations:
            ifcopenshell.api.group.assign_group(
                model,
                group=self.group,
                products=plan_annotations,
            )

        project_dir = Path(__file__).resolve().parent
        drawing_assets = project_dir / "drawings" / "assets"
        self._drawing_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=self.element,
            name="EPset_Drawing",
        )
        drawing_properties = {
            "TargetView": (
                "PLAN_VIEW" if self.view == "plan" else "ELEVATION_VIEW"
            ),
            "Scale": "1/100",
            "HumanScale": "1:100",
            "HasUnderlay": False,
            "HasLinework": True,
            "HasAnnotation": self.view == "plan",
            "GlobalReferencing": True,
            "DPI": 96,
            "LineworkMode": "OPENCASCADE",
            # Elevations need closed projected surfaces so material styling
            # can fill elements which lie behind the section plane.  Plans
            # retain their existing linework-only projection behaviour.
            "FillMode": "SHAPELY" if self.view == "elevation" else "NONE",
            "CutMode": "BISECT",
            "Stylesheet": str(project_dir / "bonsai_scripts" / "assets" / "plan.css"),
            "Markers": str(drawing_assets / "markers.svg"),
            "Symbols": str(drawing_assets / "symbols.svg"),
            "Patterns": str(drawing_assets / "patterns.svg"),
            # These drawings use OpenCascade linework without a raster
            # underlay.  Avoid applying Bonsai's stock viewport style: its
            # many Blender render-property assignments are unnecessary here
            # and can occasionally deadlock while activating the camera.
            "ShadingStyles": str(
                project_dir
                / "bonsai_scripts"
                / "assets"
                / "linework_shading_styles.json"
            ),
            "CurrentShadingStyle": "Technical",
            "DoorsClosed": self.doors_closed,
            "RightPanelWidth": self.right_panel_width,
            "RightPanelTables": "[]",
        }
        if not self._includes_all_storeys:
            drawing_properties["Include"] = (
                "+".join(
                    f'location="{storey.element.GlobalId}"'
                    for storey in self._storeys
                )
                # A deliberately nonexistent IFC GUID makes an explicitly
                # empty storey list select no model elements in Bonsai.
                or "0000000000000000000000"
            )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=self._drawing_pset,
            properties=drawing_properties,
        )

        self.information = ifcopenshell.api.document.add_information(model)
        ifcopenshell.api.document.edit_information(
            model,
            information=self.information,
            attributes={
                "Identification": "X",
                "Name": name,
                "Scope": "DRAWING",
            },
        )
        self.document = ifcopenshell.api.document.add_reference(
            model,
            information=self.information,
        )
        safe_name = "".join(character for character in name if character.isalnum() or character in "._- ")
        ifcopenshell.api.document.edit_reference(
            model,
            reference=self.document,
            attributes={"Location": f"drawings/{safe_name}.svg"},
        )
        ifcopenshell.api.document.assign_document(
            model,
            products=[self.element],
            document=self.document,
        )

        if self._automatic_door_annotations:
            for door in model.by_type("IfcDoor"):
                storey = ifcopenshell.util.element.get_container(door)
                if self._includes_storey_element(storey):
                    self.add_door_annotation(
                        door,
                        offset=self._door_annotation_offset,
                    )

    @property
    def storeys(self) -> tuple[Storey, ...]:
        """Return the explicitly selected storeys, or all current storeys."""
        if self._includes_all_storeys:
            return tuple(self.house._storeys)
        return self._storeys

    @property
    def includes_all_storeys(self) -> bool:
        """Return whether this drawing uses the default all-storeys scope."""
        return self._includes_all_storeys

    def _includes_storey(self, storey: Storey) -> bool:
        return self._includes_all_storeys or storey in self._storeys

    def _includes_storey_element(
        self,
        storey: ifcopenshell.entity_instance | None,
    ) -> bool:
        return self._includes_all_storeys or any(
            selected.element == storey for selected in self._storeys
        )

    def _require_plan_view(self, operation: str) -> None:
        if self.view != "plan":
            raise ValueError(f"{operation} is only supported for plan drawings")

    def _include_model_element(
        self,
        element: ifcopenshell.entity_instance,
    ) -> None:
        """Add one model element to an explicitly filtered drawing."""
        if self._includes_all_storeys:
            return
        include = ifcopenshell.util.element.get_pset(
            self.element,
            "EPset_Drawing",
            "Include",
        )
        if include is None:
            include = element.GlobalId
        elif element.GlobalId in include.split("+"):
            return
        else:
            include = f"{include}+{element.GlobalId}"
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=self._drawing_pset,
            properties={"Include": include},
        )

    def add_material_legend(
        self,
        items: Sequence[tuple[str, str]],
        *,
        title: str = "LEGENDA MATERIÁLŮ",
    ) -> Drawing:
        """Add a pattern-and-description table to the right-side panel.

        ``items`` contains ``(pattern, description)`` pairs.  Pattern names
        come from ``drawings/assets/patterns.svg``, for example
        ``"diagonal1"``, ``"crosshatch1"``, ``"brick"``, ``"concrete"``,
        or ``"wood"``.  Use explicit newlines in descriptions to control line
        wrapping.  Tables are stacked from the top of the panel in call order
        and are persisted in ``EPset_Drawing``.
        """
        if self.right_panel_width <= 0:
            raise ValueError(
                "add_material_legend requires right_panel_width on the drawing"
            )
        if self.right_panel_width < 40:
            raise ValueError(
                "right_panel_width must be at least 40 mm for a material legend"
            )
        title = _name(title, "title")
        if isinstance(items, (str, bytes)):
            raise TypeError(
                "items must be a sequence of pattern-description pairs"
            )
        try:
            supplied_items = list(items)
        except TypeError as error:
            raise TypeError(
                "items must be a sequence of pattern-description pairs"
            ) from error
        if not supplied_items:
            raise ValueError("items must contain at least one material")

        available_patterns = _drawing_pattern_ids()
        normalised_items = []
        for index, supplied_item in enumerate(supplied_items, start=1):
            if isinstance(supplied_item, (str, bytes)):
                raise TypeError(
                    f"item {index} must contain a pattern and description"
                )
            try:
                pattern, description = supplied_item
            except (TypeError, ValueError) as error:
                raise TypeError(
                    f"item {index} must contain a pattern and description"
                ) from error
            pattern = _name(pattern, f"item {index} pattern")
            description = _name(description, f"item {index} description")
            if pattern not in available_patterns:
                raise ValueError(
                    f'item {index} pattern "{pattern}" is not available; '
                    f"choose one of: {', '.join(sorted(available_patterns))}"
                )
            normalised_items.append(
                {"pattern": pattern, "description": description}
            )

        self._right_panel_tables.append(
            {
                "kind": "material_legend",
                "title": title,
                "items": normalised_items,
            }
        )
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=self._drawing_pset,
            properties={
                "RightPanelTables": json.dumps(
                    self._right_panel_tables,
                    ensure_ascii=False,
                )
            },
        )
        return self

    def add_dimension(
        self,
        start: Point,
        end: Point,
        *,
        offset: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add one linear plan dimension scoped only to this drawing.

        ``start`` and ``end`` are the measured points in global model XY
        coordinates.  ``offset`` moves the dimension line to its left when
        positive and to its right when negative, looking from ``start`` to
        ``end``.  Coordinates and offset are metres; Bonsai displays the
        measured value in millimetres.  A non-zero offset adds extension lines
        from the measured points to 1 mm beyond the dimension line at 1:100.
        """
        self._require_plan_view("add_dimension")
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        offset = _number(offset, "offset")
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("dimension start and end must be different points")

        self._dimension_count += 1
        dimension_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} Dimension {self._dimension_count}"
        )
        normal_x = -delta_y / length
        normal_y = delta_x / length
        offset_x = normal_x * offset
        offset_y = normal_y * offset
        dimension_start = (start_x + offset_x, start_y + offset_y)
        dimension_end = (end_x + offset_x, end_y + offset_y)

        selected_storeys_below = [
            storey for storey in self.storeys if storey.elevation <= self.z
        ]
        annotation_z = (
            max(
                selected_storeys_below,
                key=lambda storey: storey.elevation,
            ).elevation
            if selected_storeys_below
            else 0.0
        )
        placement = np.eye(4)
        placement[2, 3] = annotation_z

        model = self.house.model
        dimension = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=dimension_name,
            predefined_type="DIMENSION",
        )
        dimension_representation = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._annotation_context,
            axis=[dimension_start, dimension_end],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=dimension,
            representation=dimension_representation,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=dimension,
            matrix=placement,
            is_si=True,
        )

        dimension_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=dimension,
            name="BBIM_Dimension",
        )
        unit_choices = (
            "Feet and Inches - Fractional",
            "Feet - Decimal",
            "Inches - Fractional",
            "Inches - Decimal",
            "Meters",
            "Decimeters",
            "Centimeters",
            "Millimeters",
        )
        unit_enumeration = model.createIfcPropertyEnumeration(
            "CustomUnit",
            [model.createIfcText(unit) for unit in unit_choices],
            None,
        )
        custom_unit = model.createIfcPropertyEnumeratedValue(
            "CustomUnit",
            None,
            [model.createIfcText("Millimeters")],
            unit_enumeration,
        )
        dimension_pset.HasProperties = (
            *(dimension_pset.HasProperties or ()),
            custom_unit,
        )

        drawing_products = [dimension]
        if offset != 0:
            extension_direction = 1.0 if offset > 0 else -1.0
            # Model-space equivalent of 1 mm on this fixed 1:100 drawing.
            extension_length = 0.1
            beyond_x = normal_x * extension_direction * extension_length
            beyond_y = normal_y * extension_direction * extension_length
            extension_curves = []
            for measured_point, dimension_point in (
                ((start_x, start_y), dimension_start),
                ((end_x, end_y), dimension_end),
            ):
                point_list = model.createIfcCartesianPointList2D(
                    [
                        measured_point,
                        (
                            dimension_point[0] + beyond_x,
                            dimension_point[1] + beyond_y,
                        ),
                    ]
                )
                extension_curves.append(
                    model.createIfcIndexedPolyCurve(point_list, None, False)
                )
            extension = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcAnnotation",
                name=f"{dimension_name} Extension Lines",
                predefined_type="LINEWORK",
            )
            extension_representation = model.createIfcShapeRepresentation(
                self.house._annotation_context,
                "Annotation",
                "GeometricCurveSet",
                [model.createIfcGeometricCurveSet(extension_curves)],
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=extension,
                representation=extension_representation,
            )
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=extension,
                matrix=placement.copy(),
                is_si=True,
            )
            extension_pset = ifcopenshell.api.pset.add_pset(
                model,
                product=extension,
                name="EPset_Annotation",
            )
            ifcopenshell.api.pset.edit_pset(
                model,
                pset=extension_pset,
                properties={"Classes": "dimension-extension fine"},
            )
            drawing_products.append(extension)

        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=drawing_products,
        )
        return dimension

    def add_room_annotation(
        self,
        position: Point,
        *,
        identifier: str,
        area: Number,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a manual room identifier and area label to this drawing.

        ``position`` is the global model XY coordinate at the centre of the
        separator line.  ``area`` is supplied in square metres and displayed
        with two decimal places and a square-metre suffix.  This helper does
        not create an ``IfcSpace`` or calculate area from room boundaries.
        """
        self._require_plan_view("add_room_annotation")
        x, y = _point(position, "position")
        identifier = _name(identifier, "identifier")
        area = _number(area, "area")
        if area <= 0:
            raise ValueError("area must be greater than zero")

        annotation_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} Room {identifier}"
        )
        selected_storeys_below = [
            storey for storey in self.storeys if storey.elevation <= self.z
        ]
        annotation_z = (
            max(
                selected_storeys_below,
                key=lambda storey: storey.elevation,
            ).elevation
            if selected_storeys_below
            else 0.0
        )
        model = self.house.model

        def create_text_annotation(
            text_name: str,
            literal_value: str,
            vertical_offset: float,
            classes: str,
        ) -> ifcopenshell.entity_instance:
            annotation = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcAnnotation",
                name=text_name,
                predefined_type="TEXT",
            )
            placement = np.eye(4)
            placement[:3, 3] = (x, y + vertical_offset, annotation_z)
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=annotation,
                matrix=placement,
                is_si=True,
            )
            literal_origin = model.createIfcAxis2Placement3D(
                model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
                model.createIfcDirection((0.0, 0.0, 1.0)),
                model.createIfcDirection((1.0, 0.0, 0.0)),
            )
            literal = model.createIfcTextLiteralWithExtent(
                literal_value,
                literal_origin,
                "RIGHT",
                model.createIfcPlanarExtent(1.0, 1.0),
                "center",
            )
            representation = model.createIfcShapeRepresentation(
                self.house._annotation_context,
                "Annotation",
                "Annotation2D",
                [literal],
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=annotation,
                representation=representation,
            )
            pset = ifcopenshell.api.pset.add_pset(
                model,
                product=annotation,
                name="EPset_Annotation",
            )
            ifcopenshell.api.pset.edit_pset(
                model,
                pset=pset,
                properties={"Classes": classes},
            )
            return annotation

        identifier_annotation = create_text_annotation(
            annotation_name,
            identifier,
            0.18,
            "room-annotation room-identifier",
        )
        area_text = f"{area:.2f}".replace(".", ",") + " m²"
        area_annotation = create_text_annotation(
            f"{annotation_name} Area",
            area_text,
            -0.15,
            "room-annotation room-area",
        )
        metadata = ifcopenshell.api.pset.add_pset(
            model,
            product=identifier_annotation,
            name="EPset_RoomAnnotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=metadata,
            properties={"Identifier": identifier, "Area": area},
        )

        line_width = max(0.75, len(identifier) * 0.18)
        separator = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{annotation_name} Separator",
            predefined_type="LINEWORK",
        )
        separator_representation = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._annotation_context,
            axis=[
                (x - line_width / 2, y),
                (x + line_width / 2, y),
            ],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=separator,
            representation=separator_representation,
        )
        separator_placement = np.eye(4)
        separator_placement[2, 3] = annotation_z
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=separator,
            matrix=separator_placement,
            is_si=True,
        )
        separator_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=separator,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=separator_pset,
            properties={"Classes": "room-annotation-separator"},
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[identifier_annotation, area_annotation, separator],
        )
        return identifier_annotation

    def add_entrance_arrow(
        self,
        position: Point,
        *,
        rotation: Number = 0,
        size: Number = 0.6,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a drawing-specific arrow marking the building entrance.

        ``position`` is the arrow centre in global model XY coordinates.
        ``rotation`` is measured counter-clockwise in degrees; zero points
        right and 180 points left.  ``size`` is the arrow length in metres.
        """
        self._require_plan_view("add_entrance_arrow")
        x, y = _point(position, "position")
        rotation = _number(rotation, "rotation")
        size = _number(size, "size")
        if size <= 0:
            raise ValueError("size must be greater than zero")

        self._entrance_arrow_count += 1
        annotation_name = (
            _name(name, "name")
            if name is not None
            else (
                f"{self.name} Entrance Arrow "
                f"{self._entrance_arrow_count}"
            )
        )
        selected_storeys_below = [
            storey for storey in self.storeys if storey.elevation <= self.z
        ]
        annotation_z = (
            max(
                selected_storeys_below,
                key=lambda storey: storey.elevation,
            ).elevation
            if selected_storeys_below
            else 0.0
        )

        model = self.house.model
        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=annotation_name,
            predefined_type="LINEWORK",
        )
        half_length = size / 2
        arrow_curves = [
            model.createIfcIndexedPolyCurve(
                model.createIfcCartesianPointList2D(
                    [(-half_length, 0.0), (half_length, 0.0)]
                ),
                None,
                False,
            ),
            model.createIfcIndexedPolyCurve(
                model.createIfcCartesianPointList2D(
                    [
                        (size * 0.15, -size * 0.35),
                        (half_length, 0.0),
                        (size * 0.15, size * 0.35),
                    ]
                ),
                None,
                False,
            ),
        ]
        representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "GeometricCurveSet",
            [model.createIfcGeometricCurveSet(arrow_curves)],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=representation,
        )
        angle = radians(rotation)
        placement = np.eye(4)
        placement[:3, 0] = (cos(angle), sin(angle), 0.0)
        placement[:3, 1] = (-sin(angle), cos(angle), 0.0)
        placement[:3, 3] = (x, y, annotation_z)
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=placement,
            is_si=True,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={"Classes": "entrance-arrow"},
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[annotation],
        )
        return annotation

    def add_door_annotation(
        self,
        door: ifcopenshell.entity_instance,
        *,
        offset: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a drawing-specific ``width/height`` label for ``door``.

        The values come from ``IfcDoor.OverallWidth`` and ``OverallHeight``
        and are displayed in millimetres on two lines with a separator between
        them.  The label is placed inside the plan swing and oriented across
        the wall.  ``offset`` moves it farther into the swing, in model metres;
        a negative value moves it toward the wall.
        """
        self._require_plan_view("add_door_annotation")
        if not isinstance(door, ifcopenshell.entity_instance) or not door.is_a(
            "IfcDoor"
        ):
            raise TypeError("door must be an IfcDoor created by Wall.add_door")
        if door.file is not self.house.model:
            raise ValueError("door must belong to this house")
        if door.id() in self._annotated_doors:
            raise ValueError("door already has an annotation in this drawing")

        storey = ifcopenshell.util.element.get_container(door)
        if storey is None or not storey.is_a("IfcBuildingStorey"):
            raise ValueError("door must belong to a building storey")
        if not self._includes_storey_element(storey):
            raise ValueError("door storey is not included in this drawing")
        if door.OverallWidth is None or door.OverallHeight is None:
            raise ValueError("door must define OverallWidth and OverallHeight")
        width = float(door.OverallWidth)
        clear_height = ifcopenshell.util.element.get_pset(
            door,
            "EPset_Door",
            "ClearHeight",
        )
        height = float(
            door.OverallHeight if clear_height is None else clear_height
        )
        offset = _number(offset, "offset")

        plan = ifcopenshell.util.representation.get_representation(
            door,
            "Plan",
            "Body",
            "PLAN_VIEW",
        )
        if plan is None:
            raise ValueError("door has no plan representation")
        y_coordinates = [
            float(point[1])
            for item in plan.Items
            if item.is_a("IfcIndexedPolyCurve")
            for point in item.Points.CoordList
        ]
        if not y_coordinates:
            raise ValueError("door plan representation has no swing geometry")
        swing_y = max(y_coordinates, key=abs)
        swing_sign = 1.0 if swing_y >= 0 else -1.0
        # Swinging leaves reach approximately one door width into the room.
        # Sliding-door plan geometry does not, so ensure that its label still
        # clears the wall lining.
        label_y = swing_y * 0.55 + swing_sign * offset
        if abs(label_y) < 0.2:
            label_y = swing_sign * (0.2 + offset)

        door_placement = ifcopenshell.util.placement.get_local_placement(
            door.ObjectPlacement
        )
        label_point = door_placement @ np.array(
            (width / 2, label_y, 0.0, 1.0),
            dtype=float,
        )
        placement = np.eye(4)
        placement[:3, 0] = swing_sign * door_placement[:3, 1]
        placement[:3, 1] = -swing_sign * door_placement[:3, 0]
        # Keep labels readable when the host wall was drawn in the opposite
        # direction: horizontal text runs left-to-right and vertical text uses
        # a consistent bottom-to-top orientation in the finished plan.
        if (
            placement[0, 0] < -1e-9
            or abs(placement[0, 0]) <= 1e-9
            and placement[1, 0] < 0
        ):
            placement[:3, 0] *= -1
            placement[:3, 1] *= -1
        placement[:3, 2] = door_placement[:3, 2]
        placement[:3, 3] = label_point[:3]
        separator_placement = placement.copy()

        model = self.house.model
        annotation_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} {door.Name or 'Door'} Dimensions"
        )
        text_extent = max(width, 0.5)

        def create_text_annotation(
            text_name: str,
            value: int,
            text_placement: np.ndarray,
            classes: str,
        ) -> ifcopenshell.entity_instance:
            text_annotation = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcAnnotation",
                name=text_name,
                predefined_type="TEXT",
            )
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=text_annotation,
                matrix=text_placement,
                is_si=True,
            )
            literal_origin = model.createIfcAxis2Placement3D(
                model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
                model.createIfcDirection((0.0, 0.0, 1.0)),
                model.createIfcDirection((1.0, 0.0, 0.0)),
            )
            literal = model.createIfcTextLiteralWithExtent(
                str(value),
                literal_origin,
                "RIGHT",
                model.createIfcPlanarExtent(text_extent, text_extent),
                "center",
            )
            representation = model.createIfcShapeRepresentation(
                self.house._annotation_context,
                "Annotation",
                "Annotation2D",
                [literal],
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=text_annotation,
                representation=representation,
            )
            pset = ifcopenshell.api.pset.add_pset(
                model,
                product=text_annotation,
                name="EPset_Annotation",
            )
            ifcopenshell.api.pset.edit_pset(
                model,
                pset=pset,
                properties={"Classes": classes},
            )
            return text_annotation

        # Separate products are necessary because Bonsai intentionally lays
        # multiple text literals out at a fixed one-em spacing.
        width_placement = placement.copy()
        width_placement[:3, 3] += placement[:3, 1] * 0.12
        height_placement = placement.copy()
        height_placement[:3, 3] -= placement[:3, 1] * 0.15
        annotation = create_text_annotation(
            annotation_name,
            round(width * 1000),
            width_placement,
            "door-dimension door-dimension-width small",
        )
        height_annotation = create_text_annotation(
            f"{annotation_name} Height",
            round(height * 1000),
            height_placement,
            "door-dimension door-dimension-height small",
        )

        separator = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{annotation_name} Separator",
            predefined_type="LINEWORK",
        )
        separator_direction = float(
            np.dot(placement[:3, 0], door_placement[:3, 1])
        )
        separator_start, separator_end = sorted(
            separator_direction * (y - label_y)
            for y in (min(y_coordinates), max(y_coordinates))
        )
        separator_representation = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._annotation_context,
            axis=[
                (separator_start, 0.0),
                (separator_end, 0.0),
            ],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=separator,
            representation=separator_representation,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=separator,
            matrix=separator_placement,
            is_si=True,
        )
        separator_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=separator,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=separator_pset,
            properties={"Classes": "door-dimension-separator"},
        )
        ifcopenshell.api.drawing.assign_product(
            model,
            relating_product=door,
            related_object=annotation,
        )
        ifcopenshell.api.drawing.assign_product(
            model,
            relating_product=door,
            related_object=height_annotation,
        )
        ifcopenshell.api.drawing.assign_product(
            model,
            relating_product=door,
            related_object=separator,
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[annotation, height_annotation, separator],
        )
        self._annotated_doors.add(door.id())
        return annotation

    def add_batting(
        self,
        start: Point,
        end: Point,
        *,
        thickness: Number,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a batting annotation scoped only to this drawing."""
        self._require_plan_view("add_batting")
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("batting start and end must be different points")

        self._batting_count += 1
        annotation = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcAnnotation",
            name=(
                _name(name, "name")
                if name is not None
                else f"{self.name} Batting {self._batting_count}"
            ),
            predefined_type="BATTING",
        )

        storeys_below = [storey for storey in self.house._storeys if storey.elevation <= self.z]
        annotation_z = (
            max(storeys_below, key=lambda storey: storey.elevation).elevation
            if storeys_below
            else 0.0
        )
        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = annotation_z
        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=annotation,
            matrix=placement,
            is_si=True,
        )

        representation = ifcopenshell.api.geometry.add_axis_representation(
            self.house.model,
            context=self.house._annotation_context,
            axis=[(0.0, 0.0), (length, 0.0)],
        )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model,
            product=annotation,
            representation=representation,
        )
        pset = ifcopenshell.api.pset.add_pset(
            self.house.model,
            product=annotation,
            name="BBIM_Batting",
        )
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=pset,
            properties={"Thickness": thickness},
        )
        ifcopenshell.api.group.assign_group(
            self.house.model,
            group=self.group,
            products=[annotation],
        )
        return annotation

    def add_chimney_annotation(
        self,
        chimney: Chimney,
        *,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add the chimney body and its flue symbol to this drawing.

        If the chimney is spatially contained in a different storey, its
        GlobalId is added to this drawing's inclusion selector.  This lets one
        continuous multistorey chimney be cut in every annotated floor plan.
        """
        self._require_plan_view("add_chimney_annotation")
        if not isinstance(chimney, Chimney):
            raise TypeError("chimney must be a Chimney created by Storey.chimney")
        if chimney.file is not self.house.model:
            raise ValueError("chimney must belong to this house")
        if chimney.id() in self._annotated_chimneys:
            raise ValueError("chimney already has an annotation in this drawing")

        chimney_storey = ifcopenshell.util.element.get_container(chimney)
        if not self._includes_storey_element(chimney_storey):
            self._include_model_element(chimney)

        annotation_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} {chimney.Name} Flue Symbol"
        )
        model = self.house.model
        radius = chimney.flue_diameter / 2
        circle_points = [
            (
                radius * cos(radians(index * 360 / 32)),
                radius * sin(radians(index * 360 / 32)),
            )
            for index in range(33)
        ]

        fill = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{annotation_name} Fill",
            predefined_type="FILLAREA",
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=fill,
            matrix=chimney.placement.copy(),
            is_si=True,
        )
        fill_points = [
            (
                radius * cos(radians(45 + index * 180 / 16)),
                radius * sin(radians(45 + index * 180 / 16)),
            )
            for index in range(17)
        ]
        fill_points.append(fill_points[0])
        fill_curve = model.createIfcIndexedPolyCurve(
            model.createIfcCartesianPointList2D(fill_points),
            None,
            False,
        )
        fill_area = model.createIfcAnnotationFillArea(fill_curve, None)
        fill_representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "Annotation2D",
            [fill_area],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=fill,
            representation=fill_representation,
        )
        fill_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=fill,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=fill_pset,
            properties={"Classes": "chimney-flue-fill"},
        )

        outline = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=annotation_name,
            predefined_type="LINEWORK",
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=outline,
            matrix=chimney.placement.copy(),
            is_si=True,
        )
        outline_curve = model.createIfcIndexedPolyCurve(
            model.createIfcCartesianPointList2D(circle_points),
            None,
            False,
        )
        outline_representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "GeometricCurveSet",
            [model.createIfcGeometricCurveSet([outline_curve])],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=outline,
            representation=outline_representation,
        )
        outline_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=outline,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=outline_pset,
            properties={"Classes": "chimney-flue"},
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[fill, outline],
        )
        self._annotated_chimneys.add(chimney.id())
        return outline

    def add_stair_annotation(
        self,
        stair: Stair,
        *,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a conventional plan symbol for ``stair`` to this drawing only.

        The annotation contains the stair outline, tread lines, an upward
        walking-direction arrow.  It does not alter the stair's 3D
        representation.
        """
        self._require_plan_view("add_stair_annotation")
        if not isinstance(stair, Stair):
            raise TypeError("stair must be a Stair created by Storey.stair")
        if stair.file is not self.house.model:
            raise ValueError("stair must belong to this house")
        if stair.id() in self._annotated_stairs:
            raise ValueError("stair already has an annotation in this drawing")

        annotation_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} {stair.Name} Plan Symbol"
        )
        model = self.house.model
        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=annotation_name,
            predefined_type="LINEWORK",
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=stair.placement.copy(),
            is_si=True,
        )

        half_width = stair.width / 2
        tread_length = stair.tread_length
        polylines: list[list[tuple[float, float]]] = [
            [
                (0.0, -half_width),
                (stair.length, -half_width),
                (stair.length, half_width),
                (0.0, half_width),
                (0.0, -half_width),
            ]
        ]
        for tread in range(1, stair.treads):
            x = tread * tread_length
            polylines.append([(x, -half_width), (x, half_width)])

        arrow_start = min(tread_length / 2, stair.length * 0.1)
        arrow_end = stair.length * 0.85
        arrow_size = min(stair.width * 0.18, stair.length * 0.06)
        polylines.extend(
            [
                [(arrow_start, 0.0), (arrow_end, 0.0)],
                [
                    (arrow_end - arrow_size, -arrow_size),
                    (arrow_end, 0.0),
                    (arrow_end - arrow_size, arrow_size),
                ],
            ]
        )

        curves = []
        for points in polylines:
            point_list = model.createIfcCartesianPointList2D(points)
            curves.append(model.createIfcIndexedPolyCurve(point_list, None, False))
        representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "GeometricCurveSet",
            [model.createIfcGeometricCurveSet(curves)],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=representation,
        )
        annotation_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=annotation_pset,
            properties={"Classes": "stair"},
        )

        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[annotation],
        )
        self._annotated_stairs.add(stair.id())
        return annotation

    def render(
        self,
        output: str | PathLike[str],
        *,
        png: bool = False,
        png_dpi: Number = 200,
        blender: str | PathLike[str] = "blender",
        inkscape: str | PathLike[str] = "inkscape",
        stylesheet: str | PathLike[str] | None = None,
    ) -> Path:
        """Render through Blender/Bonsai; ``png_dpi`` controls optional PNG resolution."""
        if self.house._ifc_path is None:
            raise RuntimeError("write the house before rendering a drawing")

        output_path = Path(output)
        absolute_output = output_path.resolve()
        stylesheet_path = (
            Path(stylesheet)
            if stylesheet is not None
            else Path(__file__).resolve().parent / "bonsai_scripts" / "assets" / "plan.css"
        ).resolve()
        if not stylesheet_path.is_file():
            raise FileNotFoundError(f"drawing stylesheet not found: {stylesheet_path}")

        ifcopenshell.api.document.edit_reference(
            self.house.model,
            reference=self.document,
            attributes={"Location": str(absolute_output)},
        )
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=self._drawing_pset,
            properties={"Stylesheet": str(stylesheet_path)},
        )
        self.house.model.write(str(self.house._ifc_path))
        return _render_existing_drawing(
            self.house._ifc_path,
            self.element.GlobalId,
            output_path,
            png=png,
            png_dpi=png_dpi,
            blender=blender,
            inkscape=inkscape,
        )


class Beam(ifcopenshell.entity_instance):
    """A rectangular ``IfcBeam`` spanning two world-coordinate points."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        size: tuple[float, float],
        length: float,
        kind: str,
        material_name: str,
        rotation: float,
        height_axis: tuple[float, float, float],
        cuts: tuple[PlaneCut, ...],
        placement: np.ndarray,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "width", size[0])
        object.__setattr__(self, "height", size[1])
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "material_name", material_name)
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "height_axis", height_axis)
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "placement", placement)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this beam as its underlying IFC entity."""
        return self


class FacadeLayer(ifcopenshell.entity_instance):
    """One opening-aware ``IfcCovering`` used as exterior cladding."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        wall: Wall,
        *,
        side: str,
        offset: float,
        thickness: float,
        start_height: float,
        height: float,
        length: float,
        start_extension: float,
        end_extension: float,
        material_name: str,
        trim_openings: bool,
        opening_walls: tuple[Wall, ...],
        space_before_openings: float,
        space_after_openings: float,
        space_above_openings: float,
        space_below_openings: float,
        openings: tuple[ifcopenshell.entity_instance, ...],
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "wall", wall)
        object.__setattr__(self, "storey", wall.storey)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "start_extension", start_extension)
        object.__setattr__(self, "end_extension", end_extension)
        object.__setattr__(self, "material_name", material_name)
        object.__setattr__(self, "trim_openings", trim_openings)
        object.__setattr__(self, "opening_walls", opening_walls)
        object.__setattr__(self, "space_before_openings", space_before_openings)
        object.__setattr__(self, "space_after_openings", space_after_openings)
        object.__setattr__(self, "space_above_openings", space_above_openings)
        object.__setattr__(self, "space_below_openings", space_below_openings)
        object.__setattr__(self, "openings", openings)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this layer as its underlying IFC covering."""
        return self


class HorizontalFrame(ifcopenshell.entity_instance):
    """An ``IfcElementAssembly`` of horizontal wall-spanning laths."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        wall: Wall,
        *,
        side: str,
        offset: float,
        width: float,
        depth: float,
        gap: float,
        length: float,
        lath_offsets: tuple[float, ...],
        lath_positions: tuple[float, ...],
        start_extension: float,
        end_extension: float,
        trim_openings: bool,
        space_before_openings: float,
        space_after_openings: float,
        space_above_openings: float,
        space_below_openings: float,
        insulation_material: str | None,
        insulation_blocks: tuple[ifcopenshell.entity_instance, ...],
        members: tuple[ifcopenshell.entity_instance, ...],
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "wall", wall)
        object.__setattr__(self, "storey", wall.storey)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "depth", depth)
        object.__setattr__(self, "gap", gap)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "lath_offsets", lath_offsets)
        object.__setattr__(self, "lath_positions", lath_positions)
        object.__setattr__(self, "start_extension", start_extension)
        object.__setattr__(self, "end_extension", end_extension)
        object.__setattr__(self, "trim_openings", trim_openings)
        object.__setattr__(self, "space_before_openings", space_before_openings)
        object.__setattr__(self, "space_after_openings", space_after_openings)
        object.__setattr__(self, "space_above_openings", space_above_openings)
        object.__setattr__(self, "space_below_openings", space_below_openings)
        object.__setattr__(self, "insulation_material", insulation_material)
        object.__setattr__(self, "insulation_blocks", insulation_blocks)
        object.__setattr__(self, "members", members)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this frame as its underlying IFC assembly."""
        return self


class VerticalFrame(ifcopenshell.entity_instance):
    """An ``IfcElementAssembly`` of regularly spaced vertical laths."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        wall: Wall,
        *,
        side: str,
        offset: float,
        width: float,
        depth: float,
        start_height: float,
        height: float,
        gap: float,
        lath_offsets: tuple[float, ...],
        lath_positions: tuple[float, ...],
        space_before_openings: float,
        space_after_openings: float,
        space_above_openings: float,
        space_below_openings: float,
        insulation_material: str | None,
        insulation_blocks: tuple[ifcopenshell.entity_instance, ...],
        members: tuple[ifcopenshell.entity_instance, ...],
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "wall", wall)
        object.__setattr__(self, "storey", wall.storey)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "depth", depth)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "gap", gap)
        object.__setattr__(self, "lath_offsets", lath_offsets)
        object.__setattr__(self, "lath_positions", lath_positions)
        object.__setattr__(self, "space_before_openings", space_before_openings)
        object.__setattr__(self, "space_after_openings", space_after_openings)
        object.__setattr__(self, "space_above_openings", space_above_openings)
        object.__setattr__(self, "space_below_openings", space_below_openings)
        object.__setattr__(self, "insulation_material", insulation_material)
        object.__setattr__(self, "insulation_blocks", insulation_blocks)
        object.__setattr__(self, "members", members)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this frame as its underlying IFC assembly."""
        return self


class Roof(ifcopenshell.entity_instance):
    """An ``IfcRoof`` aggregate containing planes and other roof elements."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "_planes", [])

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this roof as its underlying IFC entity."""
        return self

    @property
    def planes(self) -> tuple[RoofPlane, ...]:
        """Return the coordinate planes created beneath this roof."""
        return tuple(self._planes)

    def add(
        self,
        *elements: ifcopenshell.entity_instance,
    ) -> ifcopenshell.entity_instance:
        """Aggregate existing IFC elements beneath this roof."""
        if not elements:
            raise ValueError("roof.add requires at least one element")
        normalised = []
        for index, element in enumerate(elements, start=1):
            if not isinstance(element, ifcopenshell.entity_instance) or not element.is_a(
                "IfcElement"
            ):
                raise TypeError(f"element {index} must be an IfcElement")
            if element.file is not self.file:
                raise ValueError(f"element {index} must belong to this house")
            if element == self:
                raise ValueError("a roof cannot aggregate itself")
            normalised.append(element)
        return ifcopenshell.api.aggregate.assign_object(
            self.file,
            products=normalised,
            relating_object=self,
        )

    def plane(
        self,
        name: str,
        *,
        points: Sequence[Point3D],
        cuts: Sequence[PlaneCut] | None = None,
    ) -> RoofPlane:
        """Create a roof-local frame from three global points.

        The first point is the origin, the second defines local positive X,
        and the third defines the roof plane and approximate positive Y.  Y is
        orthogonalised against X.  The perpendicular offset axis is flipped
        when necessary so positive local Z always has a positive global Z
        component, without changing the supplied X or Y directions.  ``cuts``
        are global three-point planes inherited by elements created through
        the returned plane.
        """
        plane_name = _name(name, "name")
        if any(plane.Name == plane_name for plane in self._planes):
            raise ValueError(f'roof plane name already exists: "{plane_name}"')
        if isinstance(points, (str, bytes)):
            raise TypeError("points must contain exactly three points")
        try:
            supplied_points = list(points)
        except TypeError as error:
            raise TypeError("points must contain exactly three points") from error
        if len(supplied_points) != 3:
            raise TypeError("points must contain exactly three points")
        origin, x_point, y_point = (
            _point_3d(point, f"point {index}")
            for index, point in enumerate(supplied_points, start=1)
        )
        origin_vector = np.array(origin, dtype=float)
        x_direction = np.array(x_point, dtype=float) - origin_vector
        x_length = float(np.linalg.norm(x_direction))
        if x_length <= 1e-9:
            raise ValueError("the first and second roof plane points must differ")
        x_axis = x_direction / x_length
        y_hint = np.array(y_point, dtype=float) - origin_vector
        raw_z_axis = np.cross(x_axis, y_hint)
        z_length = float(np.linalg.norm(raw_z_axis))
        if z_length <= 1e-9:
            raise ValueError("roof plane points must not be collinear")
        raw_z_axis /= z_length
        y_axis = np.cross(raw_z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis)
        if abs(float(raw_z_axis[2])) <= 1e-9:
            raise ValueError(
                "roof plane must have a normal with a non-zero global Z component"
            )
        normal_flipped = bool(raw_z_axis[2] < 0)
        z_axis = -raw_z_axis if normal_flipped else raw_z_axis
        geometry_y_sign = -1.0 if normal_flipped else 1.0

        # IFC placements must remain right-handed.  If the user-defined
        # X/Y directions yield a downward normal, reflect geometry's local Y
        # while preserving the user coordinate transform separately.
        placement = np.eye(4)
        placement[:3, 0] = x_axis
        placement[:3, 1] = geometry_y_sign * y_axis
        placement[:3, 2] = z_axis
        placement[:3, 3] = origin_vector
        coordinate_matrix = np.eye(4)
        coordinate_matrix[:3, 0] = x_axis
        coordinate_matrix[:3, 1] = y_axis
        coordinate_matrix[:3, 2] = z_axis
        coordinate_matrix[:3, 3] = origin_vector
        normalised_cuts = _plane_cuts(cuts)

        assembly = ifcopenshell.api.root.create_entity(
            self.file,
            ifc_class="IfcElementAssembly",
            name=plane_name,
            predefined_type="USERDEFINED",
        )
        assembly.ObjectType = "ROOF_PLANE"
        assembly.AssemblyPlace = "SITE"
        ifcopenshell.api.aggregate.assign_object(
            self.file,
            products=[assembly],
            relating_object=self,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            self.file,
            product=assembly,
            matrix=placement,
            is_si=True,
        )
        pset = ifcopenshell.api.pset.add_pset(
            self.file,
            product=assembly,
            name="BBIM_RoofPlane",
        )
        ifcopenshell.api.pset.edit_pset(
            self.file,
            pset=pset,
            properties={
                "Points": json.dumps((origin, x_point, y_point)),
                "Cuts": json.dumps(normalised_cuts),
                "NormalFlipped": normal_flipped,
            },
        )
        plane = RoofPlane(
            assembly,
            self,
            points=(origin, x_point, y_point),
            cuts=normalised_cuts,
            placement=placement,
            coordinate_matrix=coordinate_matrix,
            normal_flipped=normal_flipped,
        )
        self._planes.append(plane)
        return plane


class RoofPlane(ifcopenshell.entity_instance):
    """An IFC assembly providing a local coordinate frame for one roof slope."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        roof: Roof,
        *,
        points: tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ],
        cuts: tuple[PlaneCut, ...],
        placement: np.ndarray,
        coordinate_matrix: np.ndarray,
        normal_flipped: bool,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "roof", roof)
        object.__setattr__(self, "storey", roof.storey)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "origin", points[0])
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "coordinate_matrix", coordinate_matrix)
        object.__setattr__(self, "normal_flipped", normal_flipped)
        object.__setattr__(self, "geometry_y_sign", -1.0 if normal_flipped else 1.0)
        object.__setattr__(
            self,
            "x_axis",
            tuple(float(v) for v in coordinate_matrix[:3, 0]),
        )
        object.__setattr__(
            self,
            "y_axis",
            tuple(float(v) for v in coordinate_matrix[:3, 1]),
        )
        object.__setattr__(
            self,
            "z_axis",
            tuple(float(v) for v in coordinate_matrix[:3, 2]),
        )

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this roof plane as its underlying IFC assembly."""
        return self

    def to_world(self, point: Point3D) -> tuple[float, float, float]:
        """Transform a local XYZ point into global coordinates."""
        local = _point_3d(point, "point")
        world = self.coordinate_matrix @ np.array((*local, 1.0), dtype=float)
        return tuple(float(value) for value in world[:3])

    def to_local(self, point: Point3D) -> tuple[float, float, float]:
        """Transform a global XYZ point into this plane's coordinates."""
        world = _point_3d(point, "point")
        local = np.linalg.inv(self.coordinate_matrix) @ np.array(
            (*world, 1.0), dtype=float
        )
        return tuple(float(value) for value in local[:3])

    def add(
        self,
        *elements: ifcopenshell.entity_instance,
    ) -> ifcopenshell.entity_instance:
        """Aggregate existing IFC elements beneath this roof plane."""
        if not elements:
            raise ValueError("roof_plane.add requires at least one element")
        normalised = []
        for index, element in enumerate(elements, start=1):
            if not isinstance(element, ifcopenshell.entity_instance) or not element.is_a(
                "IfcElement"
            ):
                raise TypeError(f"element {index} must be an IfcElement")
            if element.file is not self.file:
                raise ValueError(f"element {index} must belong to this house")
            if element in {self, self.roof}:
                raise ValueError("a roof plane cannot aggregate itself or its roof")
            normalised.append(element)
        return ifcopenshell.api.aggregate.assign_object(
            self.file,
            products=normalised,
            relating_object=self,
        )

    def beam(
        self,
        name: str,
        *,
        start: Point,
        end: Point,
        size: Sequence[Number],
        z_offset: Number = 0,
        material: str = "Wood",
        kind: BeamKind = "BEAM",
        rotation: Number = 0,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Beam:
        """Create a plane-local beam with its bottom at ``z_offset``.

        The unrotated section height follows the roof plane's local Z.  When
        ``rotation`` rolls the section, the centreline is raised as necessary
        so its lowest point along local Z remains at ``z_offset``.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        z_offset = _number(z_offset, "z_offset")
        if isinstance(size, (str, bytes)):
            raise TypeError("size must contain exactly two dimensions")
        try:
            width, height = size
        except (TypeError, ValueError) as error:
            raise TypeError(
                "size must contain exactly two dimensions"
            ) from error
        width = _number(width, "size width")
        height = _number(height, "size height")
        if width <= 0 or height <= 0:
            raise ValueError("size dimensions must be greater than zero")
        rotation = _number(rotation, "rotation")
        roll = radians(rotation)
        section_extent_below_centre = (
            abs(sin(roll)) * width / 2
            + abs(cos(roll)) * height / 2
        )
        centreline_z_offset = z_offset + section_extent_below_centre
        beam = self.storey.beam(
            name,
            start=self.to_world((start_x, start_y, centreline_z_offset)),
            end=self.to_world((end_x, end_y, centreline_z_offset)),
            size=(width, height),
            material=material,
            kind=kind,
            rotation=rotation,
            color=color,
            transparency=transparency,
            height_axis=self.z_axis,
            cuts=self.cuts,
        )
        self.add(beam)
        object.__setattr__(beam, "roof_plane", self)
        object.__setattr__(beam, "local_start", (start_x, start_y))
        object.__setattr__(beam, "local_end", (end_x, end_y))
        object.__setattr__(beam, "z_offset", z_offset)
        object.__setattr__(beam, "centerline_z_offset", centreline_z_offset)
        return beam

    def layer(
        self,
        name: str,
        *,
        outline: Sequence[Point],
        z_offset: Number = 0,
        thickness: Number,
        material: str,
        color: str | None = None,
        transparency: Number = 0,
        extra_cuts: Sequence[PlaneCut] | None = None,
    ) -> RoofLayer:
        """Create a roof layer, optionally trimmed by additional plane cuts."""
        layer_name = _name(name, "name")
        material_name = _name(material, "material")
        z_offset = _number(z_offset, "z_offset")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        if isinstance(outline, (str, bytes)):
            raise TypeError("outline must contain at least three points")
        try:
            supplied_outline = list(outline)
        except TypeError as error:
            raise TypeError("outline must contain at least three points") from error
        if len(supplied_outline) < 3:
            raise ValueError("outline must contain at least three points")
        points = tuple(
            _point(point, f"outline point {index}")
            for index, point in enumerate(supplied_outline, start=1)
        )
        twice_area = 0.0
        centroid_x_sum = 0.0
        centroid_y_sum = 0.0
        for point, next_point in zip(points, (*points[1:], points[0])):
            cross = point[0] * next_point[1] - next_point[0] * point[1]
            twice_area += cross
            centroid_x_sum += (point[0] + next_point[0]) * cross
            centroid_y_sum += (point[1] + next_point[1]) * cross
        if abs(twice_area) <= 1e-9:
            raise ValueError("outline must enclose a non-zero area")
        centroid = (
            centroid_x_sum / (3 * twice_area),
            centroid_y_sum / (3 * twice_area),
        )
        geometry_points = tuple(
            (x, self.geometry_y_sign * y) for x, y in points
        )
        geometry_centroid = (
            centroid[0],
            self.geometry_y_sign * centroid[1],
        )
        normalised_extra_cuts = _plane_cuts(extra_cuts)
        effective_cuts = (
            *self.cuts,
            *normalised_extra_cuts,
        )

        placement = self.placement.copy()
        placement[:3, 3] = np.array(self.to_world((0, 0, z_offset)))
        clippings = _local_clippings(
            effective_cuts,
            placement,
            (geometry_centroid[0], geometry_centroid[1], thickness / 2),
        )
        model = self.file
        element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcSlab",
            name=layer_name,
            predefined_type="ROOF",
        )
        layer = RoofLayer(
            element,
            self,
            outline=points,
            z_offset=z_offset,
            thickness=thickness,
            material_name=material_name,
            placement=placement,
            cuts=effective_cuts,
            extra_cuts=normalised_extra_cuts,
        )
        self.add(layer)
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=layer,
            matrix=placement,
            is_si=True,
        )
        body = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.storey.house._body_context,
            depth=thickness,
            polyline=geometry_points,
        )
        _clip_body_representation(model, layer, body, clippings)
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=layer,
            representation=body,
        )
        surface_style = self.storey.house._surface_style(
            "slab",
            color=color,
            transparency=transparency,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )
        ifc_material = self.storey.house._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category=material_name.casefold(),
            )
            self.storey.house._materials[material_name] = ifc_material
        ifcopenshell.api.material.assign_material(
            model,
            products=[layer],
            type="IfcMaterial",
            material=ifc_material,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=layer,
            name="BBIM_RoofLayer",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={
                "RoofPlane": self.GlobalId,
                "Outline": json.dumps(points),
                "ZOffset": z_offset,
                "Thickness": thickness,
                "Cuts": json.dumps(effective_cuts),
                "ExtraCuts": json.dumps(normalised_extra_cuts),
            },
        )
        return layer


class RoofLayer(ifcopenshell.entity_instance):
    """A physical ``IfcSlab/ROOF`` layer created in a roof-plane frame."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        plane: RoofPlane,
        *,
        outline: tuple[tuple[float, float], ...],
        z_offset: float,
        thickness: float,
        material_name: str,
        placement: np.ndarray,
        cuts: tuple[PlaneCut, ...],
        extra_cuts: tuple[PlaneCut, ...],
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "plane", plane)
        object.__setattr__(self, "roof", plane.roof)
        object.__setattr__(self, "storey", plane.storey)
        object.__setattr__(self, "outline", outline)
        object.__setattr__(self, "z_offset", z_offset)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "material_name", material_name)
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "extra_cuts", extra_cuts)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this roof layer as its underlying IFC entity."""
        return self


class Chimney(ifcopenshell.entity_instance):
    """An ``IfcChimney`` with a square stack and central circular flue."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        center: tuple[float, float],
        size: float,
        height: float,
        flue_diameter: float,
        start_height: float,
        placement: np.ndarray,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "flue_diameter", flue_diameter)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "end_height", start_height + height)
        object.__setattr__(self, "placement", placement)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this chimney as its underlying IFC entity."""
        return self


class MiakoSlab(ifcopenshell.entity_instance):
    """A decomposed ``IfcSlab`` made from MIAKO beams, blocks, and topping."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        start: tuple[float, float],
        end: tuple[float, float],
        direction: tuple[float, float],
        structure: tuple[str, ...],
        length: float,
        width: float,
        top: float,
        block_length: float,
        block_height: float,
        beam_height: float,
        topping: float,
        placement: np.ndarray,
        beams: tuple[ifcopenshell.entity_instance, ...],
        beam_shells: tuple[ifcopenshell.entity_instance, ...],
        reinforcements: tuple[ifcopenshell.entity_instance, ...],
        blocks: tuple[ifcopenshell.entity_instance, ...],
        topping_element: ifcopenshell.entity_instance,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "structure", structure)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "top", top)
        object.__setattr__(self, "block_length", block_length)
        object.__setattr__(self, "block_height", block_height)
        object.__setattr__(self, "beam_height", beam_height)
        object.__setattr__(self, "topping", topping)
        object.__setattr__(self, "height", block_height + topping)
        object.__setattr__(self, "bottom", top - (block_height + topping))
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "beams", beams)
        object.__setattr__(self, "beam_shells", beam_shells)
        object.__setattr__(self, "reinforcements", reinforcements)
        object.__setattr__(self, "blocks", blocks)
        object.__setattr__(self, "topping_element", topping_element)
        object.__setattr__(
            self,
            "components",
            (*beams, *beam_shells, *reinforcements, *blocks, topping_element),
        )

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this MIAKO slab as its underlying IFC entity."""
        return self

    @property
    def footprint(self) -> tuple[tuple[float, float], ...]:
        """Return the four global XY corners covered by this slab."""
        offset_x = self.direction[0] * self.width
        offset_y = self.direction[1] * self.width
        return (
            self.start,
            self.end,
            (self.end[0] + offset_x, self.end[1] + offset_y),
            (self.start[0] + offset_x, self.start[1] + offset_y),
        )


class Stair(ifcopenshell.entity_instance):
    """An ``IfcStair`` containing one straight ``IfcStairFlight``."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        flight: ifcopenshell.entity_instance,
        start: tuple[float, float],
        end: tuple[float, float],
        length: float,
        width: float,
        height: float,
        start_height: float,
        risers: int,
        treads: int,
        riser_height: float,
        tread_length: float,
        underside: Literal["solid", "sloped"],
        waist_thickness: float | None,
        placement: np.ndarray,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "flight", flight)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "end_height", start_height + height)
        object.__setattr__(self, "risers", risers)
        object.__setattr__(self, "treads", treads)
        object.__setattr__(self, "riser_height", riser_height)
        object.__setattr__(self, "tread_length", tread_length)
        object.__setattr__(self, "underside", underside)
        object.__setattr__(self, "waist_thickness", waist_thickness)
        object.__setattr__(self, "placement", placement)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this stair as its underlying IFC entity."""
        return self


class Wall(ifcopenshell.entity_instance):
    """An ``IfcWall`` with convenience methods for hosted elements.

    The class is an IfcOpenShell entity instance, so it can be passed directly
    to IfcOpenShell APIs.  Door and window ``at`` distances locate the start
    of their wall opening from the wall's supplied start point.
    """

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        start: tuple[float, float],
        end: tuple[float, float],
        length: float,
        height: float,
        start_height: float,
        thickness: float,
        body_offset: float,
        surface_style: ifcopenshell.entity_instance | None,
        cuts: tuple[WallCut, ...],
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "end_height", start_height + height)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "body_offset", body_offset)
        object.__setattr__(self, "surface_style", surface_style)
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "_openings", [])

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this wall as its underlying IFC entity."""
        return self

    def _validate_opening(
        self,
        *,
        opening_start: Number,
        width: Number,
        height: Number,
        sill_height: Number,
    ) -> tuple[float, float, float, float]:
        opening_start = _number(opening_start, "opening start")
        width = _number(width, "width")
        height = _number(height, "height")
        sill_height = _number(sill_height, "sill_height")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if sill_height < 0:
            raise ValueError("sill_height must not be negative")
        if sill_height < self.start_height:
            raise ValueError("opening must not start below the wall")

        opening_end = opening_start + width
        opening_top = sill_height + height
        tolerance = 1e-9
        if opening_start < -tolerance or opening_end > self.length + tolerance:
            raise ValueError("opening must fit within the wall length")
        if opening_top > self.end_height + tolerance:
            raise ValueError("opening must fit within the wall height")

        for existing_start, existing_end, existing_bottom, existing_top in self._openings:
            overlaps_horizontally = (
                opening_start < existing_end - tolerance
                and existing_start < opening_end - tolerance
            )
            overlaps_vertically = (
                sill_height < existing_top - tolerance
                and existing_bottom < opening_top - tolerance
            )
            if overlaps_horizontally and overlaps_vertically:
                raise ValueError("opening overlaps another opening in this wall")

        return opening_start, width, height, sill_height

    def _placement(self, along: float, elevation: float) -> np.ndarray:
        direction_x = (self.end[0] - self.start[0]) / self.length
        direction_y = (self.end[1] - self.start[1]) / self.length
        placement = np.eye(4)
        placement[0, 0] = direction_x
        placement[0, 1] = -direction_y
        placement[1, 0] = direction_y
        placement[1, 1] = direction_x
        placement[0, 3] = self.start[0] + along * direction_x
        placement[1, 3] = self.start[1] + along * direction_y
        placement[2, 3] = self.storey.elevation + elevation
        return placement

    def _create_opening(
        self,
        *,
        name: str,
        opening_start: float,
        width: float,
        height: float,
        sill_height: float,
    ) -> ifcopenshell.entity_instance:
        model = self.storey.house.model
        opening = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcOpeningElement",
            name=name,
            predefined_type="OPENING",
        )
        overlap = 0.05
        representation = ifcopenshell.api.geometry.add_wall_representation(
            model,
            context=self.storey.house._body_context,
            length=width,
            height=height,
            thickness=self.thickness + 2 * overlap,
            offset=self.body_offset - overlap,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=opening,
            representation=representation,
        )
        ifcopenshell.api.feature.add_feature(
            model,
            feature=opening,
            element=self,
        )
        placement = self._placement(opening_start, sill_height)
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=opening,
            matrix=placement,
            is_si=True,
        )
        return opening

    def _add_dashed_overhead_line(
        self,
        *,
        name: str,
        opening_start: float,
        opening_width: float,
        opening_bottom: float,
        opening_top: float,
        wall_faces: bool = False,
    ) -> ifcopenshell.entity_instance:
        """Add plan-only dashed linework for the wall above an opening."""
        model = self.storey.house.model
        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{name} Overhead",
            predefined_type="LINEWORK",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[annotation],
            relating_structure=self.storey.element,
        )
        if wall_faces:
            inset = min(0.025, opening_width / 4)
            curves = []
            for y in (self.body_offset, self.body_offset + self.thickness):
                point_list = model.createIfcCartesianPointList2D(
                    [(inset, y), (opening_width - inset, y)]
                )
                curves.append(
                    model.createIfcIndexedPolyCurve(point_list, None, False)
                )
            representation = model.createIfcShapeRepresentation(
                self.storey.house._annotation_context,
                "Annotation",
                "GeometricCurveSet",
                [model.createIfcGeometricCurveSet(curves)],
            )
            classes = "door-overhead dashed"
        else:
            wall_centre = self.body_offset + self.thickness / 2
            representation = ifcopenshell.api.geometry.add_axis_representation(
                model,
                context=self.storey.house._annotation_context,
                axis=[(0.0, wall_centre), (opening_width, wall_centre)],
            )
            classes = "dashed"
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=representation,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=self._placement(opening_start, 0),
            is_si=True,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={
                "Classes": classes,
                "OpeningBottom": opening_bottom,
                "OpeningTop": opening_top,
            },
        )
        house = self.storey.house
        house._plan_annotations.append(annotation)
        for drawing in house._drawings:
            if (
                drawing.view == "plan"
                and drawing._includes_storey(self.storey)
            ):
                ifcopenshell.api.group.assign_group(
                    model,
                    group=drawing.group,
                    products=[annotation],
                )
        return annotation

    def _place_filling(
        self,
        filling: ifcopenshell.entity_instance,
        opening: ifcopenshell.entity_instance,
        placement: np.ndarray,
    ) -> None:
        model = self.storey.house.model
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[filling],
            relating_structure=self.storey.element,
        )
        ifcopenshell.api.feature.add_filling(
            model,
            opening=opening,
            element=filling,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=filling,
            matrix=placement,
            is_si=True,
        )

    def _set_door_open_angle(
        self,
        door: ifcopenshell.entity_instance,
        *,
        operation: str,
        open_angle: float,
        reverse_swing: bool,
        width: float,
        panel_offset_x: float,
        panel_offset_y: float,
    ) -> None:
        """Rotate only the movable items in a door's 3D body representation."""
        _rotate_door_framing(
            self.storey.house.model,
            door,
            operation=operation,
            angle=open_angle,
            reverse_swing=reverse_swing,
            width=width,
            panel_offset_x=panel_offset_x,
            pivot_y=self.body_offset + panel_offset_y,
        )

    def _add_door_casings(
        self,
        door: ifcopenshell.entity_instance,
        body_representation: ifcopenshell.entity_instance,
        *,
        width: float,
        height: float,
        opening_width: float,
        opening_height: float,
        lining_thickness: float,
        casing_overlap: float,
        casing_depth: float,
    ) -> None:
        """Cover the rough-opening clearance on both wall faces."""
        if casing_depth == 0:
            return

        side_clearance = (opening_width - width) / 2
        head_clearance = opening_height - height
        outer_left = -side_clearance - casing_overlap
        outer_right = width + side_clearance + casing_overlap
        outer_top = height + head_clearance + casing_overlap
        inner_left = lining_thickness
        inner_right = width - lining_thickness
        inner_top = height - lining_thickness
        profile_points = [
            (outer_left, 0.0),
            (outer_left, outer_top),
            (outer_right, outer_top),
            (outer_right, 0.0),
            (inner_right, 0.0),
            (inner_right, inner_top),
            (inner_left, inner_top),
            (inner_left, 0.0),
        ]

        builder = ShapeBuilder(self.storey.house.model)
        profile = builder.polyline(profile_points, closed=True)
        casings = [
            builder.extrude(
                profile,
                magnitude=casing_depth,
                **builder.extrude_kwargs("Y"),
            )
            for _ in range(2)
        ]
        builder.translate(
            casings[0],
            (0.0, self.body_offset - casing_depth, 0.0),
        )
        builder.translate(
            casings[1],
            (0.0, self.body_offset + self.thickness, 0.0),
        )
        body_representation.Items = [*body_representation.Items, *casings]
        ifcopenshell.api.geometry.add_shape_aspect(
            self.storey.house.model,
            "Casing",
            items=casings,
            representation=body_representation,
            part_of_product=door.Representation,
        )

    def _reverse_door_plan_swing(
        self,
        representation: ifcopenshell.entity_instance,
    ) -> None:
        """Mirror the plan swing onto the opposite room-side wall face."""
        items = list(representation.Items)
        if len(items) < 3:
            raise RuntimeError("unexpected door plan representation structure")
        ShapeBuilder(self.storey.house.model).mirror(
            items[2:],
            mirror_axes=(0.0, 1.0),
            mirror_point=(0.0, self.body_offset + self.thickness / 2),
        )

    def add_opening(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        sill_height: Number = 0,
        show_overhead: bool = True,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut an unfilled rectangular opening in this wall.

        ``at`` locates the start of the opening along the wall and
        ``sill_height`` and ``height`` are the bottom and top coordinates
        measured above the storey elevation, matching ``add_window`` and
        ``add_door``.  ``show_overhead`` adds dashed plan-only wall linework
        across it.
        """
        if not isinstance(show_overhead, bool):
            raise TypeError("show_overhead must be a boolean")
        top_height = _number(height, "height")
        sill_height = _number(sill_height, "sill_height")
        if top_height <= sill_height:
            raise ValueError("height must be greater than sill_height")
        opening_height = top_height - sill_height
        opening_start, width, opening_height, sill_height = (
            self._validate_opening(
                opening_start=at,
                width=width,
                height=opening_height,
                sill_height=sill_height,
            )
        )

        self.storey._opening_count += 1
        opening_name = (
            _name(name, "name")
            if name is not None
            else f"Wall Opening {self.storey._opening_count}"
        )
        opening = self._create_opening(
            name=opening_name,
            opening_start=opening_start,
            width=width,
            height=opening_height,
            sill_height=sill_height,
        )
        self._openings.append(
            (
                opening_start,
                opening_start + width,
                sill_height,
                sill_height + opening_height,
            )
        )
        if show_overhead:
            self._add_dashed_overhead_line(
                name=opening_name,
                opening_start=opening_start,
                opening_width=width,
                opening_bottom=sill_height,
                opening_top=sill_height + opening_height,
                wall_faces=True,
            )
        return opening

    def add_door(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        clear_height: Number | None = None,
        sill_height: Number = 0,
        opening_width: Number | None = None,
        opening_height: Number | None = None,
        operation: DoorOperation = "SINGLE_SWING_LEFT",
        open_angle: Number = 45,
        reverse_swing: bool = False,
        show_overhead: bool = True,
        casing_overlap: Number = 0.025,
        casing_depth: Number = 0.005,
        color: str | None = None,
        transparency: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut and fill a door opening in this wall.

        ``at`` is the start of the rough opening measured from the wall start.
        The actual door is centred horizontally in ``opening_width`` and its
        bottom is ``sill_height`` metres above the storey elevation.  As with
        ``add_window``, ``height`` is the door's top coordinate, not its
        vertical size.  ``opening_height`` is likewise the rough opening's top
        coordinate and defaults to ``height``.  ``clear_height`` remains a
        physical size: it records the usable walking height for plan
        annotations without changing the construction geometry and defaults
        to ``height - sill_height``.  ``open_angle`` rotates only the 3D leaf.
        ``reverse_swing`` opens the leaf on the opposite side of the wall
        without changing its hinge end, in both 3D and plan.  ``show_overhead``
        adds dashed plan-only wall linework across the rough opening.  Casings
        on both wall faces bridge any clearance between the door and rough
        opening; ``casing_overlap`` is how far they continue over the wall
        beyond the rough opening and ``casing_depth`` is their projection from
        each wall face.  Set ``casing_depth`` to zero to omit them.  ``color``
        and ``transparency`` affect only the 3D body.
        """
        operation = _enum(operation, "operation", _DOOR_OPERATIONS)
        open_angle = _number(open_angle, "open_angle")
        if not 0 <= open_angle <= 180:
            raise ValueError("open_angle must be between 0 and 180 degrees")
        if not isinstance(reverse_swing, bool):
            raise TypeError("reverse_swing must be a boolean")
        if reverse_swing and "SLIDING" in operation:
            raise ValueError("reverse_swing is not supported for sliding doors")
        if not isinstance(show_overhead, bool):
            raise TypeError("show_overhead must be a boolean")
        casing_overlap = _number(casing_overlap, "casing_overlap")
        casing_depth = _number(casing_depth, "casing_depth")
        if casing_overlap < 0:
            raise ValueError("casing_overlap must not be negative")
        if casing_depth < 0:
            raise ValueError("casing_depth must not be negative")
        surface_style = self.storey.house._surface_style(
            "door",
            color=color,
            transparency=transparency,
        )
        at = _number(at, "at")
        width = _number(width, "width")
        top_height = _number(height, "height")
        sill_height = _number(sill_height, "sill_height")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if top_height <= sill_height:
            raise ValueError("height must be greater than sill_height")
        door_height = top_height - sill_height
        clear_height = (
            door_height
            if clear_height is None
            else _number(clear_height, "clear_height")
        )
        if clear_height <= 0:
            raise ValueError("clear_height must be greater than zero")
        if clear_height > door_height + 1e-9:
            raise ValueError(
                "clear_height must not be greater than height - sill_height"
            )
        opening_width = (
            width
            if opening_width is None
            else _number(opening_width, "opening_width")
        )
        opening_top_height = (
            top_height
            if opening_height is None
            else _number(opening_height, "opening_height")
        )
        tolerance = 1e-9
        if opening_width < width - tolerance:
            raise ValueError("opening_width must not be smaller than width")
        if opening_top_height <= sill_height:
            raise ValueError("opening_height must be greater than sill_height")
        if opening_top_height < top_height - tolerance:
            raise ValueError("opening_height must not be smaller than height")
        rough_opening_height = opening_top_height - sill_height
        opening_start, opening_width, opening_height, sill_height = (
            self._validate_opening(
                opening_start=at,
                width=opening_width,
                height=rough_opening_height,
                sill_height=sill_height,
            )
        )
        door_start = opening_start + (opening_width - width) / 2
        filling_placement = self._placement(door_start, sill_height)
        self.storey._door_count += 1
        door_name = (
            _name(name, "name")
            if name is not None
            else f"Door {self.storey._door_count}"
        )
        opening = self._create_opening(
            name=f"{door_name} Opening",
            opening_start=opening_start,
            width=opening_width,
            height=opening_height,
            sill_height=sill_height,
        )

        model = self.storey.house.model
        door = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcDoor",
            name=door_name,
            predefined_type="DOOR",
        )
        door.OverallWidth = width
        door.OverallHeight = door_height
        door.OperationType = operation
        panel_offset_x = min(0.025, width / 4)
        panel_offset_y = min(0.025, self.thickness / 4)
        lining_thickness = min(0.05, width / 4, door_height / 4)
        door_properties = ifcopenshell.api.pset.add_pset(
            model,
            product=door,
            name="EPset_Door",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=door_properties,
            properties={
                "ClearHeight": clear_height,
                "OpenAngle": open_angle,
                "ReverseSwing": reverse_swing,
                "PanelOffsetX": panel_offset_x,
                "BodyPivotY": self.body_offset + panel_offset_y,
                "CasingOverlap": casing_overlap,
                "CasingDepth": casing_depth,
            },
        )
        lining_properties = {
            "LiningDepth": self.thickness,
            "LiningThickness": lining_thickness,
            "LiningOffset": self.body_offset,
            "LiningToPanelOffsetX": panel_offset_x,
            "LiningToPanelOffsetY": panel_offset_y,
            # IfcOpenShell only creates its built-in casings when
            # LiningOffset is zero.  Add consistently positioned casings below
            # instead, including for centred and asymmetrically layered walls.
            "CasingDepth": 0.0,
            "CasingThickness": 0.0,
        }
        door.Representation = model.createIfcProductDefinitionShape()
        body_representation = ifcopenshell.api.geometry.add_door_representation(
            model,
            context=self.storey.house._body_context,
            overall_height=door_height,
            overall_width=width,
            operation_type=operation,
            lining_properties=lining_properties,
            part_of_product=door.Representation,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=door,
            representation=body_representation,
        )
        self._add_door_casings(
            door,
            body_representation,
            width=width,
            height=door_height,
            opening_width=opening_width,
            opening_height=opening_height,
            lining_thickness=lining_thickness,
            casing_overlap=casing_overlap,
            casing_depth=casing_depth,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body_representation,
                styles=[surface_style],
            )
        self._set_door_open_angle(
            door,
            operation=operation,
            open_angle=open_angle,
            reverse_swing=reverse_swing,
            width=width,
            panel_offset_x=panel_offset_x,
            panel_offset_y=panel_offset_y,
        )

        plan_representation = ifcopenshell.api.geometry.add_door_representation(
            model,
            context=self.storey.house._plan_body_context,
            overall_height=door_height,
            overall_width=width,
            operation_type=operation,
            lining_properties=lining_properties,
        )
        if plan_representation is not None:
            if reverse_swing:
                self._reverse_door_plan_swing(plan_representation)
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=door,
                representation=plan_representation,
            )
        self._place_filling(door, opening, filling_placement)
        self._openings.append(
            (
                opening_start,
                opening_start + opening_width,
                sill_height,
                sill_height + opening_height,
            )
        )
        if show_overhead:
            self._add_dashed_overhead_line(
                name=door_name,
                opening_start=opening_start,
                opening_width=opening_width,
                opening_bottom=sill_height,
                opening_top=sill_height + opening_height,
                wall_faces=True,
            )
        for drawing in self.storey.house._drawings:
            if (
                drawing._automatic_door_annotations
                and drawing._includes_storey(self.storey)
            ):
                drawing.add_door_annotation(
                    door,
                    offset=drawing._door_annotation_offset,
                )
        return door

    def _align_window_panel_to_axis(
        self,
        window: ifcopenshell.entity_instance,
    ) -> None:
        """Move the generated 3D frame and glazing onto the wall axis."""
        aspects = {
            aspect.Name: aspect
            for aspect in window.Representation.HasShapeAspects
        }
        glazing = aspects.get("Glazing")
        if glazing is None:
            raise RuntimeError("window representation has no glazing aspect")
        glazing_representation = next(
            representation
            for representation in glazing.ShapeRepresentations
            if representation.ContextOfItems == self.storey.house._body_context
        )
        glass = glazing_representation.Items[0]
        glass_placement = ifcopenshell.util.placement.get_axis2placement(
            glass.Position
        )
        extrusion_direction = np.array(
            tuple(glass.ExtrudedDirection.DirectionRatios),
            dtype=float,
        )
        glass_center = glass_placement[:3, 3] + (
            glass_placement[:3, :3]
            @ extrusion_direction
            * float(glass.Depth)
            / 2
        )
        offset_y = -float(glass_center[1])

        for aspect_name in ("Framing", "Glazing"):
            aspect = aspects.get(aspect_name)
            if aspect is None:
                raise RuntimeError(
                    f"window representation has no {aspect_name.lower()} aspect"
                )
            for representation in aspect.ShapeRepresentations:
                if representation.ContextOfItems != self.storey.house._body_context:
                    continue
                for item in representation.Items:
                    coordinates = list(item.Position.Location.Coordinates)
                    coordinates[1] += offset_y
                    item.Position.Location.Coordinates = tuple(coordinates)

    def _align_window_plan_to_axis(
        self,
        representation: ifcopenshell.entity_instance,
    ) -> None:
        """Move each generated 2D frame and glass group onto the wall axis."""
        items = list(representation.Items)
        items_per_panel = 8
        if not items or len(items) % items_per_panel:
            raise RuntimeError("unexpected window plan representation structure")

        for start in range(0, len(items), items_per_panel):
            panel_items = items[start : start + items_per_panel]
            glass_line = panel_items[-1]
            glass_coordinates = glass_line.Points.CoordList
            offset_y = -float(glass_coordinates[0][1])
            for item in panel_items[3:]:
                item.Points.CoordList = tuple(
                    (float(x), float(y) + offset_y)
                    for x, y in item.Points.CoordList
                )

    def add_window(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        sill_height: Number,
        partition: WindowPartition = "SINGLE_PANEL",
        align: WindowAlignment = "axis",
        glass_transparency: Number = 0.75,
        color: str | None = None,
        transparency: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut and fill a window opening in this wall.

        ``at`` is the opening start measured from the wall start and
        ``sill_height`` and ``height`` are the bottom and top coordinates
        measured above the storey elevation.  ``align="axis"`` centres the
        frame and glazing on the wall reference axis in both the 3D and plan
        representations; ``align="inside"`` keeps IfcOpenShell's legacy panel
        position.  ``color`` applies to the whole 3D window, ``transparency``
        controls its lining and frame, and ``glass_transparency`` independently
        controls the glazing.
        """
        partition = _enum(partition, "partition", _WINDOW_PARTITIONS)
        align = _enum(align, "align", _WINDOW_ALIGNMENTS)
        surface_style = self.storey.house._surface_style(
            "window",
            color=color,
            transparency=transparency,
        )
        glass_color = color
        if (
            glass_color is None
            and "window" not in self.storey.house._default_colors
        ):
            glass_color = "#B7D9E8"
        glass_surface_style = self.storey.house._surface_style(
            "window",
            color=glass_color,
            transparency=glass_transparency,
        )
        at = _number(at, "at")
        width = _number(width, "width")
        top_height = _number(height, "height")
        sill_height = _number(sill_height, "sill_height")
        if top_height <= sill_height:
            raise ValueError("height must be greater than sill_height")
        window_height = top_height - sill_height
        opening_start, width, window_height, sill_height = self._validate_opening(
            opening_start=at,
            width=width,
            height=window_height,
            sill_height=sill_height,
        )
        self.storey._window_count += 1
        window_name = (
            _name(name, "name")
            if name is not None
            else f"Window {self.storey._window_count}"
        )
        opening = self._create_opening(
            name=f"{window_name} Opening",
            opening_start=opening_start,
            width=width,
            height=window_height,
            sill_height=sill_height,
        )
        placement = self._placement(opening_start, sill_height)

        model = self.storey.house.model
        window = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcWindow",
            name=window_name,
            predefined_type="WINDOW",
        )
        window.OverallWidth = width
        window.OverallHeight = window_height
        window.PartitioningType = partition
        window.Representation = model.createIfcProductDefinitionShape()
        lining_properties = {
            "LiningDepth": self.thickness,
            "LiningOffset": self.body_offset,
        }
        body_representation = None
        plan_representation = None
        for context in (
            self.storey.house._body_context,
            self.storey.house._plan_body_context,
        ):
            representation = ifcopenshell.api.geometry.add_window_representation(
                model,
                context=context,
                overall_height=window_height,
                overall_width=width,
                partition_type=partition,
                lining_properties=lining_properties,
                part_of_product=(
                    window.Representation
                    if context == self.storey.house._body_context
                    else None
                ),
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=window,
                representation=representation,
            )
            if context == self.storey.house._body_context:
                body_representation = representation
            else:
                plan_representation = representation
        if body_representation is None:
            raise RuntimeError("window has no 3D body representation")
        if plan_representation is None:
            raise RuntimeError("window has no plan representation")
        if align == "AXIS":
            self._align_window_panel_to_axis(window)
            self._align_window_plan_to_axis(plan_representation)
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body_representation,
                styles=[surface_style],
            )
        glazing = next(
            aspect
            for aspect in window.Representation.HasShapeAspects
            if aspect.Name == "Glazing"
        )
        for representation in glazing.ShapeRepresentations:
            if representation.ContextOfItems != self.storey.house._body_context:
                continue
            for item in representation.Items:
                ifcopenshell.api.style.assign_item_style(
                    model,
                    item=item,
                    style=glass_surface_style,
                )
        self._place_filling(window, opening, placement)
        self._openings.append(
            (opening_start, opening_start + width, sill_height, top_height)
        )
        return window


class Storey:
    """A building storey belonging to a :class:`House`."""

    def __init__(self, house: House, name: str, elevation: float) -> None:
        self.house = house
        self.name = name
        self.elevation = elevation
        self.element = ifcopenshell.api.root.create_entity(
            house.model, ifc_class="IfcBuildingStorey", name=name
        )
        self.element.Elevation = elevation
        ifcopenshell.api.aggregate.assign_object(
            house.model, products=[self.element], relating_object=house.building
        )

        placement = np.eye(4)
        placement[2, 3] = elevation
        ifcopenshell.api.geometry.edit_object_placement(
            house.model,
            product=self.element,
            matrix=placement,
            is_si=True,
        )
        self._wall_count = 0
        self._batting_count = 0
        self._opening_count = 0
        self._door_count = 0
        self._window_count = 0
        self._stair_count = 0
        self._landing_count = 0
        self._chimney_count = 0

    def add(
        self,
        *elements: ifcopenshell.entity_instance,
    ) -> ifcopenshell.entity_instance:
        """Spatially contain existing IFC elements in this storey."""
        if not elements:
            raise ValueError("storey.add requires at least one element")
        normalised = []
        for index, element in enumerate(elements, start=1):
            if not isinstance(element, ifcopenshell.entity_instance) or not element.is_a(
                "IfcElement"
            ):
                raise TypeError(f"element {index} must be an IfcElement")
            if element.file is not self.house.model:
                raise ValueError(f"element {index} must belong to this house")
            normalised.append(element)
        return ifcopenshell.api.spatial.assign_container(
            self.house.model,
            products=normalised,
            relating_structure=self.element,
        )

    def roof(self, name: str) -> Roof:
        """Create an ``IfcRoof`` aggregate contained by this storey."""
        roof_name = _name(name, "name")
        element = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcRoof",
            name=roof_name,
            predefined_type="NOTDEFINED",
        )
        roof = Roof(element, self)
        ifcopenshell.api.spatial.assign_container(
            self.house.model,
            products=[roof],
            relating_structure=self.element,
        )
        placement = np.eye(4)
        placement[2, 3] = self.elevation
        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=roof,
            matrix=placement,
            is_si=True,
        )
        return roof

    def floor_layer(
        self,
        name: str,
        *,
        outline: Sequence[Point],
        thickness: Number,
        start_height: Number = 0,
        material: str = "Floor build-up",
        color: str | None = None,
        transparency: Number = 0,
    ) -> ifcopenshell.entity_instance:
        """Create one simplified floor build-up above the storey elevation.

        ``outline`` contains the floor polygon in global XY coordinates.
        ``start_height`` locates its underside above this storey's elevation,
        and the slab extends upward by ``thickness``.  A single material keeps
        the representation simple until the build-up needs to be decomposed
        into insulation, heating, and screed layers.
        """
        layer_name = _name(name, "name")
        material_name = _name(material, "material")
        thickness = _number(thickness, "thickness")
        start_height = _number(start_height, "start_height")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        if start_height < 0:
            raise ValueError("start_height must be zero or greater")
        if isinstance(outline, (str, bytes)):
            raise TypeError("outline must contain at least three points")
        try:
            supplied_outline = list(outline)
        except TypeError as error:
            raise TypeError("outline must contain at least three points") from error
        if len(supplied_outline) < 3:
            raise ValueError("outline must contain at least three points")
        points = tuple(
            _point(point, f"outline point {index}")
            for index, point in enumerate(supplied_outline, start=1)
        )
        twice_area = sum(
            point[0] * next_point[1] - next_point[0] * point[1]
            for point, next_point in zip(points, (*points[1:], points[0]))
        )
        if abs(twice_area) <= 1e-9:
            raise ValueError("outline must enclose a non-zero area")

        model = self.house.model
        layer = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcSlab",
            name=layer_name,
            predefined_type="FLOOR",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[layer],
            relating_structure=self.element,
        )
        placement = np.eye(4)
        placement[2, 3] = self.elevation + start_height
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=layer,
            matrix=placement,
            is_si=True,
        )
        body = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.house._body_context,
            depth=thickness,
            polyline=points,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=layer,
            representation=body,
        )
        surface_style = self.house._surface_style(
            "slab",
            color=color,
            transparency=transparency,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        ifc_material = self.house._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category="floor",
            )
            self.house._materials[material_name] = ifc_material
        ifcopenshell.api.material.assign_material(
            model,
            products=[layer],
            type="IfcMaterial",
            material=ifc_material,
        )
        common_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=layer,
            name="Pset_SlabCommon",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=common_pset,
            properties={"LoadBearing": False},
        )
        layer_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=layer,
            name="BBIM_FloorLayer",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=layer_pset,
            properties={
                "Outline": json.dumps(points),
                "StartHeight": start_height,
                "Thickness": thickness,
                "Material": material_name,
            },
        )
        return layer

    def batting(
        self,
        start: Point,
        end: Point,
        *,
        thickness: Number,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a classic batt-insulation annotation along a plan line.

        The annotation and its line geometry are stored in the IFC.  Bonsai
        uses the ``BBIM_Batting.Thickness`` property, expressed in metres, to
        size the loops when producing a drawing.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("batting start and end must be different points")

        self._batting_count += 1
        annotation = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcAnnotation",
            name=(
                _name(name, "name")
                if name is not None
                else f"Batting {self._batting_count}"
            ),
            predefined_type="BATTING",
        )
        ifcopenshell.api.spatial.assign_container(
            self.house.model,
            products=[annotation],
            relating_structure=self.element,
        )

        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = self.elevation
        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=annotation,
            matrix=placement,
            is_si=True,
        )

        representation = ifcopenshell.api.geometry.add_axis_representation(
            self.house.model,
            context=self.house._annotation_context,
            axis=[(0.0, 0.0), (length, 0.0)],
        )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model,
            product=annotation,
            representation=representation,
        )
        pset = ifcopenshell.api.pset.add_pset(
            self.house.model,
            product=annotation,
            name="BBIM_Batting",
        )
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=pset,
            properties={"Thickness": thickness},
        )
        return annotation

    def beam(
        self,
        name: str,
        *,
        start: Point3D,
        end: Point3D,
        size: Sequence[Number],
        material: str = "Wood",
        kind: BeamKind = "BEAM",
        rotation: Number = 0,
        color: str | None = None,
        transparency: Number = 0,
        height_axis: Point3D | None = None,
        cuts: Sequence[PlaneCut] | None = None,
    ) -> Beam:
        """Create a rectangular beam between two world-coordinate points.

        ``start`` and ``end`` are the beam centreline endpoints in global XYZ
        coordinates.  ``size`` is ``(width, height)`` perpendicular to that
        centreline.  The height axis stays as vertical as the beam direction
        permits, while ``rotation`` applies a right-hand roll in degrees about
        the start-to-end axis.  ``height_axis`` may supply another global
        reference direction, such as a roof-plane normal.  Global three-point
        ``cuts`` retain the side containing the uncut beam centre.

        IFC4 has no dedicated rafter or purlin enum, so ``"RAFTER"`` and
        ``"PURLIN"`` are stored as user-defined ``IfcBeam`` types.  Wood is
        shown brown by default unless the house has a default beam color or an
        explicit ``color`` is supplied.
        """
        beam_name = _name(name, "name")
        start_point = _point_3d(start, "start")
        end_point = _point_3d(end, "end")
        if isinstance(size, (str, bytes)):
            raise TypeError("size must contain exactly two dimensions")
        try:
            width, height = size
        except (TypeError, ValueError) as error:
            raise TypeError(
                "size must contain exactly two dimensions"
            ) from error
        width = _number(width, "size width")
        height = _number(height, "size height")
        if width <= 0 or height <= 0:
            raise ValueError("size dimensions must be greater than zero")
        material_name = _name(material, "material")
        kind = _enum(kind, "kind", _BEAM_KINDS)
        rotation = _number(rotation, "rotation")

        start_vector = np.array(start_point, dtype=float)
        end_vector = np.array(end_point, dtype=float)
        direction = end_vector - start_vector
        length = float(np.linalg.norm(direction))
        if length == 0:
            raise ValueError("beam start and end must be different points")
        local_x = direction / length

        # Project the requested height reference into the plane normal to the
        # beam.  The default keeps ordinary beam sections as upright as their
        # direction permits; roof planes supply their own normal instead.
        supplied_height_axis = height_axis
        reference_height = np.array(
            (0.0, 0.0, 1.0)
            if supplied_height_axis is None
            else _point_3d(supplied_height_axis, "height_axis"),
            dtype=float,
        )
        reference_length = float(np.linalg.norm(reference_height))
        if reference_length <= 1e-9:
            raise ValueError("height_axis must not be a zero vector")
        reference_height /= reference_length
        local_z = reference_height - np.dot(reference_height, local_x) * local_x
        local_z_length = float(np.linalg.norm(local_z))
        if local_z_length < 1e-9:
            if supplied_height_axis is not None:
                raise ValueError("height_axis must not be parallel to the beam")
            fallback = np.array((0.0, 1.0, 0.0), dtype=float)
            local_z = fallback - np.dot(fallback, local_x) * local_x
            local_z_length = float(np.linalg.norm(local_z))
        local_z /= local_z_length
        local_y = np.cross(local_z, local_x)
        local_y /= np.linalg.norm(local_y)

        roll = radians(rotation)
        rolled_y = cos(roll) * local_y + sin(roll) * local_z
        rolled_z = -sin(roll) * local_y + cos(roll) * local_z
        placement = np.eye(4)
        placement[:3, 0] = local_x
        placement[:3, 1] = rolled_y
        placement[:3, 2] = rolled_z
        placement[:3, 3] = start_vector
        normalised_cuts = _plane_cuts(cuts)
        clippings = _local_clippings(
            normalised_cuts,
            placement,
            (length / 2, 0.0, 0.0),
        )

        predefined_type = (
            "USERDEFINED" if kind in {"RAFTER", "PURLIN"} else kind
        )
        model = self.house.model
        element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcBeam",
            name=beam_name,
            predefined_type=predefined_type,
        )
        if kind in {"RAFTER", "PURLIN"}:
            element.ObjectType = kind
        elif kind == "USERDEFINED":
            element.ObjectType = beam_name
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[element],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=element,
            matrix=placement,
            is_si=True,
        )

        profile = model.createIfcRectangleProfileDef(
            "AREA",
            f"{beam_name} Profile",
            None,
            width,
            height,
        )
        body = ifcopenshell.api.geometry.add_profile_representation(
            model,
            context=self.house._body_context,
            profile=profile,
            depth=length,
            cardinal_point="mid-depth centre",
            placement_zx_axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        )
        _clip_body_representation(model, element, body, clippings)
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=element,
            representation=body,
        )

        resolved_color = color
        if (
            resolved_color is None
            and "beam" not in self.house._default_colors
            and material_name.casefold() == "wood"
        ):
            resolved_color = "#8B5A2B"
        surface_style = self.house._surface_style(
            "beam",
            color=resolved_color,
            transparency=transparency,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        ifc_material = self.house._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category=material_name.casefold(),
            )
            self.house._materials[material_name] = ifc_material
        ifcopenshell.api.material.assign_material(
            model,
            products=[element],
            type="IfcMaterial",
            material=ifc_material,
        )
        common_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=element,
            name="Pset_BeamCommon",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=common_pset,
            properties={"LoadBearing": True},
        )

        return Beam(
            element,
            self,
            start=start_point,
            end=end_point,
            size=(width, height),
            length=length,
            kind=kind,
            material_name=material_name,
            rotation=rotation,
            height_axis=tuple(float(value) for value in reference_height),
            cuts=normalised_cuts,
            placement=placement,
        )

    def asset(
        self,
        name: str,
        *,
        asset: str | AssetInfo | None = None,
        type_name: str | None = None,
        center: Point,
        rotation: Number = 0,
        start_height: Number = 0,
        label: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Place a plan-ready object from :attr:`House.assets`.

        Use the stable friendly ``asset`` alias returned by
        ``house.assets.search(...)`` or, as an advanced escape hatch, pass the
        library's exact ``type_name``.  ``center`` is the centre of the
        object's 3D bounding box in plan, independent of the library type's
        original drawing origin.  ``rotation`` is counter-clockwise in
        degrees, and ``start_height`` places the bottom of the object above
        this storey's elevation.
        """
        object_name = _name(name, "name")
        center_x, center_y = _point(center, "center")
        rotation = _number(rotation, "rotation")
        start_height = _number(start_height, "start_height")
        if start_height < 0:
            raise ValueError("start_height must be zero or greater")
        label_text = None if label is None else _name(label, "label")

        catalog = self.house.assets
        entry = catalog._resolve(asset=asset, type_name=type_name)
        imported_type = catalog._import_type(entry)
        model = self.house.model
        occurrence = ifcopenshell.api.root.create_entity(
            model,
            ifc_class=entry.ifc_class,
            name=object_name,
        )
        ifcopenshell.api.type.assign_type(
            model,
            related_objects=[occurrence],
            relating_type=imported_type,
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[occurrence],
            relating_structure=self.element,
        )

        min_x, min_y, min_z, max_x, max_y, max_z = catalog._local_bounds(
            entry, occurrence
        )
        local_center_x = (min_x + max_x) / 2
        local_center_y = (min_y + max_y) / 2
        angle = radians(rotation)
        cosine = cos(angle)
        sine = sin(angle)
        placement = np.eye(4)
        placement[0, 0] = cosine
        placement[0, 1] = -sine
        placement[1, 0] = sine
        placement[1, 1] = cosine
        placement[0, 3] = center_x - (
            cosine * local_center_x - sine * local_center_y
        )
        placement[1, 3] = center_y - (
            sine * local_center_x + cosine * local_center_y
        )
        placement[2, 3] = self.elevation + start_height - min_z
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=occurrence,
            matrix=placement,
            is_si=True,
        )

        if label_text is not None:
            label_placement = placement.copy()
            label_placement[0, 3] = center_x
            label_placement[1, 3] = center_y
            label_placement[2, 3] = self.elevation + start_height
            self._add_plan_label(
                occurrence,
                name=object_name,
                text=label_text,
                placement=label_placement,
                width=max_x - min_x,
                depth=max_y - min_y,
            )
        return occurrence

    def _add_plan_label(
        self,
        product: ifcopenshell.entity_instance,
        *,
        name: str,
        text: str,
        placement: np.ndarray,
        width: float,
        depth: float,
    ) -> ifcopenshell.entity_instance:
        model = self.house.model
        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{name} Label",
            predefined_type="TEXT",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[annotation],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=placement,
            is_si=True,
        )
        literal_origin = model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            model.createIfcDirection((1.0, 0.0, 0.0)),
        )
        literal = model.createIfcTextLiteralWithExtent(
            text,
            literal_origin,
            "RIGHT",
            model.createIfcPlanarExtent(width, depth),
            "center",
        )
        label_representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "Annotation2D",
            [literal],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=label_representation,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={"Classes": "furniture-label small"},
        )
        ifcopenshell.api.drawing.assign_product(
            model,
            relating_product=product,
            related_object=annotation,
        )
        self.house._plan_annotations.append(annotation)
        for drawing in self.house._drawings:
            if drawing.view == "plan" and drawing._includes_storey(self):
                ifcopenshell.api.group.assign_group(
                    model,
                    group=drawing.group,
                    products=[annotation],
                )
        return annotation

    def furniture(
        self,
        name: str,
        *,
        kind: FurnitureKind,
        size: Sequence[Number],
        center: Point,
        rotation: Number = 0,
        start_height: Number = 0,
        color: str | None = None,
        transparency: Number = 0,
        label: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a semantic piece of furniture represented by a simple box.

        ``size`` is ``(width, depth, height)`` in the furniture's local axes.
        ``center`` locates the middle of the box in plan, ``rotation`` is
        counter-clockwise in degrees from global X, and ``start_height`` is
        measured above this storey's elevation.  The plan representation is a
        dashed rectangle with ``label`` centred inside; when omitted, the
        furniture name is used as the label.
        """
        furniture_name = _name(name, "name")
        kind = _enum(kind, "kind", _FURNITURE_KINDS)
        if isinstance(size, (str, bytes)):
            raise TypeError("size must contain exactly three dimensions")
        try:
            width, depth, height = size
        except (TypeError, ValueError) as error:
            raise TypeError(
                "size must contain exactly three dimensions"
            ) from error
        width = _number(width, "size width")
        depth = _number(depth, "size depth")
        height = _number(height, "size height")
        if width <= 0 or depth <= 0 or height <= 0:
            raise ValueError("size dimensions must be greater than zero")
        center_x, center_y = _point(center, "center")
        rotation = _number(rotation, "rotation")
        start_height = _number(start_height, "start_height")
        if start_height < 0:
            raise ValueError("start_height must be zero or greater")
        label_text = furniture_name if label is None else _name(label, "label")
        surface_style = self.house._surface_style(
            "furniture",
            color=color,
            transparency=transparency,
        )

        model = self.house.model
        furniture = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcFurniture",
            name=furniture_name,
            predefined_type=kind,
        )
        if kind == "USERDEFINED":
            furniture.ObjectType = furniture_name
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[furniture],
            relating_structure=self.element,
        )

        angle = radians(rotation)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = center_x
        placement[1, 3] = center_y
        placement[2, 3] = self.elevation + start_height
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=furniture,
            matrix=placement,
            is_si=True,
        )

        half_width = width / 2
        half_depth = depth / 2
        footprint = [
            (-half_width, -half_depth),
            (half_width, -half_depth),
            (half_width, half_depth),
            (-half_width, half_depth),
        ]
        body = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.house._body_context,
            depth=height,
            polyline=footprint,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=furniture,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        plan = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._plan_body_context,
            axis=[*footprint, footprint[0]],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=furniture,
            representation=plan,
        )

        self._add_plan_label(
            furniture,
            name=furniture_name,
            text=label_text,
            placement=placement.copy(),
            width=width,
            depth=depth,
        )
        return furniture

    def miako_slab(
        self,
        name: str,
        *,
        start: Point,
        end: Point,
        top: Number,
        direction: Point,
        structure: Sequence[MiakoStructureItem],
        block_length: Number = 0.25,
        block_height: Number = 0.19,
        topping: Number = 0.06,
        beam_height: Number | None = None,
        beam_color: str | None = "#bfc3c5",
        beam_shell_color: str | None = "#d98245",
        reinforcement_color: str | None = "#333333",
        wide_color: str | None = "blue",
        narrow_color: str | None = "green",
        concrete_color: str | None = None,
        transparency: Number = 0,
    ) -> MiakoSlab:
        """Create a detailed MIAKO floor slab from a crosswise strip layout.

        ``start`` and ``end`` define the joist span.  ``direction`` must be
        perpendicular to that line and selects the side on which the slab is
        constructed.  Items in ``structure`` are inserted successively in
        that direction: ``"beam"`` is 0.17 m wide, ``"wide"`` is a 0.455 m
        block bay, and ``"narrow"`` is a 0.33 m block bay.  Consequently a
        wide bay plus a beam forms a 0.625 m module and a narrow bay plus a
        beam forms a 0.5 m module.

        ``top`` is measured from this storey's elevation.  The whole assembly
        extends downward by ``block_height + topping``.  ``beam_height`` is
        the height of the ceramic U-shell (60 mm by default), not the height
        of the complete concrete rib.  The precast concrete beam body fills
        the shell to that height.  Above it, one cast-in-place concrete cover
        has a stepped underside: 60 mm thick over the blocks and dropped ribs
        between them down to the beam bodies.  Its schematic reinforcement
        can therefore cross the joint between the beam body and cover.  Blocks
        use matching bearing lips at the shell top.  These profiles are
        extruded along the joist span.  Repeated components use mapped type
        geometry and are decomposed beneath one semantic ``IfcSlab`` contained
        by this storey.  The standard beam shell is 170 mm wide and 60 mm high.
        Its two lower reinforcement bars are centred 40 mm above the bottom,
        with a third bar centred at the 175 mm apex.  Two diagonal wires join
        the inner sides of the lower bars to the outer sides of the upper bar.
        Their respective color arguments may override the default 3D styles.
        """
        slab_name = _name(name, "name")
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        direction_x, direction_y = _point(direction, "direction")
        top = _number(top, "top")
        block_length = _number(block_length, "block_length")
        block_height = _number(block_height, "block_height")
        topping = _number(topping, "topping")
        if beam_height is None:
            beam_height = 0.06
        else:
            beam_height = _number(beam_height, "beam_height")
        for value, argument in (
            (block_length, "block_length"),
            (block_height, "block_height"),
            (topping, "topping"),
            (beam_height, "beam_height"),
        ):
            if value <= 0:
                raise ValueError(f"{argument} must be greater than zero")
        if beam_height > block_height:
            raise ValueError("beam_height must not be greater than block_height")
        if beam_height < 0.046:
            raise ValueError(
                "beam_height must be at least 0.046 m to contain the lower "
                "reinforcement bars"
            )
        if block_height + topping < 0.181:
            raise ValueError(
                "block_height + topping must be at least 0.181 m to contain "
                "the upper reinforcement bar"
            )

        span_x = end_x - start_x
        span_y = end_y - start_y
        length = hypot(span_x, span_y)
        if length == 0:
            raise ValueError("slab start and end must be different points")
        direction_length = hypot(direction_x, direction_y)
        if direction_length == 0:
            raise ValueError("direction must not be a zero vector")
        span_x /= length
        span_y /= length
        direction_x /= direction_length
        direction_y /= direction_length
        if abs(span_x * direction_x + span_y * direction_y) > 1e-6:
            raise ValueError("direction must be perpendicular to start-end line")

        if isinstance(structure, (str, bytes)):
            raise TypeError("structure must be a sequence of layout items")
        try:
            supplied_structure = list(structure)
        except TypeError as error:
            raise TypeError(
                "structure must be a sequence of layout items"
            ) from error
        if not supplied_structure:
            raise ValueError("structure must contain at least one item")
        normalised_structure: list[str] = []
        previous_was_block = False
        for index, supplied_item in enumerate(supplied_structure, start=1):
            item = _name(supplied_item, f"structure item {index}").lower()
            if item not in _MIAKO_WIDTHS:
                choices = ", ".join(_MIAKO_WIDTHS)
                raise ValueError(
                    f"structure item {index} must be one of: {choices}"
                )
            is_block = item in {"wide", "narrow"}
            if is_block and previous_was_block:
                raise ValueError("MIAKO block bays must be separated by a beam")
            normalised_structure.append(item)
            previous_was_block = is_block
        if "beam" not in normalised_structure:
            raise ValueError("structure must contain at least one beam")
        if not any(item in {"wide", "narrow"} for item in normalised_structure):
            raise ValueError("structure must contain at least one block bay")
        structure_tuple = tuple(normalised_structure)
        width = sum(_MIAKO_WIDTHS[item] for item in structure_tuple)

        beam_style = self.house._surface_style(
            "beam", color=beam_color, transparency=transparency
        )
        beam_shell_style = self.house._surface_style(
            "block", color=beam_shell_color, transparency=transparency
        )
        reinforcement_style = self.house._surface_style(
            "beam", color=reinforcement_color, transparency=transparency
        )
        wide_style = self.house._surface_style(
            "block", color=wide_color, transparency=transparency
        )
        narrow_style = self.house._surface_style(
            "block", color=narrow_color, transparency=transparency
        )
        concrete_style = self.house._surface_style(
            "slab", color=concrete_color, transparency=transparency
        )

        # Keep +Z upward and the placement right-handed.  The requested
        # direction is represented as a sign along the placement's local Y.
        local_y_x = -span_y
        local_y_y = span_x
        layout_sign = (
            1.0
            if direction_x * local_y_x + direction_y * local_y_y > 0
            else -1.0
        )
        bottom_elevation = self.elevation + top - block_height - topping
        placement = np.eye(4)
        placement[0, 0] = span_x
        placement[1, 0] = span_y
        placement[0, 1] = local_y_x
        placement[1, 1] = local_y_y
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = bottom_elevation

        model = self.house.model
        slab_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcSlab",
            name=slab_name,
            predefined_type="FLOOR",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[slab_element],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=slab_element,
            matrix=placement,
            is_si=True,
        )

        signed_width = layout_sign * width
        plan = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._plan_body_context,
            axis=[
                (0.0, 0.0),
                (length, 0.0),
                (length, signed_width),
                (0.0, signed_width),
                (0.0, 0.0),
            ],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=slab_element,
            representation=plan,
        )

        common_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=slab_element,
            name="Pset_SlabCommon",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=common_pset,
            properties={"LoadBearing": True},
        )
        miako_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=slab_element,
            name="BBIM_MiakoSlab",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=miako_pset,
            properties={
                "Structure": ",".join(structure_tuple),
                "SpanLength": length,
                "OverallWidth": width,
                "BlockLength": block_length,
                "BlockHeight": block_height,
                "BeamHeight": beam_height,
                "BeamShellHeight": beam_height,
                "ConcreteRibHeight": block_height + topping,
                "ConcreteCoverRibDepth": block_height + topping - beam_height,
                "ReinforcementApexHeight": 0.175,
                "ToppingThickness": topping,
            },
        )

        def get_material(
            material_name: str,
            category: str,
        ) -> ifcopenshell.entity_instance:
            material = self.house._materials.get(material_name)
            if material is None:
                material = ifcopenshell.api.material.add_material(
                    model,
                    name=material_name,
                    category=category,
                )
                self.house._materials[material_name] = material
            return material

        beam_material = get_material("MIAKO concrete", "concrete")
        beam_shell_material = get_material(
            "MIAKO beam ceramic", "ceramic"
        )
        block_material = get_material("MIAKO block ceramic", "ceramic")
        reinforcement_material = get_material(
            "MIAKO reinforcement", "steel"
        )
        concrete_material = get_material("Concrete topping", "concrete")

        beam_module_width = _MIAKO_WIDTHS["beam"]
        beam_bearing = 0.035
        beam_shell_thickness = 0.02
        beam_shell_height = beam_height
        reinforcement_wire_thickness = 0.003
        reinforcement_dot_z = 0.04
        reinforcement_dot_radius = 0.006
        reinforcement_base_inset = 0.055
        reinforcement_apex_z = 0.175
        reinforcement_apex_y = beam_module_width / 2
        block_lip_bottom = beam_shell_height

        def get_component_type(
            *,
            component: Literal[
                "beam",
                "beam_shell",
                "beam_reinforcement",
                "wide",
                "narrow",
            ],
            component_length: float,
            component_width: float,
            component_height: float,
            style: ifcopenshell.entity_instance | None,
            material: ifcopenshell.entity_instance,
        ) -> ifcopenshell.entity_instance:
            style_id = style.id() if style is not None else None
            key = (
                component,
                round(component_length, 9),
                round(component_width, 9),
                round(component_height, 9),
                round(block_lip_bottom, 9),
                int(layout_sign),
                style_id,
            )
            component_type = self.house._miako_component_types.get(key)
            if component_type is not None:
                return component_type

            if component == "beam":
                type_class = "IfcBeamType"
                predefined_type = "JOIST"
                type_name = (
                    f"MIAKO concrete beam core "
                    f"{component_width * 1000:.0f}x"
                    f"{component_height * 1000:.0f}, L={component_length:.3f} m"
                )
            elif component in {"beam_shell", "beam_reinforcement"}:
                type_class = "IfcBuildingElementPartType"
                predefined_type = "USERDEFINED"
                detail_name = (
                    "ceramic U-shell"
                    if component == "beam_shell"
                    else "reinforcement"
                )
                type_name = (
                    f"MIAKO beam {detail_name} "
                    f"{component_width * 1000:.0f}x"
                    f"{component_height * 1000:.0f}, L={component_length:.3f} m"
                )
            else:
                type_class = "IfcBuildingElementPartType"
                predefined_type = "USERDEFINED"
                type_name = (
                    f"MIAKO {component} block "
                    f"{component_length * 1000:.0f}x"
                    f"{component_width * 1000:.0f}x"
                    f"{component_height * 1000:.0f}"
                )
            component_type = ifcopenshell.api.root.create_entity(
                model,
                ifc_class=type_class,
                name=type_name,
                predefined_type=predefined_type,
            )
            if component in {"wide", "narrow"}:
                component_type.ElementType = f"MIAKO {component} block"
            elif component == "beam_shell":
                component_type.ElementType = "MIAKO beam ceramic U-shell"
            elif component == "beam_reinforcement":
                component_type.ElementType = "MIAKO beam reinforcement"
            signed_component_width = layout_sign * component_width
            builder = ShapeBuilder(model)

            def reinforcement_wire_profile(
                start: tuple[float, float],
                end: tuple[float, float],
            ) -> list[tuple[float, float]]:
                """Return a constant-width diagonal joining two bar sides."""
                delta_y = end[0] - start[0]
                delta_z = end[1] - start[1]
                wire_length = hypot(delta_y, delta_z)
                half_thickness = reinforcement_wire_thickness / 2
                normal_y = -delta_z / wire_length * half_thickness
                normal_z = delta_y / wire_length * half_thickness
                unsigned_points = [
                    (start[0] + normal_y, start[1] + normal_z),
                    (end[0] + normal_y, end[1] + normal_z),
                    (end[0] - normal_y, end[1] - normal_z),
                    (start[0] - normal_y, start[1] - normal_z),
                ]
                return [
                    (layout_sign * y, z) for y, z in unsigned_points
                ]

            # Each wire touches its lower bar on the side facing the centre
            # and the apex bar on the corresponding outside face.
            reinforcement_wire_profiles = [
                reinforcement_wire_profile(
                    (
                        reinforcement_base_inset + reinforcement_dot_radius,
                        reinforcement_dot_z,
                    ),
                    (
                        reinforcement_apex_y - reinforcement_dot_radius,
                        reinforcement_apex_z,
                    ),
                ),
                reinforcement_wire_profile(
                    (
                        component_width
                        - reinforcement_base_inset
                        - reinforcement_dot_radius,
                        reinforcement_dot_z,
                    ),
                    (
                        reinforcement_apex_y + reinforcement_dot_radius,
                        reinforcement_apex_z,
                    ),
                ),
            ]
            reinforcement_dot_centers = [
                (
                    layout_sign * reinforcement_base_inset,
                    reinforcement_dot_z,
                ),
                (
                    layout_sign
                    * (component_width - reinforcement_base_inset),
                    reinforcement_dot_z,
                ),
                (
                    layout_sign * reinforcement_apex_y,
                    reinforcement_apex_z,
                ),
            ]

            if component == "beam":
                # The precast concrete beam body only fills the ceramic
                # U-shell.  The cast-in-place cover supplies the narrower rib
                # above it, leaving a real material boundary at shell height.
                inner_start = layout_sign * beam_shell_thickness
                inner_end = (
                    signed_component_width
                    - layout_sign * beam_shell_thickness
                )
                profile_points = [
                    (inner_start, beam_shell_thickness),
                    (inner_end, beam_shell_thickness),
                    (inner_end, component_height),
                    (inner_start, component_height),
                ]
                outer_curve = builder.polyline(profile_points, closed=True)
                profile = builder.profile(outer_curve)
                solids = [
                    builder.extrude(
                        profile,
                        magnitude=component_length,
                        position_z_axis=(1.0, 0.0, 0.0),
                        position_x_axis=(0.0, 1.0, 0.0),
                    )
                ]
            elif component == "beam_shell":
                # A single concave polygon makes the orange precast ceramic
                # base a true U rather than three overlapping rectangles.
                inner_start = layout_sign * beam_shell_thickness
                inner_end = (
                    signed_component_width
                    - layout_sign * beam_shell_thickness
                )
                profile_points = [
                    (0.0, 0.0),
                    (signed_component_width, 0.0),
                    (signed_component_width, beam_shell_height),
                    (inner_end, beam_shell_height),
                    (inner_end, beam_shell_thickness),
                    (inner_start, beam_shell_thickness),
                    (inner_start, beam_shell_height),
                    (0.0, beam_shell_height),
                ]
                profile = builder.polyline(profile_points, closed=True)
                solids = [
                    builder.extrude(
                        profile,
                        magnitude=component_length,
                        position_z_axis=(1.0, 0.0, 0.0),
                        position_x_axis=(0.0, 1.0, 0.0),
                    )
                ]
            elif component == "beam_reinforcement":
                solids = [
                    builder.extrude(
                        builder.polyline(wire_profile, closed=True),
                        magnitude=component_length,
                        position_z_axis=(1.0, 0.0, 0.0),
                        position_x_axis=(0.0, 1.0, 0.0),
                    )
                    for wire_profile in reinforcement_wire_profiles
                ]
                solids.extend(
                    builder.extrude(
                        builder.circle(
                            center=center,
                            radius=reinforcement_dot_radius,
                        ),
                        magnitude=component_length,
                        position_z_axis=(1.0, 0.0, 0.0),
                        position_x_axis=(0.0, 1.0, 0.0),
                    )
                    for center in reinforcement_dot_centers
                )
            else:
                # Every block uses the same symmetric bearing profile,
                # including blocks at slab boundaries.  The 455 and 330 mm
                # bases extend 35 mm over each adjacent beam, giving upper
                # widths of 525 and 400 mm.  The rectangular underside rises
                # beside the beam shell, then steps outward to the concrete
                # rib or edge support.
                lip_bottom = min(block_lip_bottom, component_height)
                previous_edge = -layout_sign * beam_bearing
                next_edge = (
                    signed_component_width + layout_sign * beam_bearing
                )
                profile_points = [
                    (0.0, 0.0),
                    (signed_component_width, 0.0),
                    (signed_component_width, lip_bottom),
                    (next_edge, lip_bottom),
                    (next_edge, component_height),
                    (previous_edge, component_height),
                    (previous_edge, lip_bottom),
                    (0.0, lip_bottom),
                ]
                profile = builder.polyline(profile_points, closed=True)
                solids = [
                    builder.extrude(
                        profile,
                        magnitude=component_length,
                        position_z_axis=(1.0, 0.0, 0.0),
                        position_x_axis=(0.0, 1.0, 0.0),
                    )
                ]
            representation = builder.get_representation(
                self.house._body_context,
                solids,
            )
            if style is not None:
                ifcopenshell.api.style.assign_representation_styles(
                    model,
                    shape_representation=representation,
                    styles=[style],
                )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=component_type,
                representation=representation,
            )
            ifcopenshell.api.material.assign_material(
                model,
                products=[component_type],
                type="IfcMaterial",
                material=material,
            )
            self.house._miako_component_types[key] = component_type
            return component_type

        def component_placement(
            local_x: float,
            local_y: float,
            local_z: float,
        ) -> np.ndarray:
            result = placement.copy()
            result[:3, 3] = (
                placement
                @ np.array((local_x, local_y, local_z, 1.0), dtype=float)
            )[:3]
            return result

        components: list[ifcopenshell.entity_instance] = []
        component_placements: list[np.ndarray] = []
        beams: list[ifcopenshell.entity_instance] = []
        beam_shells: list[ifcopenshell.entity_instance] = []
        reinforcements: list[ifcopenshell.entity_instance] = []
        blocks: list[ifcopenshell.entity_instance] = []
        offset = 0.0
        beam_number = 0
        bay_number = 0
        tolerance = 1e-9
        full_block_count = int(length / block_length)
        remainder = length - full_block_count * block_length
        if remainder < tolerance:
            remainder = 0.0
        elif block_length - remainder < tolerance:
            full_block_count += 1
            remainder = 0.0

        for item in structure_tuple:
            item_width = _MIAKO_WIDTHS[item]
            signed_offset = layout_sign * offset
            if item == "beam":
                beam_number += 1
                beam = ifcopenshell.api.root.create_entity(
                    model,
                    ifc_class="IfcBeam",
                    name=f"{slab_name} Beam {beam_number}",
                    predefined_type="JOIST",
                )
                beam_type = get_component_type(
                    component="beam",
                    component_length=length,
                    component_width=item_width,
                    component_height=beam_height,
                    style=beam_style,
                    material=beam_material,
                )
                ifcopenshell.api.type.assign_type(
                    model,
                    related_objects=[beam],
                    relating_type=beam_type,
                )
                beam_shell = ifcopenshell.api.root.create_entity(
                    model,
                    ifc_class="IfcBuildingElementPart",
                    name=f"{slab_name} Beam {beam_number} Ceramic U-shell",
                    predefined_type="USERDEFINED",
                )
                beam_shell.ObjectType = "MIAKO beam ceramic U-shell"
                beam_shell_type = get_component_type(
                    component="beam_shell",
                    component_length=length,
                    component_width=item_width,
                    component_height=beam_height,
                    style=beam_shell_style,
                    material=beam_shell_material,
                )
                ifcopenshell.api.type.assign_type(
                    model,
                    related_objects=[beam_shell],
                    relating_type=beam_shell_type,
                )
                reinforcement = ifcopenshell.api.root.create_entity(
                    model,
                    ifc_class="IfcBuildingElementPart",
                    name=f"{slab_name} Beam {beam_number} Reinforcement",
                    predefined_type="USERDEFINED",
                )
                reinforcement.ObjectType = "MIAKO beam reinforcement"
                reinforcement_type = get_component_type(
                    component="beam_reinforcement",
                    component_length=length,
                    component_width=item_width,
                    component_height=(
                        reinforcement_apex_z + reinforcement_dot_radius
                    ),
                    style=reinforcement_style,
                    material=reinforcement_material,
                )
                ifcopenshell.api.type.assign_type(
                    model,
                    related_objects=[reinforcement],
                    relating_type=reinforcement_type,
                )
                beams.append(beam)
                beam_shells.append(beam_shell)
                reinforcements.append(reinforcement)
                beam_placement = component_placement(
                    0.0,
                    signed_offset,
                    0.0,
                )
                components.extend((beam, beam_shell, reinforcement))
                component_placements.extend(
                    (
                        beam_placement,
                        beam_placement.copy(),
                        beam_placement.copy(),
                    )
                )
            else:
                bay_number += 1
                block_lengths = [block_length] * full_block_count
                if remainder:
                    block_lengths.append(remainder)
                along = 0.0
                for block_number, current_length in enumerate(
                    block_lengths,
                    start=1,
                ):
                    block = ifcopenshell.api.root.create_entity(
                        model,
                        ifc_class="IfcBuildingElementPart",
                        name=(
                            f"{slab_name} {item.title()} Block "
                            f"{bay_number}.{block_number}"
                        ),
                        predefined_type="USERDEFINED",
                    )
                    block.ObjectType = f"MIAKO {item} block"
                    block_type = get_component_type(
                        component=item,
                        component_length=current_length,
                        component_width=item_width,
                        component_height=block_height,
                        style=wide_style if item == "wide" else narrow_style,
                        material=block_material,
                    )
                    ifcopenshell.api.type.assign_type(
                        model,
                        related_objects=[block],
                        relating_type=block_type,
                    )
                    blocks.append(block)
                    components.append(block)
                    component_placements.append(
                        component_placement(along, signed_offset, 0.0)
                    )
                    along += current_length
            offset += item_width

        topping_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcBuildingElementPart",
            name=f"{slab_name} Concrete Cover",
            predefined_type="USERDEFINED",
        )
        topping_element.ObjectType = "Concrete cover with ribs"

        # Create the cover as one continuous comb-shaped section.  Its lower
        # face is at block height over every ceramic bay, but drops to the top
        # of each 60 mm beam body through the 100 mm concrete stem.  A single
        # profile avoids an artificial horizontal joint at block height.
        cover_bottom_points: list[tuple[float, float]] = [
            (0.0, block_height)
        ]
        cover_offset = 0.0
        for item in structure_tuple:
            item_width = _MIAKO_WIDTHS[item]
            if item == "beam":
                stem_start = cover_offset + beam_bearing
                stem_end = cover_offset + item_width - beam_bearing
                cover_bottom_points.extend(
                    (
                        (layout_sign * stem_start, block_height),
                        (layout_sign * stem_start, beam_height),
                        (layout_sign * stem_end, beam_height),
                        (layout_sign * stem_end, block_height),
                    )
                )
            cover_offset += item_width
        cover_bottom_points.append((signed_width, block_height))
        cover_profile_points = [
            *cover_bottom_points,
            (signed_width, block_height + topping),
            (0.0, block_height + topping),
        ]
        cover_builder = ShapeBuilder(model)
        cover_profile = cover_builder.polyline(
            cover_profile_points,
            closed=True,
        )
        cover_solid = cover_builder.extrude(
            cover_profile,
            magnitude=length,
            position_z_axis=(1.0, 0.0, 0.0),
            position_x_axis=(0.0, 1.0, 0.0),
        )
        topping_representation = cover_builder.get_representation(
            self.house._body_context,
            cover_solid,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=topping_element,
            representation=topping_representation,
        )
        if concrete_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=topping_representation,
                styles=[concrete_style],
            )
        ifcopenshell.api.material.assign_material(
            model,
            products=[topping_element],
            type="IfcMaterial",
            material=concrete_material,
        )
        components.append(topping_element)
        component_placements.append(
            component_placement(0.0, 0.0, 0.0)
        )

        ifcopenshell.api.aggregate.assign_object(
            model,
            products=components,
            relating_object=slab_element,
        )
        for component, component_matrix in zip(
            components,
            component_placements,
        ):
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=component,
                matrix=component_matrix,
                is_si=True,
            )

        return MiakoSlab(
            slab_element,
            self,
            start=(start_x, start_y),
            end=(end_x, end_y),
            direction=(direction_x, direction_y),
            structure=structure_tuple,
            length=length,
            width=width,
            top=top,
            block_length=block_length,
            block_height=block_height,
            beam_height=beam_height,
            topping=topping,
            placement=placement,
            beams=tuple(beams),
            beam_shells=tuple(beam_shells),
            reinforcements=tuple(reinforcements),
            blocks=tuple(blocks),
            topping_element=topping_element,
        )

    def chimney(
        self,
        center: Point,
        *,
        size: Number,
        height: Number,
        flue_diameter: Number,
        start_height: Number = 0,
        material: str = "Chimney",
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Chimney:
        """Create a square chimney with a central circular flue void.

        ``center`` locates the stack in plan, ``size`` is its outside side
        length, and ``height`` is its vertical extent.  ``start_height`` is
        measured above this storey's elevation.  ``material`` is persisted as
        an IFC material and supplies the drawing material class.  ``color``
        and ``transparency`` affect only the 3D body.
        """
        center_x, center_y = _point(center, "center")
        size = _number(size, "size")
        height = _number(height, "height")
        flue_diameter = _number(flue_diameter, "flue_diameter")
        start_height = _number(start_height, "start_height")
        material_name = _name(material, "material")
        if size <= 0:
            raise ValueError("size must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if flue_diameter <= 0:
            raise ValueError("flue_diameter must be greater than zero")
        if flue_diameter >= size:
            raise ValueError("flue_diameter must be smaller than size")
        surface_style = self.house._surface_style(
            "chimney",
            color=color,
            transparency=transparency,
        )

        self._chimney_count += 1
        chimney_name = (
            _name(name, "name")
            if name is not None
            else f"Chimney {self._chimney_count}"
        )
        model = self.house.model
        chimney_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcChimney",
            name=chimney_name,
            predefined_type="NOTDEFINED",
        )
        placement = np.eye(4)
        placement[0, 3] = center_x
        placement[1, 3] = center_y
        placement[2, 3] = self.elevation + start_height
        chimney = Chimney(
            chimney_element,
            self,
            center=(center_x, center_y),
            size=size,
            height=height,
            flue_diameter=flue_diameter,
            start_height=start_height,
            placement=placement,
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[chimney],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=chimney,
            matrix=placement,
            is_si=True,
        )

        half_size = size / 2
        outer_points = model.createIfcCartesianPointList2D(
            [
                (-half_size, -half_size),
                (half_size, -half_size),
                (half_size, half_size),
                (-half_size, half_size),
                (-half_size, -half_size),
            ]
        )
        outer_curve = model.createIfcIndexedPolyCurve(
            outer_points,
            None,
            False,
        )
        flue_position = model.createIfcAxis2Placement2D(
            model.createIfcCartesianPoint((0.0, 0.0)),
            model.createIfcDirection((1.0, 0.0)),
        )
        flue_curve = model.createIfcCircle(flue_position, flue_diameter / 2)
        profile = model.createIfcArbitraryProfileDefWithVoids(
            "AREA",
            f"{chimney_name} Profile",
            outer_curve,
            [flue_curve],
        )
        body = ifcopenshell.api.geometry.add_profile_representation(
            model,
            context=self.house._body_context,
            profile=profile,
            depth=height,
            cardinal_point=None,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=chimney,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )
        ifc_material = self.house._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category="masonry",
            )
            self.house._materials[material_name] = ifc_material
        ifcopenshell.api.material.assign_material(
            model,
            products=[chimney],
            type="IfcMaterial",
            material=ifc_material,
        )

        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=chimney,
            name="Pset_ChimneyCommon",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={"NumberOfDrafts": 1},
        )
        return chimney

    def stair_landing(
        self,
        start: Point,
        end: Point,
        *,
        height: Number,
        thickness: Number,
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> ifcopenshell.entity_instance:
        """Create a rectangular stair landing between two opposite corners.

        ``height`` is the coordinate of the landing's top surface measured
        above this storey's elevation.  The slab extends downward by
        ``thickness``.  ``color`` and ``transparency`` affect only its 3D body.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        height = _number(height, "height")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        min_x, max_x = sorted((start_x, end_x))
        min_y, max_y = sorted((start_y, end_y))
        width = max_x - min_x
        depth = max_y - min_y
        if width == 0 or depth == 0:
            raise ValueError("landing corners must define a rectangle")
        surface_style = self.house._surface_style(
            "stair",
            color=color,
            transparency=transparency,
        )

        self._landing_count += 1
        landing_name = (
            _name(name, "name")
            if name is not None
            else f"Stair Landing {self._landing_count}"
        )
        model = self.house.model
        landing = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcSlab",
            name=landing_name,
            predefined_type="LANDING",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[landing],
            relating_structure=self.element,
        )
        placement = np.eye(4)
        placement[0, 3] = min_x
        placement[1, 3] = min_y
        placement[2, 3] = self.elevation + height - thickness
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=landing,
            matrix=placement,
            is_si=True,
        )
        body = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.house._body_context,
            depth=thickness,
            polyline=[
                (0.0, 0.0),
                (width, 0.0),
                (width, depth),
                (0.0, depth),
            ],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=landing,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )
        return landing

    def stair(
        self,
        start: Point,
        end: Point,
        *,
        width: Number,
        height: Number,
        risers: int,
        start_height: Number = 0,
        underside: Literal["solid", "sloped"] = "solid",
        waist_thickness: Number = 0.15,
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Stair:
        """Create a semantic straight stair rising from ``start`` to ``end``.

        The points define the centre line of the horizontal run, with ``start``
        at the bottom and ``end`` at the upper landing edge.  ``start_height``
        is measured above this storey's elevation and defaults to zero.  The
        stair is centred on its plan line.  Its tread count is one less than
        ``risers``; riser height and tread length are calculated from the total
        rise ``height`` and horizontal run.  The returned stair exposes its
        calculated ``end_height`` for chaining another flight.  ``color`` and
        ``transparency`` affect only its 3D flight body.  Set ``underside`` to
        ``"sloped"`` to leave the space beneath the flight open;
        ``waist_thickness`` is the perpendicular structural thickness between
        the stair pitch line and its planar underside.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        width = _number(width, "width")
        height = _number(height, "height")
        start_height = _number(start_height, "start_height")
        if not isinstance(underside, str):
            raise TypeError("underside must be 'solid' or 'sloped'")
        if underside not in {"solid", "sloped"}:
            raise ValueError("underside must be 'solid' or 'sloped'")
        waist_thickness = _number(waist_thickness, "waist_thickness")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if waist_thickness <= 0:
            raise ValueError("waist_thickness must be greater than zero")
        if isinstance(risers, bool) or not isinstance(risers, int):
            raise TypeError("risers must be an integer")
        if risers < 2:
            raise ValueError("risers must be at least 2")

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("stair start and end must be different points")
        treads = risers - 1
        riser_height = height / risers
        tread_length = length / treads
        stepped_rise = treads * riser_height
        pitch_cosine = length / hypot(length, stepped_rise)
        underside_vertical_offset = waist_thickness / pitch_cosine
        if underside == "sloped" and underside_vertical_offset >= stepped_rise:
            raise ValueError("waist_thickness is too large for the stair flight")
        surface_style = self.house._surface_style(
            "stair",
            color=color,
            transparency=transparency,
        )

        self._stair_count += 1
        stair_name = (
            _name(name, "name")
            if name is not None
            else f"Stair {self._stair_count}"
        )
        model = self.house.model
        stair_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcStair",
            name=stair_name,
            predefined_type="STRAIGHT_RUN_STAIR",
        )
        flight = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcStairFlight",
            name=f"{stair_name} Flight",
            predefined_type="STRAIGHT",
        )
        flight.NumberOfRisers = risers
        flight.NumberOfTreads = treads
        flight.RiserHeight = riser_height
        flight.TreadLength = tread_length

        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = self.elevation + start_height
        stair = Stair(
            stair_element,
            self,
            flight=flight,
            start=(start_x, start_y),
            end=(end_x, end_y),
            length=length,
            width=width,
            height=height,
            start_height=start_height,
            risers=risers,
            treads=treads,
            riser_height=riser_height,
            tread_length=tread_length,
            underside=underside,
            waist_thickness=(
                waist_thickness if underside == "sloped" else None
            ),
            placement=placement,
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[stair],
            relating_structure=self.element,
        )
        ifcopenshell.api.aggregate.assign_object(
            model,
            products=[flight],
            relating_object=stair,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=stair,
            matrix=placement,
            is_si=True,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=flight,
            matrix=placement,
            is_si=True,
        )

        # Build one closed stepped solid.  A sloped underside is parallel to
        # the stair pitch line and clipped at the flight's starting elevation,
        # leaving a short solid bearing at the bottom.  The final riser is a
        # separate face: the upper storey floor acts as the landing instead of
        # another tread.
        profile: list[tuple[float, float]] = [(0.0, 0.0)]
        if underside == "sloped":
            underside_end_z = stepped_rise - underside_vertical_offset
            underside_start_x = (
                underside_vertical_offset * length / stepped_rise
            )
            profile.extend(
                [
                    (underside_start_x, 0.0),
                    (length, underside_end_z),
                ]
            )
        else:
            profile.append((length, 0.0))
        profile.append((length, stepped_rise))
        for tread in range(treads, 0, -1):
            x = (tread - 1) * tread_length
            profile.append((x, tread * riser_height))
            if tread > 1:
                profile.append((x, (tread - 1) * riser_height))

        half_width = width / 2
        vertices = [
            (x, -half_width, z)
            for x, z in profile
        ] + [
            (x, half_width, z)
            for x, z in profile
        ]
        profile_size = len(profile)
        faces: list[tuple[int, ...]] = [
            tuple(reversed(range(profile_size))),
            tuple(range(profile_size, 2 * profile_size)),
        ]
        for index in range(profile_size):
            next_index = (index + 1) % profile_size
            faces.append(
                (
                    index,
                    next_index,
                    next_index + profile_size,
                    index + profile_size,
                )
            )
        final_riser_depth = min(tread_length * 0.025, 0.005)
        final_riser_x = length - final_riser_depth
        final_riser_z = treads * riser_height
        final_riser_vertices = [
            (final_riser_x, -half_width, final_riser_z),
            (length, -half_width, final_riser_z),
            (length, half_width, final_riser_z),
            (final_riser_x, half_width, final_riser_z),
            (final_riser_x, -half_width, height),
            (length, -half_width, height),
            (length, half_width, height),
            (final_riser_x, half_width, height),
        ]
        final_riser_start = len(vertices)
        vertices.extend(final_riser_vertices)
        faces.extend(
            [
                tuple(final_riser_start + index for index in (1, 2, 3, 0)),
                tuple(final_riser_start + index for index in (7, 6, 5, 4)),
                tuple(final_riser_start + index for index in (4, 5, 1, 0)),
                tuple(final_riser_start + index for index in (5, 6, 2, 1)),
                tuple(final_riser_start + index for index in (6, 7, 3, 2)),
                tuple(final_riser_start + index for index in (7, 4, 0, 3)),
            ]
        )
        body = ifcopenshell.api.geometry.add_mesh_representation(
            model,
            context=self.house._body_context,
            vertices=[vertices],
            faces=[faces],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=flight,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=flight,
            name="Pset_StairFlightCommon",
        )
        pset_properties = {
            "NumberOfRiser": risers,
            "NumberOfTreads": treads,
            "RiserHeight": riser_height,
            "TreadLength": tread_length,
        }
        if underside == "sloped":
            pset_properties["WaistThickness"] = waist_thickness
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties=pset_properties,
        )
        return stair

    def wall(
        self,
        start: Point,
        end: Point,
        *,
        thickness: Number | None = None,
        height: Number,
        start_height: Number = 0,
        wall_type: ifcopenshell.entity_instance | None = None,
        cuts: Sequence[WallCut] | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Wall:
        """Create a straight wall whose axis runs from ``start`` to ``end``.

        Points, thickness and height are in metres.  ``start_height`` is the
        wall bottom above this storey's elevation and ``height`` is its
        vertical extent.  Supply either a direct ``thickness`` or a reusable
        ``wall_type`` created by :meth:`House.wall_type`.  Direct-thickness
        walls are centred on their axis; layered walls use their type's
        optional ``"axis"`` marker.
        Each item in ``cuts`` contains three world-coordinate points defining
        an infinite clipping plane.  Point order does not matter: the side
        containing the original wall centre is retained and the opposite
        half-space is removed.  Multiple planes are applied cumulatively.
        ``color`` and ``transparency`` affect only the 3D body.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        if thickness is None and wall_type is None:
            raise ValueError("either thickness or wall_type must be supplied")
        if thickness is not None and wall_type is not None:
            raise ValueError("thickness and wall_type must not both be supplied")
        body_offset: float
        usage_offset: float
        if wall_type is not None:
            is_wall_type = isinstance(
                wall_type, ifcopenshell.entity_instance
            ) and wall_type.is_a("IfcWallType")
            if not is_wall_type:
                raise TypeError("wall_type must be an IfcWallType")
            if wall_type.file is not self.house.model:
                raise ValueError("wall_type must belong to this house")
            layer_set = ifcopenshell.util.element.get_material(wall_type)
            if not layer_set or not layer_set.is_a("IfcMaterialLayerSet"):
                raise ValueError("wall_type must have an IfcMaterialLayerSet")
            thickness = sum(layer.LayerThickness for layer in layer_set.MaterialLayers)
            body_offset, usage_offset = self.house._wall_type_layouts.get(
                wall_type.id(), (-thickness / 2, thickness / 2)
            )
        else:
            thickness = _number(thickness, "thickness")
            body_offset = -thickness / 2
            usage_offset = thickness / 2
        height = _number(height, "height")
        start_height = _number(start_height, "start_height")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if start_height < 0:
            raise ValueError("start_height must be zero or greater")
        transparency = _number(transparency, "transparency")
        if not 0 <= transparency <= 1:
            raise ValueError("transparency must be between 0 and 1")

        if color is None and transparency == 0 and wall_type is not None:
            surface_style = self.house._wall_type_styles.get(wall_type.id())
        else:
            surface_style = self.house._surface_style(
                "wall",
                color=color,
                transparency=transparency,
            )

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("wall start and end must be different points")

        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = self.elevation + start_height

        if cuts is None:
            supplied_cuts: list[WallCut] = []
        else:
            if isinstance(cuts, (str, bytes)):
                raise TypeError("cuts must be a sequence of three-point planes")
            try:
                supplied_cuts = list(cuts)
            except TypeError as error:
                raise TypeError(
                    "cuts must be a sequence of three-point planes"
                ) from error

        normalised_cuts: list[WallCut] = []
        clippings: list[dict[str, tuple[float, float, float]]] = []
        world_to_local = np.linalg.inv(placement)
        wall_centre = np.array(
            (length / 2, body_offset + thickness / 2, height / 2),
            dtype=float,
        )
        for cut_index, supplied_cut in enumerate(supplied_cuts, start=1):
            if isinstance(supplied_cut, (str, bytes)):
                raise TypeError(
                    f"cut {cut_index} must contain exactly three points"
                )
            try:
                supplied_points = list(supplied_cut)
            except TypeError as error:
                raise TypeError(
                    f"cut {cut_index} must contain exactly three points"
                ) from error
            if len(supplied_points) != 3:
                raise TypeError(
                    f"cut {cut_index} must contain exactly three points"
                )
            world_points = tuple(
                _point_3d(point, f"cut {cut_index} point {point_index}")
                for point_index, point in enumerate(supplied_points, start=1)
            )
            local_points = [
                (
                    world_to_local
                    @ np.array((*point, 1.0), dtype=float)
                )[:3]
                for point in world_points
            ]
            normal = np.cross(
                local_points[1] - local_points[0],
                local_points[2] - local_points[0],
            )
            normal_length = float(np.linalg.norm(normal))
            if normal_length <= 1e-9:
                raise ValueError(f"cut {cut_index} points must not be collinear")
            normal /= normal_length
            centre_side = float(
                np.dot(normal, wall_centre - local_points[0])
            )
            if abs(centre_side) <= 1e-9:
                raise ValueError(
                    f"cut {cut_index} passes through the wall centre; "
                    "the retained side is ambiguous"
                )
            # If the normal points at the centre, reverse it.  IfcOpenShell's
            # clipping normal points into removed rather than retained matter.
            if centre_side > 0:
                normal *= -1
            normalised_cuts.append(world_points)
            clippings.append(
                {
                    "location": tuple(float(value) for value in local_points[0]),
                    "normal": tuple(float(value) for value in normal),
                }
            )

        self._wall_count += 1
        wall_element = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcWall",
            name=f"Wall {self._wall_count}",
        )
        wall = Wall(
            wall_element,
            self,
            start=(start_x, start_y),
            end=(end_x, end_y),
            length=length,
            height=height,
            start_height=start_height,
            thickness=thickness,
            body_offset=body_offset,
            surface_style=surface_style,
            cuts=tuple(normalised_cuts),
        )
        ifcopenshell.api.spatial.assign_container(
            self.house.model, products=[wall], relating_structure=self.element
        )
        if wall_type is not None:
            ifcopenshell.api.type.assign_type(
                self.house.model,
                related_objects=[wall],
                relating_type=wall_type,
            )
            material_relationship = ifcopenshell.api.material.assign_material(
                self.house.model,
                products=[wall],
                type="IfcMaterialLayerSetUsage",
            )
            usage = material_relationship.RelatingMaterial
            ifcopenshell.api.material.edit_layer_usage(
                self.house.model,
                usage=usage,
                attributes={
                    "DirectionSense": "NEGATIVE",
                    "OffsetFromReferenceLine": usage_offset,
                },
            )

        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=wall,
            matrix=placement,
            is_si=True,
        )

        body = ifcopenshell.api.geometry.add_wall_representation(
            self.house.model,
            context=self.house._body_context,
            length=length,
            height=height,
            thickness=thickness,
            offset=body_offset,
        )
        if clippings:
            item = body.Items[0]
            clipping_ids: list[int] = []
            for clipping in clippings:
                item = ifcopenshell.api.geometry.clip_solid(
                    self.house.model,
                    item=item,
                    location=clipping["location"],
                    normal=clipping["normal"],
                )
                clipping_ids.append(item.id())
            body.Items = [item]
            body.RepresentationType = "Clipping"
            boolean_pset = ifcopenshell.api.pset.add_pset(
                self.house.model,
                product=wall,
                name="BBIM_Boolean",
            )
            ifcopenshell.api.pset.edit_pset(
                self.house.model,
                pset=boolean_pset,
                properties={"Data": json.dumps(clipping_ids)},
            )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model, product=wall, representation=body
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                self.house.model,
                shape_representation=body,
                styles=[surface_style],
            )

        axis = ifcopenshell.api.geometry.add_axis_representation(
            self.house.model,
            context=self.house._axis_context,
            axis=[(0.0, 0.0), (length, 0.0)],
        )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model, product=wall, representation=axis
        )
        return wall

    def connect_wall(
        self,
        wall_1: ifcopenshell.entity_instance,
        wall_2: ifcopenshell.entity_instance,
        *,
        is_atpath: bool = False,
    ) -> ifcopenshell.entity_instance:
        """Connect two layered walls and regenerate their joined bodies.

        By default, the nearest end of each wall is joined, which produces an
        L-shaped mitre for two equally prioritised layers.  Set ``is_atpath``
        to true when the end of ``wall_1`` should terminate along the path of
        ``wall_2``, such as at a T-junction.
        """
        if wall_1 == wall_2:
            raise ValueError("a wall cannot be connected to itself")
        if not isinstance(is_atpath, bool):
            raise TypeError("is_atpath must be a boolean")

        for wall, argument in ((wall_1, "wall_1"), (wall_2, "wall_2")):
            is_wall = isinstance(
                wall, ifcopenshell.entity_instance
            ) and wall.is_a("IfcWall")
            if not is_wall:
                raise TypeError(f"{argument} must be an IfcWall")
            if wall.file is not self.house.model:
                raise ValueError(f"{argument} must belong to this house")
            container = ifcopenshell.util.element.get_container(
                wall,
                ifc_class="IfcBuildingStorey",
            )
            if container != self.element:
                raise ValueError(f"{argument} must belong to this storey")
            usage = ifcopenshell.util.element.get_material(wall)
            if not usage or not usage.is_a("IfcMaterialLayerSetUsage"):
                raise ValueError(
                    f"{argument} must use an IfcMaterialLayerSetUsage"
                )

        connection = ifcopenshell.api.geometry.connect_wall(
            self.house.model,
            wall_1,
            wall_2,
            is_atpath=is_atpath,
        )
        if connection is None:
            raise ValueError("wall axes must intersect")

        for wall in (wall_1, wall_2):
            representation = (
                ifcopenshell.api.geometry.regenerate_wall_representation(
                    self.house.model,
                    wall,
                )
            )
            if representation is None:
                raise ValueError("wall body could not be regenerated")
            surface_style = wall.surface_style if isinstance(wall, Wall) else None
            if surface_style is not None:
                ifcopenshell.api.style.assign_representation_styles(
                    self.house.model,
                    shape_representation=representation,
                    styles=[surface_style],
                )
        return connection
