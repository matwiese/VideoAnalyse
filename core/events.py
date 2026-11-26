"""Festschritt-RK4 mit Ereignisortung durch Nullstellensuche (SPEC Kap. 2, 6.4).

Ereignisse werden nicht per Zeitraster erkannt: wechselt eine Event-Funktion g(t, y)
innerhalb eines Schritts das Vorzeichen in der geforderten Richtung, wird die
Teilschrittweite θ ∈ (0, dt] per Bisektion bestimmt (RK4-Schritt der Länge θ ab
Schrittanfang), bis das Intervall kleiner als ``tol`` ist (Default 1e-8 s, also weit
unter den geforderten 0,1 ms).

Dieselbe Logik ist in web/src/sim-live/level1.ts portiert; beide Implementierungen
nutzen identische Gleitkomma-Operationsfolgen, damit Python und TypeScript auf
1e-6 übereinstimmen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

Vec = list[float]
RHS = Callable[[float, Vec], Vec]


@dataclass
class Event:
    """Ereignis: ``g(t, y) = 0`` mit Richtung −1 (fallend), +1 (steigend) oder 0."""

    name: str
    g: Callable[[float, Vec], float]
    direction: int = 0


def rk4_step(f: RHS, t: float, y: Vec, h: float) -> Vec:
    """Ein klassischer RK4-Schritt der Länge h [s]."""
    n = len(y)
    k1 = f(t, y)
    y2 = [y[i] + 0.5 * h * k1[i] for i in range(n)]
    k2 = f(t + 0.5 * h, y2)
    y3 = [y[i] + 0.5 * h * k2[i] for i in range(n)]
    k3 = f(t + 0.5 * h, y3)
    y4 = [y[i] + h * k3[i] for i in range(n)]
    k4 = f(t + h, y4)
    return [y[i] + h / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) for i in range(n)]


def _crossed(g0: float, g1: float, direction: int) -> bool:
    if direction < 0:
        return g0 > 0.0 and g1 <= 0.0
    if direction > 0:
        return g0 < 0.0 and g1 >= 0.0
    return (g0 > 0.0 and g1 <= 0.0) or (g0 < 0.0 and g1 >= 0.0)


@dataclass
class IntegrationResult:
    t: list[float]
    y: list[Vec]
    event: str | None  # Name des ausgelösten Ereignisses oder None (t_max erreicht)


def integrate(
    f: RHS,
    t0: float,
    y0: Vec,
    dt: float,
    t_max: float,
    events: Sequence[Event] = (),
    tol: float = 1e-8,
) -> IntegrationResult:
    """Integriert von t0 bis zum ersten Ereignis oder t_max.

    Gibt alle akzeptierten Stützstellen zurück; der letzte Punkt ist der
    Ereigniszeitpunkt (Genauigkeit ``tol``).
    """
    ts = [t0]
    ys = [list(y0)]
    t, y = t0, list(y0)
    gs = [ev.g(t, y) for ev in events]
    while t < t_max - 1e-15:
        h = min(dt, t_max - t)
        y1 = rk4_step(f, t, y, h)
        g1s = [ev.g(t + h, y1) for ev in events]
        hit = -1
        theta_hit = h
        y_hit = y1
        for i, ev in enumerate(events):
            if _crossed(gs[i], g1s[i], ev.direction):
                lo, hi = 0.0, h
                y_hi = y1
                while hi - lo > tol:
                    mid = 0.5 * (lo + hi)
                    y_mid = rk4_step(f, t, y, mid)
                    if _crossed(gs[i], ev.g(t + mid, y_mid), ev.direction):
                        hi, y_hi = mid, y_mid
                    else:
                        lo = mid
                if hit < 0 or hi < theta_hit:
                    hit, theta_hit, y_hit = i, hi, y_hi
        if hit >= 0:
            t = t + theta_hit
            ts.append(t)
            ys.append(y_hit)
            return IntegrationResult(ts, ys, events[hit].name)
        t, y, gs = t + h, y1, g1s
        ts.append(t)
        ys.append(y)
    return IntegrationResult(ts, ys, None)
