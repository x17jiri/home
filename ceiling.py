from house_drawing import *


drawing = Drawing(-1000, -1000, 8000, 14000)

drawing.add_wall(-250, -250, 6750, 12750)
drawing.add_box(0, 0, 6500, 3750)
drawing.add_box(0, 4000, 6500, 8125)
drawing.add_box(0, 8375, 6500, 12500)

drawing.add_ceiling(-40, -125-70, 4000+140, [
	Wide(visible=False),
	Beam(visible=False),
	Narrow(visible=False),
	Beam(visible=False),
	Narrow(visible=False),
	Beam(visible=False),
	Narrow(visible=False),
	Beam(visible=False),
	Narrow(visible=False),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
])

drawing.add_ceiling(-40, 3750+125-70, 4375+140, [
	Narrow(),
	Beam(),
	Narrow(),
	Beam(),
	Narrow(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
])

drawing.add_ceiling(-40, 8125+125-70, 4375+140, [
	Narrow(),
	Beam(),
	Narrow(),
	Beam(),
	Narrow(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Wide(),
	Beam(),
	Narrow(),
])

# komin
drawing.add_box(4562.5-250, 3750-750, 4562.5+250, 3750-250, hatch="xx", facecolor="#c080c0")
# odpad
drawing.add_box(4500+250+125, 3750-250, 4500+250+125+500, 3750, hatch="xx", facecolor="#c080c0")

# schody
drawing.add_box(0, 0, 1000, 3750, facecolor="#d0d0d0")
drawing.add_box(0, 0, 2350, 1000, facecolor="#d0d0d0")
drawing.add_box(0, 3750-1000, 1830, 3750, facecolor="#d0d0d0")

# sachta kuchyn
drawing.add_box(0, 3750+250, 450, 3750+250+150, hatch="xx", facecolor="#c080c0")

# pricka dole
drawing.add_box(6500/2-125, 3750+4125+250+250, 6500/2+125, 12750, facecolor="none", linestyle="dotted", hatch="xx")

# sachta loznice
drawing.add_box(3040-150, 3750+4125+250+250, 3040, 3750+4125+250+250+150, hatch="xx", facecolor="#c080c0")

# sachta risanek
drawing.add_box(3665-150, 3750+4125+250+250, 3665, 3750+4125+250+250+150, hatch="xx", facecolor="#c080c0")

# NOTE:
# G21a.1.4.250 Uložení stropních trámů POT na vnitřní stěnu v příčném směru, uložení menší než 125 mm, tl. stropu 250 mm

# A second wall and a dimension showing their 300 cm span.
#drawing.add_wall(30, 10, 330, 30)
#drawing.add_dimension(30, 30, 330, 30, offset=50)

# Styles can be overridden per wall.
#drawing.add_wall(330, 10, 350, 200, facecolor="#dbeafe", hatch="xx")

drawing.save("ceiling.svg")
drawing.save("ceiling.png", dpi=200)
