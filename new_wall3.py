"""The first brick-wall elevation drawing."""

from house_drawing import Drawing

HOUSE_W = 8000
AIR_HATCH_H = 2875
PRIZEMI_Y = -2750
STROP_Y = PRIZEMI_Y-250
VIKYR_Y = STROP_Y-2500
HREBEN_Y = STROP_Y-2875-500

def main() -> None:
	drawing = Drawing(-HOUSE_W/2-1000, -10000, HOUSE_W/2+1000, 2000)

	drawing.add_brick_wall(
		start_y = 0,
		polygon=[
			(-HOUSE_W/2, 250),
			(-HOUSE_W/2, PRIZEMI_Y),
			(+HOUSE_W/2, PRIZEMI_Y),
			(+HOUSE_W/2, 250),
		],
		#half_rows=[-8, -10]
	)

	drawing.add_brick_wall(
		start_y = 0,
		polygon=[
			(-HOUSE_W/2, 250),
			(-HOUSE_W/2, 0),
			(+HOUSE_W/2, 0),
			(+HOUSE_W/2, 250),
		],
		facecolor="#f0e0e0"
	)

	drawing.add_brick_wall(
		start_y=STROP_Y-250,
		polygon=[
			(-HOUSE_W/2, STROP_Y),
			(-HOUSE_W/2, STROP_Y),
			(-HOUSE_W/2, VIKYR_Y),
			(-HOUSE_W/2+250, VIKYR_Y),
			(-1125, HREBEN_Y),
			(+1125, HREBEN_Y),
			(+HOUSE_W/2-250, STROP_Y-1500),
			(+HOUSE_W/2-250, STROP_Y-1250),
			(+HOUSE_W/2, STROP_Y-1250),
			(+HOUSE_W/2, STROP_Y),
		],
#		half_rows=[10],
	)
	drawing.add_box(-1125, -2750-210-3250, -1125+500, -2750-210-3000, facecolor="#e8e8e8")
	drawing.add_box(+1125, -2750-210-3250, +1125-500, -2750-210-3000, facecolor="#e8e8e8")

	# venec
	drawing.add_wall(
		-3500, -2750-210-1250,
		3500, -2750-210-1000,
		hatch="oo"
	)
	drawing.add_wall(
		-3500, -2750-210-2500,
		-500, -2750-210-2500+250,
		hatch="oo"
	)
	drawing.add_box(
		-HOUSE_W/2+125-80, -2750-210-1250-120,
		-HOUSE_W/2+250-125+80, -2750-210-1250,
		facecolor="yellow"
	)
	drawing.add_box(
		-HOUSE_W/2+125-80, -2750-210-2500-120,
		-HOUSE_W/2+250-125+80, -2750-210-2500,
		facecolor="yellow"
	)
	drawing.add_box(
		HOUSE_W/2-125+80, -2750-210-1250-120,
		HOUSE_W/2-250+125-80, -2750-210-1250,
		facecolor="yellow"
	)

	drawing.add_box(
		-800-70, HREBEN_Y-240,
		-800+70, HREBEN_Y,
		facecolor="yellow"
	)
	drawing.add_box(
		+800+70, HREBEN_Y-240,
		+800-70, HREBEN_Y,
		facecolor="yellow"
	)

	# dvere kuchyn
	drawing.add_box(
		125, 250,
		125-1000, -2125,
	)
	drawing.add_box(
		750, 0,
		1750, -2125,
	)
	drawing.add_wall(125-1000-125, -2125, 1750+125, -2125-125) # preklad
	drawing.add_box(125, -2125, 125+375, -2000, facecolor="#e8e8e8")
	drawing.add_box(
		125-50, 70,
		125-950, -2100+70,
		facecolor="none",
		edgecolor="#8080ff",
		linestyle="dashed",
		linewidth=2.0,
	)

	# dvere horni pokoj
	drawing.add_box(-125, -2750-210, +875, -2750-210-2250)
	drawing.add_wall(-125-125, -2750-210-2250, +875+125, -2750-210-2250-125) # preklad

	# horni instalacni sachta
	drawing.add_wall(-500-125, -2750-210-3125, +500+125, -2750-210-3000)
	drawing.add_box(-500, -2750-210-3000, +500, -2750-210-2750, facecolor="#b0d0ff")

	# strop
	drawing.add_wall(-3500, PRIZEMI_Y, +3500, STROP_Y, hatch="xx")

	# zaklad
	drawing.add_wall(-3500, 250, +3500, 400, hatch="xx")

	# otvor voda
	drawing.add_box(875-30, -2250, 875+30, -2250-250, facecolor="#b0d0ff")
	# otvor topeni
	drawing.add_box(-3250, -2250, -3250+50, -2250-250, facecolor="#b0d0ff")

	#drawing.add_ellipse(750-30, 50, 750+30, 110, facecolor="#b0d0ff")

	#drawing.add_line(-3250-125-80, -2750-210-2500-120, -875-70, -2750-210-3250-240)

	# komin
	drawing.add_box(215, 250, 215+455, -8000,
		facecolor="none",
		edgecolor="#8080ff",
		linestyle="dashed",
		linewidth=2.0,
	)

	SCHOD = (-STROP_Y + 70 + 100)/18
	# schody - wall4
	drawing.add_box(-HOUSE_W/2+750, 70-13*SCHOD+100, -HOUSE_W/2+1750, 70-13*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+1*270, 70-13*SCHOD, -HOUSE_W/2+1750+0*270, 70-14*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+2*270, 70-14*SCHOD, -HOUSE_W/2+1750+1*270, 70-15*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+3*270, 70-15*SCHOD, -HOUSE_W/2+1750+2*270, 70-16*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+4*270, 70-16*SCHOD, -HOUSE_W/2+1750+3*270, 70-17*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+5*270, 70-17*SCHOD, -HOUSE_W/2+1750+4*270, 70-18*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)

	# schody - wall3
	drawing.add_box(-HOUSE_W/2+750, 70-0*SCHOD, -HOUSE_W/2+1750, 70-7*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+1*270, 70-6*SCHOD, -HOUSE_W/2+1750, 70-5*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+2*270, 70-5*SCHOD, -HOUSE_W/2+1750, 70-4*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+3*270, 70-4*SCHOD, -HOUSE_W/2+1750, 70-3*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+4*270, 70-3*SCHOD, -HOUSE_W/2+1750, 70-2*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+5*270, 70-2*SCHOD, -HOUSE_W/2+1750, 70-1*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)
	drawing.add_box(-HOUSE_W/2+1750+6*270, 70-1*SCHOD, -HOUSE_W/2+1750, 70-0*SCHOD, facecolor="none", edgecolor="#8080ff", linestyle="dashed", linewidth=2.0)

#	drawing.save("new_wall3.svg")
	drawing.save("new_wall3.png", dpi=200)
	drawing.close()


if __name__ == "__main__":
	main()
