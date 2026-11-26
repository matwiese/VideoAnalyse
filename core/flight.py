"""Flugphase P7 (SPEC Kap. 6.5): Ballistik + Drehimpulserhaltung.

Koordinaten nach SPEC Kap. 3: z = 0 an der unbelasteten Brettoberseite (Spitze),
Wasser bei z = −3,00 m, x positiv Richtung Wasser. Einheiten: m, s, kg.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class FlightResult:
    t_apex: float  # s nach TO
    z_apex: float  # m, KSP-Höhe über Brett (z-Koordinate)
    h_rise: float  # m, KSP-Steigung ab TO
    t_water: float  # s nach TO bis Eintauchen (KSP erreicht z_entry)
    t_board_plane: float  # s nach TO, KSP passiert z = 0 abwärts
    x_board_plane: float  # m, KSP-x beim Passieren der Brettebene (Freigang zur Spitze x=0)
    x_water: float  # m
    rotation_potential: float | None  # H_y · t_Flug [kg m²/s · s]
    somersaults: dict[str, float] = field(default_factory=dict)  # Umdrehungen je Haltung


def time_to_height(z0: float, vz: float, z_target: float, g: float) -> float:
    """Positive Zeit, bis z(t) = z0 + vz t − ½ g t² fallend z_target erreicht [s]."""
    disc = vz * vz + 2.0 * g * (z0 - z_target)
    if disc < 0:
        raise ValueError("Zielhöhe wird nie erreicht")
    return (vz + math.sqrt(disc)) / g


def flight(
    z_to: float,
    vz_to: float,
    x_to: float,
    vx_to: float,
    g: float,
    z_entry: float,
    H_y: float | None = None,
    inertias: dict[str, float] | None = None,
) -> FlightResult:
    """Analytische Flugphase ab Takeoff.

    z_entry: KSP-Höhe beim Eintauchen = −3,0 m + Restlänge (SPEC Kap. 2).
    H_y: Salto-Drehimpuls um den KSP [kg m²/s] (Level 1: None).
    inertias: Trägheitsmomente je Haltung [kg m²] für die Saltoanzahl.
    """
    t_apex = max(vz_to, 0.0) / g
    z_apex = z_to + max(vz_to, 0.0) ** 2 / (2.0 * g)
    t_w = time_to_height(z_to, vz_to, z_entry, g)
    t_bp = time_to_height(z_to, vz_to, 0.0, g) if z_apex >= 0.0 else 0.0
    rot = None
    som: dict[str, float] = {}
    if H_y is not None:
        rot = H_y * t_w
        for name, I in (inertias or {}).items():
            som[name] = H_y * t_w / (2.0 * math.pi * I)
    return FlightResult(
        t_apex=t_apex, z_apex=z_apex, h_rise=z_apex - z_to, t_water=t_w,
        t_board_plane=t_bp, x_board_plane=x_to + vx_to * t_bp, x_water=x_to + vx_to * t_w,
        rotation_potential=rot, somersaults=som,
    )


def sample(z_to: float, vz_to: float, x_to: float, vx_to: float, g: float, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """KSP-Bahn (x, z, v_z) zu Zeiten t nach TO [s]."""
    return x_to + vx_to * t, z_to + vz_to * t - 0.5 * g * t * t, vz_to - g * t


def simulate_rigid_flight(
    y0: tuple[float, float, float, float, float],
    H: float,
    inertia: callable,
    d_inertia: callable,
    g: float,
    t_end: float,
    n: int = 2001,
):
    """Numerischer Flug eines Körpers mit zeitvariablem Trägheitsmoment I(t)
    (Haltungswechsel). Zustand [x, z, vx, vz, θ, ω]; Rotationsgleichung
    d(Iω)/dt = 0 ⇔ ω̇ = −İ ω / I. Referenz für Test 9.1 Nr. 5 und Grundlage der
    Mehrkörper-Flugphase (Level 2)."""
    from scipy.integrate import solve_ivp

    x0, z0, vx0, vz0, th0 = y0
    w0 = H / inertia(0.0)

    def rhs(t, s):
        return [s[2], s[3], 0.0, -g, s[5], -d_inertia(t) * s[5] / inertia(t)]

    ts = np.linspace(0.0, t_end, n)
    sol = solve_ivp(rhs, (0.0, t_end), [x0, z0, vx0, vz0, th0, w0], method="DOP853",
                    rtol=1e-12, atol=1e-13, t_eval=ts)
    return sol.t, sol.y
