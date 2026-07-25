from heat2d_boxes import *

model = HeatModel2D(
    width=5.0,
    height=5.0,
    nx=500,
    ny=1000,
    default_lambda=1.5,
    default_name="zemina",
)

# https://www.gealan.de/cz/najit-vyrobce-oken
# https://selektorskel.izos.cz/category/5/169
# purenit box pro zaluzie: https://www.isotra.cz/d-doc/2/2799/639111528600966667/sesit_Purenitovy_box_CZ_14_5_2025.pdf
# rucni vyroba purenit boxu: https://share.google/aimode/PeHiIFE6oA900kHKh
# zapustne pouzdro pro zaluzii: https://www.podomitku.cz/izolacni-panely-a-pouzdra-pro-vodici-listy

# https://www.wienerberger.cz/content/dam/wienerberger/czech-republic/marketing/documents-magazines/technical/technical-product-info-sheet/wall/CZ_POR_TEC_Pth_25_AKU_SYM.pdf

# https://www.izolace-info.cz/katalog/polyisokyanurat/puren-gmbh/izolacni-panel-z-pir-peny-puren-fal-p.html

# Misto ISO Kimmstein:
# - ytong static plus
# - liapor M 240

model.add_box(0.0, 2.0, 4.0, 2.3, 0.085, "pěnosklo")
model.add_box(0.0, 2.3, 4.0, 2.5, 2.1, "betonová deska")
model.add_box(0.0, 2.5, 4.0, 2.55, 0.035, "vata")
model.add_box(3.95, 2.55, 4.0, 2.6, 0.33, "vata2")
model.add_box(4.0, 2.5, 4.25, 2.6, 0.33, "iso")
model.add_box(4.0, 0.2, 4.25, 2.5, 2.1, "základový pas")
model.add_box(4.25, 0.2, 4.5, 5, 0.045, "perimetr")

model.set_boundary_temperature("top", 20.0)
model.set_boundary_temperature("right", -15.0)
model.set_boundary_temperature("bottom", 5.0)

model.solve()
model.plot_temperature()

print(model.boundary_heat_flow("top"), "W/m")
