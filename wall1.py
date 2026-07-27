"""The first brick-wall elevation drawing."""

from house_drawing import Drawing


def main() -> None:
	drawing = Drawing(-4000, -10000, 4000, 2000)

	drawing.add_brick_wall(
		start_y=0,
		polygon=[
			(-3500, 250),
			(-3500, -2750),
			(+3500, -2750),
			(+3500, 250),
		],
		#half_rows=[-8, -10]
	)

	drawing.add_brick_wall(
		start_y=0,
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
			(-3500, -2750-210-1250),
			(+3500, -2750-210-1250),
			(+3500, -2750-210),
		],
	)
	drawing.add_brick_wall(
		start_y=-2750-210,
		polygon=[
			(-3250, -2750-210-1250),
			(-3250, -2750-210-1500),
			(-1125, -2750-210-3250),
			(+1125, -2750-210-3250),
			(+3250, -2750-210-1500),
			(+3250, -2750-210-1250),
		],
	)
	drawing.add_box(-1125, -2750-210-3250, -1125+500, -2750-210-3000, facecolor="#e8e8e8")
	drawing.add_box(+1125, -2750-210-3250, +1125-500, -2750-210-3000, facecolor="#e8e8e8")

	# venec
	drawing.add_wall(
		-3500, -2750-210-1250,
		3500, -2750-210-1000,
		hatch="oo"
	)
	drawing.add_box(
		-3500+125-80, -2750-210-1250-120,
		-3250-125+80, -2750-210-1250,
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

	# dvere
	drawing.add_box(-750, 0, +750, -2250)
	drawing.add_wall(-1000, -2250, +1000, -2250-250) # preklad

	# okno
	drawing.add_box(-750, -2750-210-1000, +750, -2750-210-1000-1250)
	drawing.add_wall(-1000, -2750-210-1000-1250, +1000, -2750-210-1000-1250-250) # preklad

	# strop
	drawing.add_wall(-3500, -2750, +3500, -2750-210, hatch="xx")

	# zaklad
	drawing.add_wall(-3500, 250, +3500, 400, hatch="xx")

	drawing.save("wall1.svg")
	drawing.save("wall1.png", dpi=200)
	drawing.close()


if __name__ == "__main__":
	main()
