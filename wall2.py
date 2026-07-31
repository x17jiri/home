"""The first brick-wall elevation drawing."""

from house_drawing import Drawing


def main() -> None:
	drawing = Drawing(-4000, -10000, 4000, 2000)

	drawing.add_brick_wall(
		start_y = 0,
		polygon=[
			(-3500, 250),
			(-3500, -2750),
			(+3500, -2750),
			(+3500, 250),
		],
		#half_rows=[-8, -10]
	)

	drawing.add_brick_wall(
		start_y = 0,
		polygon=[
			(-3500, 250),
			(-3500, 0),
			(+3500, 0),
			(+3500, 250),
		],
		facecolor="#f0e0e0"
	)

	drawing.add_brick_wall(
		start_y=-2750-210-250,
		polygon=[
			(-3500, -2750-210),
			(-3500, -2750-210),
			(-3500, -2750-210-2500),
			(-3250, -2750-210-2500),
			(-1125, -2750-210-3250),
			(+1125, -2750-210-3250),
			(+3250, -2750-210-1500),
			(+3250, -2750-210-1250),
			(+3500, -2750-210-1250),
			(+3500, -2750-210),
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
		-3500+125-80, -2750-210-1250-120,
		-3250-125+80, -2750-210-1250,
		facecolor="yellow"
	)
	drawing.add_box(
		-3500+125-80, -2750-210-2500-120,
		-3250-125+80, -2750-210-2500,
		facecolor="yellow"
	)
	drawing.add_box(
		3500-125+80, -2750-210-1250-120,
		3250+125-80, -2750-210-1250,
		facecolor="yellow"
	)

	drawing.add_box(
		-800-70, -2750-210-3250-240,
		-800+70, -2750-210-3250,
		facecolor="yellow"
	)
	drawing.add_box(
		+800+70, -2750-210-3250-240,
		+800-70, -2750-210-3250,
		facecolor="yellow"
	)

	# dvere kuchyn
	drawing.add_polygon(
		[
			(125, 250),
			(125-1000, 250),
			(125-1000, 0),
			(125-2000, 0),
			(125-2000, -2125),
			(125, -2125)
		]
	)
	drawing.add_wall(125+125, -2125, 125-2000-125, -2125-125) # preklad
	drawing.add_box(125, -2000, 125+375, -2000-125, facecolor="#e8e8e8")
	drawing.add_box(125-2000, -2000, 125-2000-375, -2000-125, facecolor="#e8e8e8")
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
	drawing.add_wall(-3500, -2750, +3500, -2750-210, hatch="xx")

	# zaklad
	drawing.add_wall(-3500, 250, +3500, 400, hatch="xx")

	# otvor voda
	drawing.add_box(875-30, -2250, 875+30, -2250-250, facecolor="#b0d0ff")
	# otvor topeni
	drawing.add_box(-3250, -2250, -3250+50, -2250-250, facecolor="#b0d0ff")

	#drawing.add_ellipse(750-30, 50, 750+30, 110, facecolor="#b0d0ff")

	#drawing.add_line(-3250-125-80, -2750-210-2500-120, -875-70, -2750-210-3250-240)

	# komin
	drawing.add_box(-1040, 250, -1040-455, -8000,
		facecolor="none",
		edgecolor="#8080ff",
		linestyle="dashed",
		linewidth=2.0,
	)


	drawing.save("wall2.svg")
	drawing.save("wall2.png", dpi=200)
	drawing.close()


if __name__ == "__main__":
	main()
