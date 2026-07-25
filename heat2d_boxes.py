"""
Jednoduchý 2D simulátor stacionárního vedení tepla.

- Geometrie se skládá z obdélníků přidaných pomocí add_box(...)
- Každá buňka má tepelnou vodivost lambda [W/(m.K)]
- Okraje mohou mít pevnou teplotu; nezadané okraje jsou adiabatické
- Řeší se rovnice div(lambda * grad(T)) = 0 metodou konečných objemů

Závislosti:
    pip install numpy scipy matplotlib
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve


Side = Literal["left", "right", "bottom", "top"]


@dataclass(frozen=True)
class Material:
    name: str
    conductivity: float  # lambda [W/(m.K)]


class HeatModel2D:
    def __init__(
        self,
        width: float,
        height: float,
        nx: int,
        ny: int,
        default_lambda: float,
        default_name: str = "zemina",
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Rozměry modelu musí být kladné.")
        if nx < 2 or ny < 2:
            raise ValueError("Mřížka musí mít alespoň 2 × 2 buňky.")
        if default_lambda <= 0:
            raise ValueError("Tepelná vodivost musí být kladná.")

        self.width = float(width)
        self.height = float(height)
        self.nx = int(nx)
        self.ny = int(ny)
        self.dx = self.width / self.nx
        self.dy = self.height / self.ny

        self.x = (np.arange(self.nx) + 0.5) * self.dx
        self.y = (np.arange(self.ny) + 0.5) * self.dy

        self.materials: list[Material] = [
            Material(default_name, float(default_lambda))
        ]
        self.material_index = np.zeros((self.ny, self.nx), dtype=np.int32)
        self.lambda_field = np.full(
            (self.ny, self.nx), float(default_lambda), dtype=float
        )

        # Nezadaný okraj = adiabatický (nulový tok).
        self.boundary_temperatures: dict[Side, float] = {}
        self.temperature: np.ndarray | None = None

    def add_box(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        conductivity: float,
        name: str | None = None,
    ) -> None:
        """
        Přidá obdélníkový materiál.

        Souřadnice:
            x roste zleva doprava
            y roste zdola nahoru

        Buňka patří do obdélníku, pokud v něm leží její střed.
        Později přidaný obdélník přepíše dřívější materiál.
        """
        if conductivity <= 0:
            raise ValueError("Tepelná vodivost musí být kladná.")

        xa, xb = sorted((float(x1), float(x2)))
        ya, yb = sorted((float(y1), float(y2)))

        if xa == xb or ya == yb:
            raise ValueError("Obdélník musí mít nenulovou plochu.")

        mask_x = (self.x >= xa) & (self.x < xb)
        mask_y = (self.y >= ya) & (self.y < yb)
        mask = np.outer(mask_y, mask_x)

        if not np.any(mask):
            raise ValueError(
                "Obdélník nezasáhl žádnou buňku. "
                "Zvětšete jej nebo zjemněte mřížku."
            )

        material_name = name or f"lambda={conductivity:g}"
        material_id = len(self.materials)
        self.materials.append(Material(material_name, float(conductivity)))

        self.material_index[mask] = material_id
        self.lambda_field[mask] = conductivity
        self.temperature = None

    def set_boundary_temperature(self, side: Side, temperature: float) -> None:
        """Nastaví pevnou teplotu na celém zvoleném okraji."""
        if side not in {"left", "right", "bottom", "top"}:
            raise ValueError(f"Neznámý okraj: {side}")
        self.boundary_temperatures[side] = float(temperature)
        self.temperature = None

    @staticmethod
    def _harmonic_mean(a: float, b: float) -> float:
        """Vodivost na rozhraní dvou materiálů."""
        return 2.0 * a * b / (a + b)

    def _index(self, iy: int, ix: int) -> int:
        return iy * self.nx + ix

    def solve(self) -> np.ndarray:
        """
        Sestaví a vyřeší lineární systém.

        Pro jednu buňku platí energetická bilance:
            součet(G_face * (T_buňka - T_soused/okraj)) = 0
        """
        n = self.nx * self.ny
        A = lil_matrix((n, n), dtype=float)
        b = np.zeros(n, dtype=float)

        for iy in range(self.ny):
            for ix in range(self.nx):
                p = self._index(iy, ix)
                k_p = self.lambda_field[iy, ix]
                diagonal = 0.0

                # Levý soused nebo levý okraj
                if ix > 0:
                    k_n = self.lambda_field[iy, ix - 1]
                    g = self._harmonic_mean(k_p, k_n) * self.dy / self.dx
                    A[p, self._index(iy, ix - 1)] = -g
                    diagonal += g
                elif "left" in self.boundary_temperatures:
                    # Vzdálenost středu krajní buňky od okraje je dx/2.
                    g = k_p * self.dy / (0.5 * self.dx)
                    diagonal += g
                    b[p] += g * self.boundary_temperatures["left"]

                # Pravý soused nebo pravý okraj
                if ix < self.nx - 1:
                    k_n = self.lambda_field[iy, ix + 1]
                    g = self._harmonic_mean(k_p, k_n) * self.dy / self.dx
                    A[p, self._index(iy, ix + 1)] = -g
                    diagonal += g
                elif "right" in self.boundary_temperatures:
                    g = k_p * self.dy / (0.5 * self.dx)
                    diagonal += g
                    b[p] += g * self.boundary_temperatures["right"]

                # Dolní soused nebo dolní okraj
                if iy > 0:
                    k_n = self.lambda_field[iy - 1, ix]
                    g = self._harmonic_mean(k_p, k_n) * self.dx / self.dy
                    A[p, self._index(iy - 1, ix)] = -g
                    diagonal += g
                elif "bottom" in self.boundary_temperatures:
                    g = k_p * self.dx / (0.5 * self.dy)
                    diagonal += g
                    b[p] += g * self.boundary_temperatures["bottom"]

                # Horní soused nebo horní okraj
                if iy < self.ny - 1:
                    k_n = self.lambda_field[iy + 1, ix]
                    g = self._harmonic_mean(k_p, k_n) * self.dx / self.dy
                    A[p, self._index(iy + 1, ix)] = -g
                    diagonal += g
                elif "top" in self.boundary_temperatures:
                    g = k_p * self.dx / (0.5 * self.dy)
                    diagonal += g
                    b[p] += g * self.boundary_temperatures["top"]

                if diagonal == 0:
                    raise RuntimeError(
                        "Model nemá žádnou pevnou okrajovou teplotu, "
                        "takže řešení není jednoznačné."
                    )

                A[p, p] = diagonal

        solution = spsolve(A.tocsr(), b)
        self.temperature = solution.reshape((self.ny, self.nx))
        return self.temperature

    def boundary_heat_flow(self, side: Side) -> float:
        """
        Celkový tepelný tok přes zvolený okraj [W/m].

        Jde o výkon na 1 metr délky kolmo k 2D řezu.
        Kladná hodnota znamená tok z okraje do modelu.
        """
        if self.temperature is None:
            raise RuntimeError("Nejprve zavolejte solve().")
        if side not in self.boundary_temperatures:
            raise ValueError(f"Na okraji {side!r} není nastavena teplota.")

        tb = self.boundary_temperatures[side]
        total = 0.0

        if side == "left":
            for iy in range(self.ny):
                k = self.lambda_field[iy, 0]
                g = k * self.dy / (0.5 * self.dx)
                total += g * (tb - self.temperature[iy, 0])

        elif side == "right":
            for iy in range(self.ny):
                k = self.lambda_field[iy, -1]
                g = k * self.dy / (0.5 * self.dx)
                total += g * (tb - self.temperature[iy, -1])

        elif side == "bottom":
            for ix in range(self.nx):
                k = self.lambda_field[0, ix]
                g = k * self.dx / (0.5 * self.dy)
                total += g * (tb - self.temperature[0, ix])

        elif side == "top":
            for ix in range(self.nx):
                k = self.lambda_field[-1, ix]
                g = k * self.dx / (0.5 * self.dy)
                total += g * (tb - self.temperature[-1, ix])

        return float(total)

    def heat_flux(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Vrátí přibližné složky hustoty tepelného toku qx, qy [W/m²].
        q = -lambda * grad(T)
        """
        if self.temperature is None:
            raise RuntimeError("Nejprve zavolejte solve().")

        dT_dy, dT_dx = np.gradient(
            self.temperature, self.dy, self.dx, edge_order=2
        )
        qx = -self.lambda_field * dT_dx
        qy = -self.lambda_field * dT_dy
        return qx, qy

    def plot_temperature(
        self,
        contours: int = 15,
        show_flux: bool = True,
        flux_stride: int = 8,
    ) -> None:
        if self.temperature is None:
            raise RuntimeError("Nejprve zavolejte solve().")

        fig, ax = plt.subplots(figsize=(11, 6))
        image = ax.imshow(
            self.temperature,
            origin="lower",
            extent=(0, self.width, 0, self.height),
            aspect="equal",
        )
        fig.colorbar(image, ax=ax, label="Teplota [°C]")

        xx, yy = np.meshgrid(self.x, self.y)
        contour_set = ax.contour(
            xx,
            yy,
            self.temperature,
            levels=contours,
            linewidths=0.7,
        )
        ax.clabel(contour_set, inline=True, fontsize=8, fmt="%.1f")

        # Obrysy materiálových oblastí
        ax.contour(
            xx,
            yy,
            self.material_index,
            levels=np.arange(len(self.materials)) + 0.5,
            linewidths=1.0,
        )

        if show_flux:
            qx, qy = self.heat_flux()
            s = max(1, int(flux_stride))
            ax.quiver(
                xx[::s, ::s],
                yy[::s, ::s],
                qx[::s, ::s],
                qy[::s, ::s],
            )

        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.set_title("2D stacionární vedení tepla")
        plt.tight_layout()
        plt.show()

    def plot_materials(self) -> None:
        fig, ax = plt.subplots(figsize=(11, 6))
        cmap = ListedColormap(plt.cm.tab20(np.linspace(0, 1, len(self.materials))))
        image = ax.imshow(
            self.material_index,
            origin="lower",
            extent=(0, self.width, 0, self.height),
            aspect="equal",
            cmap=cmap,
            vmin=-0.5,
            vmax=len(self.materials) - 0.5,
        )

        cbar = fig.colorbar(
            image,
            ax=ax,
            ticks=np.arange(len(self.materials)),
            label="Materiál",
        )
        cbar.ax.set_yticklabels(
            [f"{m.name} (λ={m.conductivity:g})" for m in self.materials]
        )

        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.set_title("Materiálová geometrie")
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    # Ukázkový řez okrajem podlahy a základu.
    # Celá oblast je nejprve zemina.
    model = HeatModel2D(
        width=5.0,
        height=3.2,
        nx=250,
        ny=160,
        default_lambda=1.5,
        default_name="zemina",
    )

    # x1, y1, x2, y2, lambda, název
    model.add_box(0.0, 2.55, 3.9, 2.75, 2.1, "železobetonová deska")
    model.add_box(0.0, 2.15, 3.9, 2.55, 0.085, "pěnosklo")
    model.add_box(3.9, 0.25, 4.55, 2.75, 2.1, "základový pas")
    model.add_box(3.72, 0.25, 3.90, 2.75, 0.045, "vnitřní izolace")
    model.add_box(4.55, 0.25, 4.75, 2.95, 0.045, "vnější perimetr")
    model.add_box(3.9, 2.75, 4.35, 3.2, 0.18, "obvodové zdivo")
    model.add_box(0.0, 2.75, 3.9, 3.2, 0.026, "interiérový vzduch – náhrada")

    # Zjednodušené okrajové podmínky.
    model.set_boundary_temperature("top", 20.0)
    model.set_boundary_temperature("right", -5.0)
    model.set_boundary_temperature("bottom", 8.0)
    # Levý okraj zůstává adiabatický – představuje osu symetrie/interiér.

    model.plot_materials()
    model.solve()
    model.plot_temperature()

    print(f"Tok přes horní okraj:   {model.boundary_heat_flow('top'):.3f} W/m")
    print(f"Tok přes pravý okraj:   {model.boundary_heat_flow('right'):.3f} W/m")
    print(f"Tok přes spodní okraj:  {model.boundary_heat_flow('bottom'):.3f} W/m")
