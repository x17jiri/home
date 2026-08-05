from ifc_utils import *

house = House("My house")

ground = house.storey("Ground floor", elevation=0)

exterior_wall = house.wall_type(
    "Brick and rock wool",
    layers=[
        ("Brick", 0.25),
        "axis",
        ("Rockwool", 0.20),
    ],
)

wall_front = ground.wall((0, 0), (12, 0), wall_type=exterior_wall, height=2.75)
wall_4 = ground.wall((12, 0), (12, 8), wall_type=exterior_wall, height=2.75)
wall_back = ground.wall((12, 8), (0, 8), wall_type=exterior_wall, height=2.75)
wall_1 = ground.wall((0, 8), (0, 0), wall_type=exterior_wall, height=2.75)
ground.connect_wall(wall_front, wall_4)
ground.connect_wall(wall_4, wall_back)
ground.connect_wall(wall_back, wall_1)
ground.connect_wall(wall_1, wall_front)

# The Rockwool occupies the right side of each wall axis.  These centre lines
# meet at the outside corner and are persisted as IFC batting annotations.
ground.batting((4.10, 0), (4.10, 5.10), thickness=0.20)
ground.batting((4.10, 5.10), (-11, 5.10), thickness=0.20)

house.write("house.ifc")

generate_plan("house.ifc", "house.svg", x=6, y=4, z=1.5, radius=8, png=True)
