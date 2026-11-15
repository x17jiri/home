"""Generate the generic FCU sample without placing equipment in the house plans."""

from pathlib import Path
import json
import subprocess
from tempfile import TemporaryDirectory

import ifcopenshell.geom
import numpy as np

from ifc_utils import House


def make_preview(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    house = House("Wall-mounted fan coil sample")
    floor = house.storey("Sample", elevation=0)
    floor.wall((-.7, .115), (.7, .115), thickness=.15, height=2.7)
    unit = floor.fan_coil("Wall-mounted fan coil", center=(0, 0))
    plan = house.add_drawing("FCU plan", x=0, y=0, z=1.2, radius=.8, scale=10,
                             storeys=[floor], door_annotations=False)
    house.write(directory/"fan_coil.ifc")

    # Render the actual IFC mesh, including its outlet and material colours.
    shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), unit)
    vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
    faces = np.asarray(shape.geometry.faces).reshape(-1, 3)
    materials = shape.geometry.materials
    colours = [(m.diffuse.r(), m.diffuse.g(), m.diffuse.b()) for m in materials]
    with TemporaryDirectory(prefix="fan-coil-") as temporary:
        source = Path(temporary)/"mesh.json"
        source.write_text(json.dumps(dict(vertices=vertices.tolist(), faces=faces.tolist(),
                                         colours=colours, material_ids=list(shape.geometry.material_ids))))
        renderer = Path(__file__).resolve().parent/"bonsai_scripts"/"render_equipment_preview.py"
        subprocess.run(["blender", "--background", "--python", str(renderer), "--",
                        str(source), str((directory/"fan_coil.png").resolve())], check=True)
    plan.render(directory/"plan.svg", pdf=directory/"plan.pdf",
                title="Fan coil - plan (mounted above cut)")
    return directory


if __name__ == "__main__":
    make_preview(Path(__file__).resolve().parent/"projekt2"/"fan_coil_preview")
