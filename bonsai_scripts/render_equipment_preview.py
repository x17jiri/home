"""Render a standalone IFC equipment mesh exported by fan_coil_preview.py."""

import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


source, output = sys.argv[sys.argv.index("--")+1:]
data = json.loads(Path(source).read_text())
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new("Equipment IFC mesh")
mesh.from_pydata(data["vertices"], [], data["faces"])
mesh.update()
unit = bpy.data.objects.new("Fan coil", mesh)
bpy.context.collection.objects.link(unit)
for index, colour in enumerate(data["colours"]):
    material = bpy.data.materials.new(f"IFC material {index}")
    material.diffuse_color = (*colour, 1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*colour, 1)
    shader.inputs["Roughness"].default_value = .42
    mesh.materials.append(material)
for polygon, material in zip(mesh.polygons, data["material_ids"]):
    polygon.material_index = material

bpy.ops.object.camera_add(location=(1.15, -2.3, .95))
camera = bpy.context.object
target = Vector((0, 0, .15))
camera.rotation_euler = (target-camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 1.35
scene = bpy.context.scene
scene.camera = camera
for location, power, size in (((-1, -2, 3), 140, 2), ((2, -1, 1), 70, 2), ((0, 2, 3), 100, 2)):
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.data.energy, light.data.shape, light.data.size = power, "DISK", size
    light.rotation_euler = (target-light.location).to_track_quat("-Z", "Y").to_euler()
scene.world.use_nodes = True
background = scene.world.node_tree.nodes.get("Background")
background.inputs["Color"].default_value = (1, 1, 1, 1)
background.inputs["Strength"].default_value = .6
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = 1400, 800
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(Path(output).resolve())
scene.view_settings.view_transform = "Standard"
bpy.ops.render.render(write_still=True)
