"""Select positions on the existing situation map and save them as S-JTSK points."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from math import ceil, cos, floor, hypot, isfinite, sin
from pathlib import Path
import shutil
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
DEFAULT_MAP = ROOT / "projekt2/situace.svg"
DEFAULT_OUTPUT = ROOT / "selected_points.json"


@dataclass(frozen=True)
class MapCoordinates:
    east: float
    north: float
    angle: float
    bounds: tuple[float, float, float, float]
    rect: tuple[float, float, float, float]
    crs: str

    @classmethod
    def from_svg(cls, path):
        root = ET.parse(path).getroot()
        element = root.find('{http://www.w3.org/2000/svg}metadata[@id="situation-data"]')
        if element is None:
            raise ValueError("This SVG has no situation-map coordinate metadata")
        data = json.loads(element.text)
        frame = data["frame"]
        bounds, rect = tuple(data["map_bounds_local_m"]), tuple(data["map_rect_mm"])
        values = (frame["east"], frame["north"], frame["north_angle"], *bounds, *rect)
        if (len(bounds) != 4 or len(rect) != 4 or not all(isfinite(v) for v in values)
                or bounds[2] <= bounds[0] or bounds[3] <= bounds[1] or min(rect[2:]) <= 0):
            raise ValueError("Invalid map coordinate frame or bounds")
        return cls(frame["east"], frame["north"], frame["north_angle"], bounds, rect,
                   data["coordinate_system"])

    def to_survey(self, x, y):
        """Local east/north metres to positive survey Y (westing), X (southing)."""
        c, s = cos(self.angle), sin(self.angle)
        return -(self.east + c*x + s*y), -(self.north - s*x + c*y)

    def to_local(self, survey_y, survey_x):
        dx, dy = -survey_y-self.east, -survey_x-self.north
        c, s = cos(self.angle), sin(self.angle)
        return c*dx-s*dy, s*dx+c*dy

    def image_to_local(self, x, y, width, height):
        left, bottom, right, top = self.bounds
        return left+x/width*(right-left), top-y/height*(top-bottom)

    def local_to_image(self, x, y, width, height):
        left, bottom, right, top = self.bounds
        return (x-left)/(right-left)*width, (top-y)/(top-bottom)*height

    def contains(self, x, y):
        left, bottom, right, top = self.bounds
        return left <= x <= right and bottom <= y <= top


class PointSelection:
    """Coordinate edits and atomic persistence, independent of the GUI."""

    def __init__(self, coordinates, output, source):
        self.coordinates = coordinates
        self.output = Path(output).resolve()
        self.source = Path(source).resolve()
        self.points = []
        self.selected = None
        self.history = []
        if self.output.exists():
            data = json.loads(self.output.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or data.get("crs") != coordinates.crs:
                raise ValueError(f"{self.output}: unsupported selection format or coordinate system")
            points = data.get("points")
            if not isinstance(points, list):
                raise ValueError(f"{self.output}: points must be a list")
            ids = set()
            for p in points:
                if (not isinstance(p, dict) or type(p.get("id")) is not int or p["id"] <= 0
                        or p["id"] in ids or any(type(p.get(k)) not in (int, float)
                                                or not isfinite(p[k]) for k in ("Y", "X"))
                        or (p.get("Z") is not None and
                            (type(p["Z"]) not in (int, float) or not isfinite(p["Z"])))):
                    raise ValueError(f"{self.output}: invalid point record")
                ids.add(p["id"])
                self.points.append({"id": p["id"], "Y": p["Y"], "X": p["X"], "Z": p.get("Z")})
            self.selected = self.points[-1]["id"] if self.points else None

    def local(self, point):
        return self.coordinates.to_local(point["Y"], point["X"])

    def selected_point(self):
        return next((p for p in self.points if p["id"] == self.selected), None)

    def _commit(self, action):
        self.save()
        p = self.selected_point()
        if p is not None:
            x, y = self.local(p)
            print(f'{action}: point {p["id"]}  Y={p["Y"]:.3f}  X={p["X"]:.3f}'
                  f'  x={x:.3f}  y={y:.3f}  Z={p["Z"]}', flush=True)
        else:
            print(f"{action}: {len(self.points)} points", flush=True)

    def _edit(self, action, change):
        before = ([p.copy() for p in self.points], self.selected)
        try:
            change()
            self._commit(action)
        except Exception:
            self.points, self.selected = before
            raise
        self.history.append(before)

    def add(self, x, y):
        if not self.coordinates.contains(x, y):
            return False
        survey_y, survey_x = self.coordinates.to_survey(x, y)
        point_id = max((p["id"] for p in self.points), default=0)+1

        def change():
            self.points.append({"id": point_id, "Y": survey_y, "X": survey_x, "Z": None})
            self.selected = point_id

        self._edit("Added", change)
        return True

    def move(self, dx, dy):
        p = self.selected_point()
        if p is None:
            return False
        x, y = self.local(p)
        if not self.coordinates.contains(x+dx, y+dy):
            return False

        def change():
            p["Y"], p["X"] = self.coordinates.to_survey(x+dx, y+dy)

        self._edit("Moved", change)
        return True

    def delete(self):
        if self.selected_point() is None:
            return False

        def change():
            self.points = [p for p in self.points if p["id"] != self.selected]
            self.selected = self.points[-1]["id"] if self.points else None

        self._edit("Deleted", change)
        return True

    def undo(self):
        if not self.history:
            return False
        current = (self.points, self.selected)
        previous = self.history[-1]
        self.points, self.selected = [p.copy() for p in previous[0]], previous[1]
        try:
            self._commit("Undid edit")
        except Exception:
            self.points, self.selected = current
            raise
        self.history.pop()
        return True

    def save(self):
        points = []
        for p in self.points:
            x, y = self.local(p)
            points.append({"id": p["id"], "x": round(x, 3), "y": round(y, 3),
                           "Y": round(p["Y"], 3), "X": round(p["X"], 3), "Z": p["Z"]})
        data = {"version": 1, "crs": self.coordinates.crs, "coordinate_system": "S-JTSK",
                "units": "metres", "source_svg": str(self.source),
                "frame": {"east": self.coordinates.east, "north": self.coordinates.north,
                          "north_angle": self.coordinates.angle},
                "map_bounds_local_m": self.coordinates.bounds, "points": points}
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tmp",
                                    prefix=f".{self.output.name}-", dir=self.output.parent,
                                    delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            temporary.replace(self.output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def rasterize_map(source, coordinates, *, width=3600):
    """Rasterize only the existing map viewport; never regenerate the drawing."""
    from PIL import Image

    inkscape = shutil.which("inkscape")
    if inkscape is None:
        raise FileNotFoundError("Inkscape is required to open the SVG map")
    root = ET.parse(source).getroot()
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    x, y, w, h = coordinates.rect
    root.set("viewBox", f"{x:g} {y:g} {w:g} {h:g}")
    root.set("width", f"{w:g}mm")
    root.set("height", f"{h:g}mm")
    with TemporaryDirectory(prefix="house-map-picker-") as directory:
        svg, png = Path(directory)/"map.svg", Path(directory)/"map.png"
        ET.ElementTree(root).write(svg, encoding="utf-8", xml_declaration=True)
        result = subprocess.run([inkscape, str(svg), f"--export-filename={png}",
                                 "--export-type=png", "--export-area-page",
                                 f"--export-width={width}", "--batch-process"],
                                capture_output=True, text=True)
        if result.returncode or not png.is_file():
            raise RuntimeError(f"Could not render the map: {result.stderr.strip()}")
        with Image.open(png) as image:
            return image.convert("RGB")


class MapPicker:
    def __init__(self, root, image, selection):
        import tkinter as tk
        from tkinter import ttk

        self.root, self.image, self.selection = root, image, selection
        self.photo = None
        self.zoom = 1
        self.pan = (0., 0.)
        self.pan_start = None
        self.view_changed = False
        self.pending_draw = None
        root.title("Map point picker")
        root.geometry(f"{min(1280, root.winfo_screenwidth()-80)}x{min(950, root.winfo_screenheight()-100)}")
        toolbar = ttk.Frame(root, padding=6)
        toolbar.pack(fill="x")
        for label, command in (("Undo", selection.undo), ("Delete point", selection.delete)):
            ttk.Button(toolbar, text=label, command=lambda c=command: self.edit(c)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Fit map", command=self.fit).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Done", command=self.close).pack(side="right", padx=3)
        ttk.Label(root, text="Click to add/select • Arrows: 10 cm • Shift+arrows: 1 m • Ctrl+arrows: 1 cm",
                  padding=(10, 2)).pack(anchor="w")
        ttk.Label(root, text="Wheel: zoom • Right/middle drag: pan • Tab: next point • Delete: remove • Ctrl+Z: undo",
                  padding=(10, 2)).pack(anchor="w")
        self.canvas = tk.Canvas(root, bg="#d9d9d9", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.background = self.canvas.create_image(0, 0, anchor="nw")
        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, padding=(10, 4)).pack(fill="x")
        ttk.Label(root, text=f"Autosave: {selection.output}", padding=(10, 2)).pack(anchor="w")
        self.canvas.bind("<Configure>", self.resize)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<MouseWheel>", lambda e: self.wheel(e, 1.2 if e.delta > 0 else 1/1.2))
        self.canvas.bind("<Button-4>", lambda e: self.wheel(e, 1.2))
        self.canvas.bind("<Button-5>", lambda e: self.wheel(e, 1/1.2))
        for button in (2, 3):
            self.canvas.bind(f"<ButtonPress-{button}>", self.start_pan)
            self.canvas.bind(f"<B{button}-Motion>", self.drag_pan)
        for key in ("Left", "Right", "Up", "Down"):
            root.bind(f"<{key}>", self.nudge)
        for key in ("<Delete>", "<BackSpace>"):
            root.bind(key, lambda e: self.edit(selection.delete))
        root.bind("<Control-z>", lambda e: self.edit(selection.undo))
        root.bind("<Tab>", self.next_point)
        root.bind("<Escape>", lambda e: self.close())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.update_status()
        self.canvas.focus_set()

    def update_status(self):
        p = self.selection.selected_point()
        text = f"{len(self.selection.points)} points"
        if p is not None:
            text += f' • Selected {p["id"]}: Y {p["Y"]:.3f}, X {p["X"]:.3f}'
        self.status.set(text)

    def edit(self, command):
        from tkinter import messagebox

        try:
            command()
            self.update_status()
            self.draw_markers()
        except (OSError, ValueError) as error:
            messagebox.showerror("Points were not saved", str(error), parent=self.root)
        return "break"

    def fit(self):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.zoom = min(width/self.image.width, height/self.image.height)*.97
        self.pan = ((width-self.image.width*self.zoom)/2, (height-self.image.height*self.zoom)/2)
        self.view_changed = False
        self.schedule_draw()

    def resize(self, event):
        if not self.view_changed:
            self.fit()
        else:
            self.schedule_draw()

    def schedule_draw(self):
        if self.pending_draw is not None:
            self.root.after_cancel(self.pending_draw)
        self.pending_draw = self.root.after(20, self.draw)

    def screen_point(self, p):
        x, y = self.selection.coordinates.local_to_image(*self.selection.local(p), self.image.width, self.image.height)
        return self.pan[0]+x*self.zoom, self.pan[1]+y*self.zoom

    def draw(self):
        from PIL import Image, ImageTk

        self.pending_draw = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        left, top = max(0, floor(-self.pan[0]/self.zoom)), max(0, floor(-self.pan[1]/self.zoom))
        right = min(self.image.width, ceil((w-self.pan[0])/self.zoom))
        bottom = min(self.image.height, ceil((h-self.pan[1])/self.zoom))
        if right > left and bottom > top:
            crop = self.image.crop((left, top, right, bottom))
            size = (max(1, round(crop.width*self.zoom)), max(1, round(crop.height*self.zoom)))
            self.photo = ImageTk.PhotoImage(crop.resize(size, Image.Resampling.LANCZOS), master=self.root)
            self.canvas.itemconfigure(self.background, image=self.photo, state="normal")
            self.canvas.coords(self.background, self.pan[0]+left*self.zoom, self.pan[1]+top*self.zoom)
        else:
            self.canvas.itemconfigure(self.background, state="hidden")
        self.draw_markers()

    def draw_markers(self):
        self.canvas.delete("point-marker")
        for p in self.selection.points:
            x, y = self.screen_point(p)
            color = "#7b169d" if p["id"] == self.selection.selected else "#d7191c"
            for stroke, width in (("white", 5), (color, 2.5)):
                for sign in (-1, 1):
                    self.canvas.create_line(x-6, y-sign*6, x+6, y+sign*6, fill=stroke,
                                            width=width, tags="point-marker")
            self.canvas.create_text(x+10, y-10, text=str(p["id"]), fill=color, anchor="sw",
                                    font=("TkDefaultFont", 11, "bold"), tags="point-marker")

    def click(self, event):
        self.canvas.focus_set()
        candidates = [(hypot(event.x-x, event.y-y), p["id"])
                      for p in self.selection.points for x, y in (self.screen_point(p),)]
        if candidates and min(candidates)[0] <= 12:
            self.selection.selected = min(candidates)[1]
            self.update_status()
            self.draw_markers()
        else:
            local = self.selection.coordinates.image_to_local((event.x-self.pan[0])/self.zoom,
                                                               (event.y-self.pan[1])/self.zoom,
                                                               self.image.width, self.image.height)
            self.edit(lambda: self.selection.add(*local))

    def nudge(self, event):
        step = .01 if event.state & 0x4 else (1.0 if event.state & 0x1 else .1)
        dx, dy = {"Left": (-step, 0), "Right": (step, 0), "Up": (0, step), "Down": (0, -step)}[event.keysym]
        return self.edit(lambda: self.selection.move(dx, dy))

    def next_point(self, event):
        ids = [p["id"] for p in self.selection.points]
        if ids:
            current = ids.index(self.selection.selected) if self.selection.selected in ids else -1
            self.selection.selected = ids[(current+1) % len(ids)]
            self.update_status()
            self.draw_markers()
        return "break"

    def wheel(self, event, factor):
        fit = min(self.canvas.winfo_width()/self.image.width, self.canvas.winfo_height()/self.image.height)
        zoom = min(fit*30, max(fit*.5, self.zoom*factor))
        image_x, image_y = (event.x-self.pan[0])/self.zoom, (event.y-self.pan[1])/self.zoom
        self.pan = (event.x-image_x*zoom, event.y-image_y*zoom)
        self.zoom, self.view_changed = zoom, True
        self.schedule_draw()
        return "break"

    def start_pan(self, event):
        self.pan_start = (event.x, event.y, *self.pan)

    def drag_pan(self, event):
        if self.pan_start is not None:
            x, y, px, py = self.pan_start
            self.pan = (px+event.x-x, py+event.y-y)
            self.view_changed = True
            self.schedule_draw()

    def close(self):
        # Every successful edit is already on disk; closing cannot lose points.
        if self.pending_draw is not None:
            self.root.after_cancel(self.pending_draw)
        self.root.destroy()


def main():
    import tkinter as tk

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP, help="Existing situation SVG")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Selection JSON (loaded if present)")
    args = parser.parse_args()
    try:
        coordinates = MapCoordinates.from_svg(args.map)
        selection = PointSelection(coordinates, args.output, args.map)
        root = tk.Tk()
        root.withdraw()
        print("Opening existing map…", flush=True)
        image = rasterize_map(args.map, coordinates)
        MapPicker(root, image, selection)
        print(f"Autosaving to {selection.output}", flush=True)
        root.deiconify()
        root.mainloop()
    except (OSError, ValueError, KeyError, ET.ParseError, tk.TclError) as error:
        parser.exit(1, f"Map picker: {error}\n")


if __name__ == "__main__":
    main()
