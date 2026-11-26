"""Level 1 – Zwei-Massen-Modell Springer/Brett (SPEC Kap. 6.1).

    M  z̈_c = F_Bein − M g
    m_b z̈_b = −k_s z_b − c_b ż_b − F_Bein
    F_Bein = max(0, k_l·max(0, l_TD − l) − c_l l̇ + a(t) F_max f(l) h(l̇)),   l = z_c − z_b

Phasen: P3 Hürdenflug (Brett frei, gedämpft) → P4 Depression (TD bis ż_b = 0) →
P5 Recoil → P6 Takeoff (F_Bein = 0) → P7 Flug (analytisch, core.flight).

Zustandsvektor y (SI):
    0 z_c  KSP-Höhe [m]            1 v_c  [m/s]
    2 z_b  Brettspitze [m]         3 v_b  [m/s]
    4 W_act  aktive Beinarbeit ∫F_act l̇ dt [J]
    5 D_leg  Beinverluste ∫c_l l̇² dt (+ lastfreie Federentspannung bei F=0) [J]
    6 D_board Brettdämpfung ∫c_b ż_b² dt [J]
    7 W_board  Energie Springer→Brett ∫(−F ż_b) dt [J]
    8 J_z  vertikaler Kraftstoß ∫F dt [N s]
Zeit t = 0 beim Touchdown; negative Zeiten im Hürdenflug.

Die Passivfeder des Beins hat ihre Ruhelänge l_TD (Beingeometrie bei TD), sodass
die Kontaktkraft beim Aufsetzen stetig bei 0 beginnt; Streckung über l_TD hinaus
erzeugt nur der aktive Term bis zur vollen Streckung l_max.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..board import BoardModel, board_phase_deg, make_board
from ..events import Event, integrate
from ..flight import flight, sample
from ..muscles import Activation, force_length, force_velocity
from ..params import ParamSet

N_STATE = 9


@dataclass(frozen=True)
class Level1Config:
    """Abgeleitete Modellgrößen (SI)."""

    M: float
    g: float
    H: float
    l_td: float
    l_max: float
    l_opt: float
    k_leg: float
    c_leg: float
    F_max: float
    v0: float
    gamma: float
    ecc: float
    act: Activation
    board: BoardModel
    active: bool = True  # False → passiver Springer (Tests)
    dt: float = 1e-4
    t_contact_max: float = 2.0
    event_tol: float = 1e-8

    @staticmethod
    def from_params(p: ParamSet, active: bool = True) -> "Level1Config":
        H, M, g = p["athlete.height"], p["athlete.mass"], p["numerics.g"]
        return Level1Config(
            M=M, g=g, H=H,
            l_td=p["leg.l_td_ratio"] * H,
            l_max=p["leg.l_max_ratio"] * H,
            l_opt=p["leg.l_opt_ratio"] * H,
            k_leg=p["leg.k_leg_per_kg"] * M,
            c_leg=p["leg.c_leg"],
            F_max=p["leg.f_max_bw"] * M * g,
            v0=p["leg.v0"], gamma=p["leg.gamma"], ecc=p["leg.ecc_factor"],
            act=Activation(
                a0=p["activation.a0"], t_on=p["activation.t_on"], t_rise=p["activation.t_rise"],
                a_plateau=p["activation.a_plateau"], t_off=p["activation.t_off"],
                t_fall=p["activation.t_fall"], a_end=p["activation.a_end"],
            ),
            board=make_board(p),
            active=active,
            dt=p["numerics.dt"],
            t_contact_max=p["numerics.t_contact_max"],
            event_tol=p["numerics.event_tol"],
        )


# ---------------------------------------------------------------------------
# Kraftgesetz und rechte Seiten
# ---------------------------------------------------------------------------

def leg_force_parts(cfg: Level1Config, t: float, y: list[float]) -> tuple[float, float, float, float]:
    """Rohe (ungeclampte) Beinkraft und ihre Anteile [N].

    Rückgabe: (F_raw, F_spring, F_damp, F_act); F_raw = Summe.
    """
    l = y[0] - y[2]
    ldot = y[1] - y[3]
    comp = cfg.l_td - l
    f_spring = cfg.k_leg * comp if comp > 0.0 else 0.0
    f_damp = -cfg.c_leg * ldot
    f_act = 0.0
    if cfg.active:
        f_act = cfg.act(t) * cfg.F_max * force_length(l, cfg.l_opt, cfg.l_max) * force_velocity(ldot, cfg.v0, cfg.gamma, cfg.ecc)
    return f_spring + f_damp + f_act, f_spring, f_damp, f_act


def rhs_contact(cfg: Level1Config):
    b = cfg.board
    M, g = cfg.M, cfg.g

    def f(t: float, y: list[float]) -> list[float]:
        F_raw, f_s, _fd, f_act = leg_force_parts(cfg, t, y)
        F = F_raw if F_raw > 0.0 else 0.0
        ldot = y[1] - y[3]
        return [
            y[1],
            F / M - g,
            y[3],
            (-b.k_s * y[2] - b.c_b * y[3] - F) / b.m_b,
            f_act * ldot if F_raw > 0.0 else 0.0,
            # geclampt (F = 0): Passivfeder entspannt lastfrei → Verlust im Bein
            cfg.c_leg * ldot * ldot if F_raw > 0.0 else f_s * ldot,
            b.c_b * y[3] * y[3],
            -F * y[3],
            F,
        ]

    return f


def rhs_free(cfg: Level1Config):
    """Kein Kontakt: Springer ballistisch, Brett frei gedämpft (P3)."""
    b = cfg.board
    g = cfg.g

    def f(_t: float, y: list[float]) -> list[float]:
        return [y[1], -g, y[3], (-b.k_s * y[2] - b.c_b * y[3]) / b.m_b, 0.0, 0.0, b.c_b * y[3] * y[3], 0.0, 0.0]

    return f


def mechanical_energy(cfg: Level1Config, y: list[float], contact: bool) -> float:
    """Mechanische Gesamtenergie [J] ohne horizontale kinetische Energie (konstant)."""
    b = cfg.board
    e = 0.5 * cfg.M * y[1] ** 2 + cfg.M * cfg.g * y[0] + 0.5 * b.m_b * y[3] ** 2 + 0.5 * b.k_s * y[2] ** 2
    if contact:
        comp = cfg.l_td - (y[0] - y[2])
        if comp > 0:
            e += 0.5 * cfg.k_leg * comp * comp
    return e


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class Level1Result:
    """Ergebnis einer Level-1-Simulation. Zeiten in s (0 = TD), SI-Einheiten."""

    series: dict[str, np.ndarray]  # Rohstützstellen (alle RK4-Punkte)
    events: dict[str, float]  # Ereigniszeiten
    metrics: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def initial_state_hurdle(cfg: Level1Config, p: ParamSet) -> list[float]:
    """Zustand bei Hürden-Lift-off: Bein voll gestreckt (l_max) auf dem Brett."""
    z_b = p["technique.board_z_hurdle"]
    v_b = p["technique.board_v_hurdle"]
    v_up = math.sqrt(2.0 * cfg.g * p["technique.hurdle_height"])
    return [z_b + cfg.l_max, v_up, z_b, v_b, 0.0, 0.0, 0.0, 0.0, 0.0]


def initial_state_td(cfg: Level1Config, p: ParamSet) -> list[float]:
    """Zustand direkt bei Touchdown (Start in P4)."""
    z_b = p["technique.board_z_td"]
    return [z_b + cfg.l_td, -abs(p["technique.v_z_td"]), z_b, p["technique.board_v_td"], 0.0, 0.0, 0.0, 0.0, 0.0]


def integrate_with_kinks(f, t0: float, y0: list[float], cfg: Level1Config, terminal: list[Event], kinks: list[Event]):
    """Integriert bis zu einem terminalen Ereignis; Knick-Ereignisse beenden nur den
    RK4-Schritt (Neustart am Knick). Rückgabe wie ``integrate``."""
    from ..events import IntegrationResult

    ts, ys = [t0], [list(y0)]
    t, y = t0, list(y0)
    names = {e.name for e in kinks}
    for _ in range(10000):
        r = integrate(f, t, y, cfg.dt, cfg.t_contact_max, terminal + kinks, cfg.event_tol)
        ts += r.t[1:]
        ys += r.y[1:]
        t, y = r.t[-1], r.y[-1]
        if r.event not in names:
            return IntegrationResult(ts, ys, r.event)
    return IntegrationResult(ts, ys, None)


def simulate(p: ParamSet, active: bool = True, cfg: Level1Config | None = None) -> Level1Result:
    """Volle Level-1-Simulation P3 (optional) → P7."""
    cfg = cfg or Level1Config.from_params(p, active=active)
    b = cfg.board
    warnings: list[str] = []
    seg_t: list[list[float]] = []
    seg_y: list[list[list[float]]] = []
    seg_contact: list[bool] = []
    phase_marks: dict[str, float] = {}

    # --- P3 Hürdenflug -----------------------------------------------------
    hurdle = p["technique.start_mode"] == "hurdle"
    if hurdle:
        y0 = initial_state_hurdle(cfg, p)
        td_event = Event("TD", lambda t, y: (y[0] - y[2]) - cfg.l_td, -1)
        r = integrate(rhs_free(cfg), 0.0, y0, cfg.dt, 5.0, [td_event], cfg.event_tol)
        if r.event != "TD":
            raise RuntimeError("Kein Touchdown nach Hürde gefunden")
        t_td_local = r.t[-1]
        seg_t.append([t - t_td_local for t in r.t])
        seg_y.append(r.y)
        seg_contact.append(False)
        phase_marks["HTO"] = -t_td_local
        y_td = list(r.y[-1])
    else:
        y_td = initial_state_td(cfg, p)

    E0 = mechanical_energy(cfg, (seg_y[0][0] if hurdle else y_td), False)

    # --- P4 Depression bis tiefster Punkt ----------------------------------
    phase_marks["TD"] = 0.0
    lp_event = Event("LP", lambda t, y: y[3], +1)
    to_event = Event("TO", lambda t, y: leg_force_parts(cfg, t, y)[0], -1)
    f_c = rhs_contact(cfg)
    # In P4 gibt es keinen Takeoff: kurzzeitiges F_roh ≤ 0 (leichtes Brett federt nach
    # dem Aufprall weg) wird als Kraft 0 bei weiter bestehendem Fußkontakt behandelt.
    # Knicke im Kraftgesetz (Clamp F ≥ 0, Passivfeder an l = l_TD) werden als
    # nicht-terminale Ereignisse geortet, damit RK4 nie über einen Knick integriert.
    kinks = [
        Event("KINK_F", lambda t, y: leg_force_parts(cfg, t, y)[0], 0),
        Event("KINK_L", lambda t, y: cfg.l_td - (y[0] - y[2]), 0),
    ]
    r = integrate_with_kinks(f_c, 0.0, y_td, cfg, [lp_event], kinks)
    seg_t.append(r.t)
    seg_y.append(r.y)
    seg_contact.append(True)
    if r.event == "LP":
        phase_marks["LP"] = r.t[-1]
        r2 = integrate_with_kinks(f_c, r.t[-1], r.y[-1], cfg, [to_event], kinks[1:])
        seg_t.append(r2.t[1:])
        seg_y.append(r2.y[1:])
        seg_contact.append(True)
        r = r2
    else:
        warnings.append("Kein tiefster Brettpunkt innerhalb der maximalen Kontaktzeit.")
    if r.event != "TO":
        warnings.append(f"Kein Takeoff innerhalb {cfg.t_contact_max} s Kontaktzeit.")
    t_to = r.t[-1]
    y_to = list(r.y[-1])
    phase_marks["TO"] = t_to

    # --- Zeitreihen zusammensetzen ----------------------------------------
    t_all: list[float] = []
    Y: list[list[float]] = []
    contact_flag: list[bool] = []
    for ts, ys, c in zip(seg_t, seg_y, seg_contact):
        t_all.extend(ts)
        Y.extend(ys)
        contact_flag.extend([c] * len(ts))
    T = np.asarray(t_all)
    A = np.asarray(Y)
    Fc = np.array([max(0.0, leg_force_parts(cfg, t, y)[0]) if c else 0.0 for t, y, c in zip(t_all, Y, contact_flag)])
    act = np.array([cfg.act(t) if (c and cfg.active) else 0.0 for t, c in zip(t_all, contact_flag)])

    # --- P7 Flug -----------------------------------------------------------
    H, g = cfg.H, cfg.g
    v_x = p["technique.v_x"]
    x_td = -b.d
    x_to = x_td + v_x * t_to
    z_entry = -p["board.height_above_water"] + p["technique.entry_offset_ratio"] * H
    fr = flight(y_to[0], y_to[1], x_to, v_x, g, z_entry)

    # Brett nach TO frei weiter (für Visualisierung/Freigang), 1 ms Raster
    r_post = integrate(rhs_free(cfg), t_to, y_to, cfg.dt, t_to + fr.t_water, [], cfg.event_tol)

    # --- Energiebilanz -----------------------------------------------------
    E_to = mechanical_energy(cfg, y_to, True)
    W_act, D_leg, D_board = y_to[4], y_to[5], y_to[6]
    E_ref = max(abs(E0), abs(E_to), 0.5 * cfg.M * y_to[1] ** 2, 1.0)
    balance_err = (E_to - E0) - (W_act - D_leg - D_board)
    balance_rel = abs(balance_err) / E_ref
    if balance_rel > 0.005:
        warnings.append(f"Energiebilanz-Abweichung {balance_rel * 100:.2f} % > 0,5 %")

    # --- Kennwerte ---------------------------------------------------------
    i_c0 = next(i for i, c in enumerate(contact_flag) if c)
    tc = T[i_c0:]
    Fc_c = Fc[i_c0:]
    Ac = A[i_c0:]
    t_lp = phase_marks.get("LP", float("nan"))
    W_board_dep = float(np.trapezoid(np.where(tc <= t_lp, -Fc_c * Ac[:, 3], 0.0), tc)) if "LP" in phase_marks else float("nan")
    W_board_rec = float(np.trapezoid(np.where(tc > t_lp, Fc_c * Ac[:, 3], 0.0), tc)) if "LP" in phase_marks else float("nan")
    J_dep = float(np.trapezoid(np.where(tc <= t_lp, Fc_c, 0.0), tc)) if "LP" in phase_marks else float("nan")
    J_rec = float(np.trapezoid(np.where(tc > t_lp, Fc_c, 0.0), tc)) if "LP" in phase_marks else float("nan")
    m50 = (tc > 0) & (tc <= 0.05)
    dF = np.diff(Fc_c) / np.maximum(np.diff(tc), 1e-12)
    rfd = float(np.max(dF[m50[1:]])) if np.any(m50[1:]) else float("nan")
    i_peak = int(np.argmax(Fc_c))
    BW = cfg.M * g
    y_lp = Ac[np.argmin(np.abs(tc - t_lp))] if "LP" in phase_marks else Ac[-1]

    hurdle_metrics: dict[str, Any] = {}
    if hurdle:
        hurdle_metrics = {
            "hurdle_flight_time": -phase_marks["HTO"],
            "hurdle_height": p["technique.hurdle_height"],
            "board_phase_td_deg": board_phase_deg(y_td[2], y_td[3], b.omega0),
        }
    else:
        hurdle_metrics = {"board_phase_td_deg": board_phase_deg(y_td[2], y_td[3], b.omega0) if (y_td[2] or y_td[3]) else float("nan")}

    metrics: dict[str, Any] = {
        # Brett
        "board_k_s": b.k_s, "board_m_b": b.m_b, "board_f0": b.f0, "board_f_loaded": b.f_loaded(cfg.M),
        # TD
        "v_z_td": y_td[1], "v_x_td": v_x, "z_b_td": y_td[2], "v_b_td": y_td[3],
        "v_rel_td": y_td[1] - y_td[3],
        # LP
        "z_b_min": float(np.min(Ac[:, 2])), "v_b_min": float(np.min(Ac[:, 3])), "v_z_lp": float(y_lp[1]), "z_c_lp": float(y_lp[0]),
        # TO
        "v_z_to": y_to[1], "v_x_to": v_x, "z_c_to": y_to[0], "z_b_to": y_to[2], "v_b_to": y_to[3],
        "takeoff_angle_deg": math.degrees(math.atan2(y_to[1], v_x)),
        # Kräfte
        "F_peak": float(Fc_c[i_peak]), "F_peak_bw": float(Fc_c[i_peak] / BW), "t_F_peak": float(tc[i_peak]),
        "F_mean_bw": float(np.trapezoid(Fc_c, tc) / max(t_to, 1e-9) / BW),
        "board_spring_force_max": float(b.k_s * -np.min(Ac[:, 2])),
        "rfd_max": rfd,
        "impulse_z": float(y_to[8]), "impulse_dep": J_dep, "impulse_rec": J_rec,
        # Zeiten
        "t_depression": t_lp, "t_recoil": t_to - t_lp, "t_contact": t_to,
        "t_flight": fr.t_water, "t_apex": fr.t_apex,
        # Höhen
        "h_max_board": fr.z_apex, "h_max_water": fr.z_apex + p["board.height_above_water"],
        "h_rise": fr.h_rise, "x_board_plane": fr.x_board_plane, "x_water": fr.x_water, "z_entry": z_entry,
        # Energie
        "E_kin_to": 0.5 * cfg.M * (y_to[1] ** 2 + v_x ** 2),
        "E_board_max": 0.5 * b.k_s * float(np.min(Ac[:, 2])) ** 2,
        "W_act": W_act, "W_act_per_kg": W_act / cfg.M, "D_leg": D_leg, "D_board": D_board,
        "W_athlete_to_board": W_board_dep, "W_board_to_athlete": W_board_rec,
        "board_efficiency": W_board_rec / W_board_dep if W_board_dep and W_board_dep > 0 else float("nan"),
        "energy_balance_rel": balance_rel,
        "leg_power_peak": float(np.max(Fc_c * (Ac[:, 1] - Ac[:, 3]))),
        # Rotation (Level 1: nicht modelliert)
        "H_y": None, "rotation_potential": None,
        **hurdle_metrics,
    }
    metrics["leg_power_peak_per_kg"] = metrics["leg_power_peak"] / cfg.M

    series = {
        "t": T, "z_c": A[:, 0], "v_c": A[:, 1], "z_b": A[:, 2], "v_b": A[:, 3],
        "F": Fc, "act": act, "contact": np.asarray(contact_flag, dtype=bool),
        "W_act": A[:, 4], "D_leg": A[:, 5], "D_board": A[:, 6],
        "t_post": np.asarray(r_post.t), "z_b_post": np.asarray([y[2] for y in r_post.y]),
    }
    return Level1Result(series=series, events=phase_marks, metrics=metrics, warnings=warnings)


def resample(res: Level1Result, p: ParamSet, rate: float | None = None) -> dict[str, np.ndarray]:
    """Gibt alle Zeitverläufe auf ein festes Raster (Default 1 kHz) aus, inkl. Flug."""
    rate = rate or p["numerics.output_rate"]
    s = res.series
    t0 = float(s["t"][0])
    t_to = res.events["TO"]
    t_end = t_to + res.metrics["t_flight"]
    t = np.arange(math.ceil(t0 * rate), math.floor(t_end * rate) + 1) / rate
    out = {"t": t}
    stance = t <= t_to
    for key in ("z_c", "v_c", "F", "act"):
        out[key] = np.interp(t, s["t"], s[key])
    tb = np.concatenate([s["t"], s["t_post"][1:]])
    zb = np.concatenate([s["z_b"], s["z_b_post"][1:]])
    out["z_b"] = np.interp(t, tb, zb)
    tf = np.clip(t - t_to, 0.0, None)
    x_to = -p["technique.d_toes"] + p["technique.v_x"] * t_to
    xf, zf, vf = sample(res.metrics["z_c_to"], res.metrics["v_z_to"], x_to, p["technique.v_x"], p["numerics.g"], tf)
    out["z_c"] = np.where(stance, out["z_c"], zf)
    out["v_c"] = np.where(stance, out["v_c"], vf)
    out["F"] = np.where(stance, out["F"], 0.0)
    out["x_c"] = np.where(t <= 0, -p["technique.d_toes"] + p["technique.v_x"] * t, np.where(stance, -p["technique.d_toes"] + p["technique.v_x"] * t, xf))
    out["x_b"] = -p["board.horiz_coeff"] * out["z_b"] ** 2
    return out
