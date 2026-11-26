"""Sprungbrettmodell Duraflex Maxiflex B (SPEC Kap. 4).

Brettspitze als effektive Masse m_b an linearer Feder k_s(d, F):

    m_b z̈_b = −k_s z_b − c_b ż_b − F_c          (SPEC 4.2, 4.5)

z_b = 0 ist der unbelastete Ruhezustand (Eigengewicht im Nullpunkt enthalten,
deshalb kein m_b·g-Term). Einheiten: m, kg, N, s.

Hinweis zur Steifigkeit k_s(d) (siehe docs/validation/model-notes.md): Die
Matching-Konstanten m_k = 7551 N/m², c_k = 3597 N/m liefern mit
k = m_k (d + 0,15) + c_k bei d = 0 nur 4730 N/m, gemessen sind 5446 N/m an der
Spitze. Damit der überschreibbare Messwert k_s(7,5) die Referenz bleibt, nutzt
der Default die Steigung m_k mit dem Messwert als Achsenabschnitt:
k_s(d) = k_tip + m_k · d.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .params import ParamSet

REF_FULCRUM = 7.5


@dataclass(frozen=True)
class BoardModel:
    """Abgeleitete Brettparameter für eine konkrete Einstellung.

    Attribute (SI): k_s [N/m] am Lastort d, m_b [kg], c_b [N s/m],
    horiz_coeff [1/m], d [m], fulcrum [-], model ['A'|'B'].
    """

    k_s: float
    m_b: float
    c_b: float
    zeta: float
    horiz_coeff: float
    d: float
    fulcrum: float
    model: str
    EI_eff: float  # N m² (nur Variante B relevant, sonst aus Kalibrierung informativ)
    span: float  # m, Anker–Fulkrum
    overhang: float  # m, Fulkrum–Spitze

    # --- abgeleitete Größen -------------------------------------------------
    @property
    def omega0(self) -> float:
        """Eigenkreisfrequenz leeres Brett [rad/s] (ungedämpft)."""
        return math.sqrt(self.k_s / self.m_b)

    @property
    def f0(self) -> float:
        """Eigenfrequenz leeres Brett [Hz]."""
        return self.omega0 / (2.0 * math.pi)

    def f_loaded(self, mass: float) -> float:
        """Eigenfrequenz mit aufgesetzter Masse [Hz] ≈ √(k/(m_b+M))/2π (SPEC 4.5)."""
        return math.sqrt(self.k_s / (self.m_b + mass)) / (2.0 * math.pi)

    def x_tip(self, z_b: float) -> float:
        """Horizontale Spitzenverschiebung x_b = −c z_b² [m] (Kong et al. 2004)."""
        return -self.horiz_coeff * z_b * z_b

    def spring_energy(self, z_b: float) -> float:
        """Brett-Federenergie ½ k_s z_b² [J]."""
        return 0.5 * self.k_s * z_b * z_b


def _beam_k(EI: float, a: float, span: float) -> float:
    """Kragbalken mit Auflager am Fulkrum: k = 3 EI / (a² (L_s + a)) [N/m]."""
    return 3.0 * EI / (a * a * (span + a))


def stiffness(p: ParamSet, d: float, fulcrum: float, model: str | None = None) -> tuple[float, float, float, float]:
    """Steifigkeit k_s(d, F) [N/m] nach Variante A oder B (SPEC 4.3).

    Rückgabe: (k_s, EI_eff, span, overhang).
    """
    model = model or p["board.fulcrum_model"]
    k_tip = p["board.k_tip_75"]
    step_len = p["board.fulcrum_step_length"]
    span0 = p["board.span_75"]
    a0 = p["board.overhang_75"]
    EI = k_tip * a0 * a0 * (span0 + a0) / 3.0  # Kalibrierung auf k(7,5; d=0)
    shift = step_len * (fulcrum - REF_FULCRUM)  # höhere Stufe → Fulkrum Richtung Anker
    span = span0 - shift
    overhang = a0 + shift
    if model == "A":
        k = k_tip + p["board.m_k"] * d + p["board.delta_k_per_step"] * (REF_FULCRUM - fulcrum)
    elif model == "B":
        k = _beam_k(EI, overhang - d, span)
    else:
        raise ValueError(f"Unbekanntes Fulkrum-Modell {model!r}")
    if k <= 0:
        raise ValueError("Brettsteifigkeit ≤ 0 – Parameter prüfen")
    return k, EI, span, overhang


def effective_mass(p: ParamSet, fulcrum: float, model: str | None = None) -> float:
    """m_b(F) = m_b(7,5) · [k(7,5)/k(F)]^n, Lastort Spitze (SPEC 4.3, Schätzung)."""
    k_ref, *_ = stiffness(p, 0.0, REF_FULCRUM, model)
    k_f, *_ = stiffness(p, 0.0, fulcrum, model)
    return p["board.m_b_75"] * (k_ref / k_f) ** p["board.mb_exponent"]


def make_board(p: ParamSet, d: float | None = None) -> BoardModel:
    """Brettmodell für die Einstellung im Parametersatz; d = Abstand Zehen–Spitze [m]."""
    d = p["technique.d_toes"] if d is None else d
    fulcrum = p["board.fulcrum"]
    model = p["board.fulcrum_model"]
    k, EI, span, overhang = stiffness(p, d, fulcrum, model)
    m_b = effective_mass(p, fulcrum, model)
    zeta = p["board.zeta"]
    c_b = 2.0 * zeta * math.sqrt(k * m_b)
    return BoardModel(
        k_s=k, m_b=m_b, c_b=c_b, zeta=zeta, horiz_coeff=p["board.horiz_coeff"], d=d,
        fulcrum=fulcrum, model=model, EI_eff=EI, span=span, overhang=overhang,
    )


def free_board_rhs(board: BoardModel):
    """RHS der freien Brettschwingung y = [z_b, ż_b] (SPEC 4.5)."""

    def rhs(_t: float, y: list[float]) -> list[float]:
        z, v = y[0], y[1]
        return [v, (-board.k_s * z - board.c_b * v) / board.m_b]

    return rhs


def board_phase_deg(z_b: float, v_b: float, omega: float) -> float:
    """Phasenlage der Brettschwingung [°] aus z_b = A cos(ψ), ż_b = −A ω sin(ψ).

    0° = oberer Umkehrpunkt, 90° = abwärts durch Ruhelage, 180° = unterer
    Umkehrpunkt, 270° = aufwärts durch Ruhelage. Trifft der Springer bei 180–360°
    (Brett schwingt aufwärts), steigt die Relativgeschwindigkeit (SPEC Kap. 2).
    """
    psi = math.degrees(math.atan2(-v_b / omega, z_b))
    return psi % 360.0
