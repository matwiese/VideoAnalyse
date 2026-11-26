"""Aktivierung und Kraft-Länge-/Kraft-Geschwindigkeits-Beziehungen (SPEC Kap. 5.3).

Level 1 nutzt einen linearen Bein-Aktuator: F_act = a(t) · F_max · f(l) · h(l̇).
Die Funktionsformen sind dieselben, die Level 2 je Gelenk (θ, ω) verwendet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def smoothstep5(s: float) -> float:
    """Quintische Rampe S(s) = 6s⁵ − 15s⁴ + 10s³, C²-stetig, S(0)=0, S(1)=1."""
    if s <= 0.0:
        return 0.0
    if s >= 1.0:
        return 1.0
    return s * s * s * (s * (6.0 * s - 15.0) + 10.0)


@dataclass(frozen=True)
class Activation:
    """Aktivierung a(t) ∈ [0, 1], t in s relativ zum Touchdown.

    a0 → Rampe ab t_on über t_rise auf a_plateau → ab t_off über t_fall auf a_end
    (Abfall vor dem Takeoff auf nachgiebigem Untergrund, Cheng & Hubbard 2005).
    """

    a0: float
    t_on: float
    t_rise: float
    a_plateau: float
    t_off: float
    t_fall: float
    a_end: float

    def __call__(self, t: float) -> float:
        a = self.a0 + (self.a_plateau - self.a0) * smoothstep5((t - self.t_on) / self.t_rise)
        if t > self.t_off:
            a = a + (self.a_end - a) * smoothstep5((t - self.t_off) / self.t_fall)
        return min(1.0, max(0.0, a))


def force_length(l: float, l_opt: float, l_max: float) -> float:
    """Quadratische Kraft-Länge-Beziehung f(l) ∈ [0, 1], f(l_opt)=1, f(l_max)=0.

    Symmetrisch um l_opt; für l ≥ l_max ist das Bein voll gestreckt (f = 0).
    """
    if l >= l_max:
        return 0.0
    w = l_max - l_opt
    x = (l - l_opt) / w
    return max(0.0, 1.0 - x * x)


def force_velocity(v: float, v0: float, gamma: float, ecc: float) -> float:
    """Kraft-Geschwindigkeit h(v), v = Streckgeschwindigkeit (>0 konzentrisch).

    Konzentrisch (Selbie & Caldwell 1996):  h = (v0 − v)/(v0 + Γ v), 0 ≤ v < v0.
    Exzentrisch (v < 0): Plateau ``ecc`` (Yeadon, King & Wilson 2006),
    h = ecc − (ecc − 1)·exp(−s·|v|) mit s so gewählt, dass h in v = 0 C¹-stetig ist.
    """
    if v >= v0:
        return 0.0
    if v >= 0.0:
        return (v0 - v) / (v0 + gamma * v)
    if ecc <= 1.0:
        return 1.0
    s = (1.0 + gamma) / (v0 * (ecc - 1.0))
    return ecc - (ecc - 1.0) * math.exp(s * v)
