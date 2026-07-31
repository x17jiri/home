"""The first brick-wall elevation drawing."""

from house_drawing import Drawing


def main() -> None:
	drawing = Drawing(-15000, -10000, 3000, 2000)

	# spodek
	drawing.add_brick_wall(
		start_y=250,
		polygon=[
			(-12750, 250),
			(-12750, -2750),
			(+250, -2750),
			(+250, 250),
		],
	)

	# ytong
	drawing.add_brick_wall(
		start_y=250,
		polygon=[
			(-12750, 250),
			(-12750, 0),
			(+250, 0),
			(+250, 250),
		],
		facecolor="#f0e0e0"
	)

	# vrsek 1
	drawing.add_brick_wall(
		polygon=[
			(-12750, -2750-210),
			(-12750, -2750-210-1250),
			(+250, -2750-210-1250),
			(+250, -2750-210),
		],
		half_rows=[7],
	)

	# vrsek 2
	drawing.add_brick_wall(
		start_y=-2750-210-250,
		polygon=[
			(-12750+250+4125, -2750-210-1250),
			(-12750+250+4125, -2750-210-2625),
			(-12750+250+4125+250+4125+250, -2750-210-2625),
			(-12750+250+4125+250+4125+250, -2750-210-1250),
		],
		half_rows=[7],
	)

	# okno left, nahore
	drawing.add_box(
		-12750+250+4125+500, -2750-210-2625+250,
		-12750+250+4125+2000, -2750-210-1250,
	)

	# okno right, nahore
	drawing.add_box(
		-12750+250+4125+500+4125-500, -2750-210-2625+250,
		-12750+250+4125+500+4125-2000, -2750-210-1250,
	)

	# okno left, dole
	drawing.add_box(
		-12750+250+4125+500, -875,
		-12750+250+4125+2000, -2250,
	)
	# pruvlak
	drawing.add_wall(
		-12750+250+4125+500-250, -2250-125,
		-12750+250+4125+2000+250, -2250,
	)

	# okno right, dole
	drawing.add_box(
		-12750+250+4125+500+4125-500, 0,
		-12750+250+4125+500+4125-2000, -2125,
	)
	# pruvlak
	drawing.add_wall(
		-12750+250+4125+500+4125-500+250, -2125-125,
		-12750+250+4125+500+4125-2000-250, -2125,
	)
	# topeni
	drawing.add_box(
		-12750+250+4125+500+4125-1250-450, -2125,
		-12750+250+4125+500+4125-1250+450, -2125-350,
		facecolor="none",
		edgecolor="#8080ff",
		linestyle="dashed",
		linewidth=2.0,
	)

	# okno risanek
	drawing.add_box(
		-12750+250+4125-500, -875,
		-12750+250+4125-2500, -2250,
	)
	# pruvlak
	drawing.add_wall(
		-12750+250+4125-500+250, -2250,
		-12750+250+4125-2500-250, -2250-125,
	)

	# vence
	drawing.add_wall(
		-12750+250+4125, -2750-210-2625,
		-12750+250+4125+500+4125, -2750-210-2625+250,
		hatch="oo"
	)
	drawing.add_wall(
		-12750, -2750-210-1250,
		250, -2750-210-1000,
		hatch="oo"
	)
	drawing.add_box(
		-12750+250+4125, -2750-210-2625,
		-12750+250+4125+500+4125, -2750-210-2625-120,
		facecolor="yellow"
	)
	drawing.add_box(
		-12750+250+4125, -2750-210-1250,
		-12750, -2750-210-1250-120,
		facecolor="yellow"
	)
	drawing.add_box(
		-12750+250+4125+500+4125, -2750-210-1250,
		250, -2750-210-1250-120,
		facecolor="yellow"
	)
	# strop
	drawing.add_wall(-12750, -2750, +250, -2750-210, hatch="xx")

	# zaklad
	drawing.add_wall(-12750, 250, +250, 400, hatch="xx")

	# otvor na vzduch pro krb
	drawing.add_box(-12750+750+4125*2+125, -750, -12750+750+4125*2+625, -500, facecolor="#e8e8e8")
	drawing.add_ellipse(-12750+750+4125*2+250, -250, -12750+750+4125*2+500, -500, facecolor="#b0d0ff")

	# otvor privod rekuperace
	# TODO - je pres pul cihly
	drawing.add_box(-12750+750+4125*2+125, -2750-210-750, -12750+750+4125*2+625, -2750-210-500, facecolor="#e8e8e8")
	drawing.add_ellipse(-12750+750+4125*2+250, -2750-210-250, -12750+750+4125*2+500, -2750-210-500, facecolor="#b0d0ff")

	drawing.save("wall_left.svg")
	drawing.save("wall_left.png", dpi=200)


if __name__ == "__main__":
	main()
