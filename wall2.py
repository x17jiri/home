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
	drawing.add_box(-750, 250, +250, -2250)
	drawing.add_wall(-1000, -2250, +500, -2250-250) # preklad

	# dvere horni pokoj
	drawing.add_box(-125, -2750-210, +875, -2750-210-1000-1250)
	drawing.add_wall(-375, -2750-210-1000-1250, +1125, -2750-210-1000-1250-250) # preklad

	# horni instalacni sachta
	drawing.add_box(-500-125, -2750-210-3250, +500+125, -2750-210-3000)
	drawing.add_box(-500, -2750-210-3000, +500, -2750-210-2750)
	drawing.add_line(-500-125, -2750-210-3250, +500+125, -2750-210-3250, color="white", linewidth=2)
	drawing.add_line(-500, -2750-210-3000, +500, -2750-210-3000, color="white", linewidth=2)

	# strop
	drawing.add_wall(-3500, -2750, +3500, -2750-210, hatch="xx")

	# zaklad
	drawing.add_wall(-3500, 250, +3500, 400, hatch="xx")

	drawing.add_box(875-30, -2250, 875+30, -2250-250, facecolor="#b0d0ff")
	drawing.add_box(-1250-250, -2250, -1250+250, -2250+250, facecolor="#e8e8e8")
	drawing.add_ellipse(-1250-125, -2250+500, -1250+125, -2250+250, facecolor="#b0d0ff")
	drawing.add_box(-1250-250, -500, -1250+250, -750, facecolor="#e8e8e8")
	drawing.add_ellipse(-1250-125, -500, -1250+125, -250, facecolor="#b0d0ff")

	#drawing.add_ellipse(750-30, 50, 750+30, 110, facecolor="#b0d0ff")

	#drawing.add_line(-3250-125-80, -2750-210-2500-120, -875-70, -2750-210-3250-240)

	drawing.save("wall2.svg")
	drawing.save("wall2.png", dpi=200)
	drawing.close()


if __name__ == "__main__":
	main()
