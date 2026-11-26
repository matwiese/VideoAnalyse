"""Level 2 – planares Mehrkörpermodell Springer/Brett (SPEC 5, 6.2, 6.4).

Bewegungsgleichungen aus level2_generated.py (SymPy/Kane, scripts/generate_level2.py):
    M(q) u̇ = f(q, u, τ, F_Kontakt, F_Schwabbel),   q̇ = u
Brett: m_b z̈_b = −k_s z_b − c_b ż_b + Q_b, mit Q_b = −Σ F_i · ∂P_i/∂z_b (SPEC 4.2/4.4).
Brettspitze x_b = −c·z_b² (Kong et al. 2004, kinematisch) und Neigung φ_b = κ·z_b aus der
Biegelinie des Kragbalkens (κ = (2L+3a) / (2a(L+a)), SPEC 4.4 „physikalische Alternative“).

Fuß-Brett-Kontakt (SPEC 5.4) an Zehenspitze, Ballen (MTP) und Ferse:
    F⊥ = k⊥ δ + c⊥ δ δ̇  (≥ 0),   F∥ = −k∥ x δ − c∥ δ ẋ
δ Eindringtiefe senkrecht zur Brettoberfläche, x tangentiale Verschiebung seit Kontaktbeginn
(Anker als Materialkoordinate s entlang des Bretts, bei jedem Kontaktbeginn neu gesetzt).

Drehmoment-Generatoren je Gelenk (SPEC 5.3): T = a(t) T_max f(θ) h(ω), getrennt für +θ- und
−θ-Richtung, plus passive exponentielle Endanschläge.

Zeit t = 0 beim Touchdown. Integration: solve_ivp Radau mit Event-Funktionen.
Einheiten SI; Winkel in rad.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from ..athlete import Anthropometry, build_anthropometry
from ..board import BoardModel, board_phase_deg, make_board
from ..events import Event, integrate
from ..flight import flight
from ..muscles import force_velocity, smoothstep5
from ..params import ParamSet
from . import level2_generated as G
from .level1 import Level1Config, rhs_free

JOINTS = G.JOINTS  # mtp, ankle, knee, hip, shoulder, elbow
NQ = 12
IDX_ZB = 24
IDX_VB = 25
ACC = ["W_act", "W_pas", "W_c", "D_w", "D_b", "J_z", "J_x"]
N_STATE = 26 + len(ACC)
WOBBLE = ["trunk", "thigh", "shank"]  # q9, q10, q11


@dataclass(frozen=True)
class Generator:
    """Drehmoment-Generator in +θ (sign=+1) oder −θ (sign=−1) Richtung."""

    joint: int
    sign: int
    tmax: float
    w0: float
    opt: float
    width: float
    a0: float
    t_on: float
    t_rise: float
    a_p: float

    def activation(self, t: float) -> float:
        return self.a0 + (self.a_p - self.a0) * smoothstep5((t - self.t_on) / self.t_rise)


@dataclass(frozen=True)
class Level2Config:
    anthro: Anthropometry
    board: BoardModel
    gens: tuple[Generator, ...]
    rom_min: tuple[float, ...]
    rom_max: tuple[float, ...]
    k1: float
    k2: float
    gamma: float
    ecc: float
    k_perp: float
    c_perp: float
    k_par: float
    c_par: float
    kappa: float  # Brettneigung pro m Durchbiegung [rad/m]
    g: float
    rtol: float
    atol: float
    max_step: float
    t_contact_max: float = 1.5
    active: bool = True
    locked: bool = False  # Gelenke und Schwabbelmassen gesperrt (Test 9.1 Nr. 4)
    contact_points: tuple[str, ...] = ("toe", "ball", "heel")
    linear_contact: bool = False  # nur Test: F⊥ = k⊥ δ, keine Tangentialkraft

    @staticmethod
    def from_params(p: ParamSet, active: bool = True) -> "Level2Config":
        an = build_anthropometry(p)
        b = make_board(p)
        sc = p["athlete.mass"] / p["torque.mass_ref"]
        gens = []
        for j, name in enumerate(JOINTS):
            for sign, s in ((1, "pos"), (-1, "neg")):
                g = f"{name}_{s}"
                gens.append(Generator(
                    joint=j, sign=sign, tmax=p[f"torque.{g}_tmax"] * sc, w0=p[f"torque.{name}_w0"],
                    opt=p[f"torque.{g}_opt"], width=p[f"torque.{name}_width"],
                    a0=p[f"act2.{g}_a0"], t_on=p[f"act2.{g}_on"], t_rise=p[f"act2.{g}_rise"], a_p=p[f"act2.{g}_ap"],
                ))
        a, L = b.overhang, b.span
        kappa = (2 * L + 3 * a) / (2 * a * (L + a)) if p["contact.board_slope"] == "beam" else 0.0
        return Level2Config(
            anthro=an, board=b, gens=tuple(gens),
            rom_min=tuple(p[f"rom.{j}_min"] for j in JOINTS), rom_max=tuple(p[f"rom.{j}_max"] for j in JOINTS),
            k1=p["rom.k1"], k2=p["rom.k2"], gamma=p["torque.gamma"], ecc=p["torque.ecc"],
            k_perp=p["contact.k_perp"], c_perp=p["contact.c_perp"], k_par=p["contact.k_par"], c_par=p["contact.c_par"],
            kappa=kappa, g=p["numerics.g"], rtol=p["numerics.rtol2"], atol=p["numerics.rtol2"] * 1e-3,
            max_step=p["numerics.max_step2"], t_contact_max=p["numerics.t_contact_max"], active=active,
        )


# ---------------------------------------------------------------------------
# Kräfte
# ---------------------------------------------------------------------------

def joint_torques(cfg: Level2Config, t: float, th: np.ndarray, om: np.ndarray):
    """Aktive und passive Gelenkmomente [Nm] je Gelenk (+ = +θ-Richtung)."""
    act = np.zeros(6)
    if cfg.active:
        for gn in cfg.gens:
            j = gn.joint
            a = gn.activation(t)
            if a <= 0.0 or gn.tmax <= 0.0:
                continue
            x = (th[j] - gn.opt) / gn.width
            f = max(0.0, 1.0 - x * x)
            h = force_velocity(gn.sign * om[j], gn.w0, cfg.gamma, cfg.ecc)
            act[j] += gn.sign * min(a, 1.0) * gn.tmax * f * h
    pas = np.empty(6)
    for j in range(6):
        pas[j] = -cfg.k1 * math.exp(cfg.k2 * (th[j] - cfg.rom_max[j])) + cfg.k1 * math.exp(-cfg.k2 * (th[j] - cfg.rom_min[j]))
    return act, pas


def gen_activations(cfg: Level2Config, t: float) -> list[float]:
    return [min(1.0, max(0.0, g.activation(t))) if cfg.active else 0.0 for g in cfg.gens]


@dataclass
class BoardFrame:
    tip: np.ndarray
    t: np.ndarray  # Tangente Richtung Wasser
    n: np.ndarray  # Normale nach oben
    phi: float
    phidot: float
    tipdot: np.ndarray


def board_frame(cfg: Level2Config, zb: float, vb: float) -> BoardFrame:
    c = cfg.board.horiz_coeff
    phi = cfg.kappa * zb
    tv = np.array([math.cos(phi), math.sin(phi)])
    nv = np.array([-math.sin(phi), math.cos(phi)])
    return BoardFrame(np.array([-c * zb * zb, zb]), tv, nv, phi, cfg.kappa * vb, np.array([-2 * c * zb * vb, vb]))


def contact_forces(cfg: Level2Config, q, u, zb, vb, anchors):
    """Kontaktkräfte [N] (x, z) je Punkt, generalisierte Brettkraft Q_b [N],
    Kontaktleistung F·(v − Ṗ) [W] und Penetrationen δ [m]."""
    pts = G.points(q, cfg.anthro.p)
    vel = G.contact_velocities(q, u, cfg.anthro.p)
    bf = board_frame(cfg, zb, vb)
    c = cfg.board.horiz_coeff
    Fc = [0.0] * 6
    Qb = 0.0
    P_c = 0.0
    deltas = []
    for i, name in enumerate(G.CONTACTS):
        r = np.array(pts[2 * i: 2 * i + 2])
        v = np.array(vel[2 * i: 2 * i + 2])
        rel = r - bf.tip
        delta = -float(rel @ bf.n)
        deltas.append(delta)
        if delta <= 0.0 or name not in cfg.contact_points:
            continue
        s = anchors[i] if anchors[i] is not None else -float(rel @ bf.t)
        rP = rel + s * bf.t  # r − P(s)
        Pdot = bf.tipdot - s * bf.phidot * bf.n
        vr = v - Pdot
        ddelta = -float(vr @ bf.n) + float(rP @ (bf.phidot * bf.t))
        if cfg.linear_contact:
            Fn, Ft = cfg.k_perp * delta, 0.0
        else:
            xt = float(rP @ bf.t)
            dxt = float(vr @ bf.t) + float(rP @ (bf.phidot * bf.n))
            Fn = max(0.0, cfg.k_perp * delta + cfg.c_perp * delta * ddelta)
            Ft = -cfg.k_par * xt * delta - cfg.c_par * delta * dxt
        F = Fn * bf.n + Ft * bf.t
        Fc[2 * i], Fc[2 * i + 1] = float(F[0]), float(F[1])
        dPdz = np.array([-2 * c * zb, 1.0]) - s * cfg.kappa * bf.n
        Qb -= float(F @ dPdz)
        P_c += float(F @ vr)
    return Fc, Qb, P_c, deltas


def make_rhs(cfg: Level2Config, anchors: list[float | None]):
    b = cfg.board
    an = cfg.anthro
    kw = [an.wobble_k[w] for w in WOBBLE]
    cw = [an.wobble_c[w] for w in WOBBLE]

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        q = y[:NQ]
        u = y[NQ:2 * NQ]
        zb, vb = y[IDX_ZB], y[IDX_VB]
        th, om = q[3:9], u[3:9]
        act, pas = joint_torques(cfg, t, th, om)
        tau = act + pas
        Fw = [-kw[i] * q[9 + i] ** 3 - cw[i] * u[9 + i] for i in range(3)]
        Fc, Qb, P_c, _d = contact_forces(cfg, q, u, zb, vb, anchors)
        Mm = np.array(G.mass_matrix(q, an.p)).reshape(NQ, NQ)
        fo = np.array(G.forcing(q, u, an.p, tau, Fc, Fw))
        if cfg.locked:
            ud = np.zeros(NQ)
            ud[:3] = np.linalg.solve(Mm[:3, :3], fo[:3])
        else:
            ud = np.linalg.solve(Mm, fo)
        dy = np.empty(N_STATE)
        dy[:NQ] = u
        dy[NQ:2 * NQ] = ud
        dy[IDX_ZB] = vb
        dy[IDX_VB] = (-b.k_s * zb - b.c_b * vb + Qb) / b.m_b
        dy[26] = float(act @ om)
        dy[27] = float(pas @ om)
        dy[28] = P_c
        dy[29] = sum(cw[i] * u[9 + i] ** 2 for i in range(3))
        dy[30] = b.c_b * vb * vb
        dy[31] = Fc[1] + Fc[3] + Fc[5]
        dy[32] = Fc[0] + Fc[2] + Fc[4]
        if cfg.locked:
            dy[26] = dy[27] = dy[29] = 0.0
        return dy

    return rhs


def mechanical_energy(cfg: Level2Config, y: np.ndarray) -> float:
    q, u = y[:NQ], y[NQ:2 * NQ]
    ke, pe = G.energy(q, u, cfg.anthro.p)
    wob = sum(cfg.anthro.wobble_k[w] * q[9 + i] ** 4 / 4 for i, w in enumerate(WOBBLE))
    b = cfg.board
    return ke + pe + wob + 0.5 * b.m_b * y[IDX_VB] ** 2 + 0.5 * b.k_s * y[IDX_ZB] ** 2


def angular_momentum_y(cfg: Level2Config, q, u) -> tuple[float, list[float]]:
    """H_y um den KSP [kg m²/s] (SPEC 3: + = Vorwärtssalto) und Beiträge je Segment."""
    seg = G.segment_momentum(q, u, cfg.anthro.p)
    return -float(sum(seg)), [-float(h) for h in seg]


def inertia_about_com(cfg: Level2Config, q) -> float:
    """Trägheitsmoment des Gesamtkörpers um die Querachse durch den KSP [kg m²]."""
    p = dict(zip(G.PARAM_NAMES, cfg.anthro.p))
    cm = np.array(G.segment_coms(q, cfg.anthro.p)).reshape(-1, 2)
    ms = np.array([p[k] for k in G.MASS_PARAMS])
    rc = (ms[:, None] * cm).sum(0) / ms.sum()
    I = float((ms * ((cm - rc) ** 2).sum(1)).sum())
    I += sum(p[k] for k in G.INERTIA_PARAMS if k)
    return I


# ---------------------------------------------------------------------------
# Anfangszustand bei Touchdown
# ---------------------------------------------------------------------------

def td_posture(p: ParamSet) -> np.ndarray:
    return np.array([p[f"posture.{j}"] for j in JOINTS])


def initial_q(cfg: Level2Config, p: ParamSet, zb: float, joints: np.ndarray | None = None) -> np.ndarray:
    """Zehen flach auf dem Brett, Zehenspitze im Abstand d hinter der Brettspitze, δ = 0."""
    bf = board_frame(cfg, zb, 0.0)
    toe = bf.tip - cfg.board.d * bf.t
    q = np.zeros(NQ)
    q[0], q[1] = toe
    q[2] = math.pi + bf.phi
    q[3:9] = td_posture(p) if joints is None else joints
    return q


def align_ankle(cfg: Level2Config, p: ParamSet, zb: float) -> np.ndarray:
    """Sprunggelenkwinkel so wählen, dass der KSP um ``posture.com_offset`` [m] horizontal
    vom Ballen (MTP) entfernt liegt (Brent-Verfahren). Rückgabe: Gelenkwinkel [rad]."""
    from scipy.optimize import brentq

    joints = td_posture(p)
    if p["posture.align"] != "ja":
        return joints
    target = p["posture.com_offset"]

    def err(ank):
        jj = joints.copy()
        jj[1] = ank
        q = initial_q(cfg, p, zb, jj)
        c = G.com(q, np.zeros(NQ), cfg.anthro.p)
        ball_x = G.points(q, cfg.anthro.p)[2]
        return c[0] - ball_x - target

    lo, hi = cfg.rom_min[1], cfg.rom_max[1]
    if err(lo) * err(hi) > 0:
        return joints
    joints[1] = brentq(err, lo, hi, xtol=1e-10)
    return joints


def com_height_over_toe(cfg: Level2Config, q: np.ndarray) -> float:
    c = G.com(q, np.zeros(NQ), cfg.anthro.p)
    return c[1] - q[1]


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    sol: Any
    t0: float
    t1: float
    anchors: list[float | None]


@dataclass
class Level2Result:
    events: dict[str, float]
    metrics: dict[str, Any]
    series: dict[str, np.ndarray]
    warnings: list[str] = field(default_factory=list)
    level: int = 2


def simulate(p: ParamSet, active: bool = True, cfg: Level2Config | None = None, series: bool = True,
             y_td_override: np.ndarray | None = None) -> Level2Result:
    cfg = cfg or Level2Config.from_params(p, active=active)
    b = cfg.board
    an = cfg.anthro
    M = an.total_mass
    g = cfg.g
    warnings: list[str] = []
    events: dict[str, float] = {}

    # --- P3 Hürdenflug (KSP ballistisch, Brett frei) -----------------------
    q_ref = initial_q(cfg, p, 0.0, align_ankle(cfg, p, 0.0))
    h_td = com_height_over_toe(cfg, q_ref)
    v_x = p["technique.v_x"]
    hurdle_series = None
    if y_td_override is not None:
        y0 = y_td_override
    else:
        if p["technique.start_mode"] == "hurdle":
            c1 = Level1Config.from_params(p)
            c1 = replace(c1, l_td=h_td, board=b, M=M)
            zb0 = p["technique.board_z_hurdle"]
            yh = [zb0 + c1.l_max, math.sqrt(2 * g * p["technique.hurdle_height"]), zb0, p["technique.board_v_hurdle"], 0, 0, 0, 0, 0]
            r = integrate(rhs_free(c1), 0.0, yh, 1e-4, 5.0, [Event("TD", lambda t, y: (y[0] - y[2]) - h_td, -1)], 1e-9)
            if r.event != "TD":
                raise RuntimeError("Kein Touchdown nach Hürde gefunden")
            t_td = r.t[-1]
            events["HTO"] = -t_td
            ytd1 = r.y[-1]
            zb, vb, vz = ytd1[2], ytd1[3], ytd1[1]
            hurdle_series = (np.asarray(r.t) - t_td, np.asarray([y[0] for y in r.y]), np.asarray([y[2] for y in r.y]))
        else:
            zb, vb, vz = p["technique.board_z_td"], p["technique.board_v_td"], -abs(p["technique.v_z_td"])
        q0 = initial_q(cfg, p, zb, align_ankle(cfg, p, zb))
        u0 = np.zeros(NQ)
        u0[7] = p["posture.shoulder_rate"]
        # Ganzkörper translatorisch mit (v_x, v_z); KSP-Geschwindigkeit danach korrigieren (Armschwung)
        cv = G.com(q0, u0, an.p)
        u0[0] = v_x - cv[2]
        u0[1] = vz - cv[3]
        y0 = np.zeros(N_STATE)
        y0[:NQ], y0[NQ:2 * NQ], y0[IDX_ZB], y0[IDX_VB] = q0, u0, zb, vb
    events["TD"] = 0.0
    E0 = mechanical_energy(cfg, y0)

    # --- P4–P6 Kontakt -----------------------------------------------------
    anchors: list[float | None] = [None, None, None]
    _F, _Q, _P, d0 = contact_forces(cfg, y0[:NQ], y0[NQ:2 * NQ], y0[IDX_ZB], y0[IDX_VB], anchors)
    bf0 = board_frame(cfg, y0[IDX_ZB], y0[IDX_VB])
    pts0 = G.points(y0[:NQ], an.p)
    for i in range(3):
        if d0[i] >= -1e-9:
            anchors[i] = -float((np.array(pts0[2 * i:2 * i + 2]) - bf0.tip) @ bf0.t)

    def delta_fn(i):
        def ev(t, y):
            return contact_forces(cfg, y[:NQ], y[NQ:2 * NQ], y[IDX_ZB], y[IDX_VB], [None] * 3)[3][i]
        return ev

    segs: list[Segment] = []
    t, y = 0.0, y0.copy()
    lp_found = False
    took_off = False
    for _it in range(200):
        evs = []
        onset = []
        for i in range(3):
            if anchors[i] is None and G.CONTACTS[i] in cfg.contact_points:
                ev = delta_fn(i)
                ev.terminal, ev.direction = True, 1
                evs.append(ev)
                onset.append(i)
            elif anchors[i] is not None:
                # Kontaktende: Anker freigeben (nicht terminal nötig, aber für sauberen Neustart)
                ev = delta_fn(i)
                ev.terminal, ev.direction = True, -1
                evs.append(ev)
                onset.append(-(i + 1))
        lp = None
        if not lp_found:
            lp = lambda t, y: y[IDX_VB]  # noqa: E731
            lp.terminal, lp.direction = True, 1
            evs.append(lp)
        rhs = make_rhs(cfg, list(anchors))
        sol = solve_ivp(rhs, (t, cfg.t_contact_max), y, method="Radau", rtol=cfg.rtol, atol=cfg.atol,
                        max_step=cfg.max_step, events=evs, dense_output=True)
        if not sol.success:
            warnings.append(f"Integrator: {sol.message}")
            segs.append(Segment(sol, t, sol.t[-1], list(anchors)))
            break
        t_end = sol.t[-1]
        segs.append(Segment(sol, t, t_end, list(anchors)))
        hit = [k for k, te in enumerate(sol.t_events) if len(te) and abs(te[0] - t_end) < 1e-12]
        t, y = t_end, sol.y[:, -1].copy()
        if not hit:
            warnings.append(f"Kein Takeoff innerhalb {cfg.t_contact_max} s.")
            break
        k = hit[0]
        if lp is not None and k == len(evs) - 1:
            lp_found = True
            events["LP"] = t
            continue
        i = onset[k]
        bf = board_frame(cfg, y[IDX_ZB], y[IDX_VB])
        pts = G.points(y[:NQ], an.p)
        if i >= 0:
            anchors[i] = -float((np.array(pts[2 * i:2 * i + 2]) - bf.tip) @ bf.t)
        else:
            anchors[-i - 1] = None
            if all(a is None for a in anchors) and lp_found:
                took_off = True
                break
    if not took_off and "TO" not in events and not warnings:
        warnings.append("Takeoff nicht gefunden.")
    events["TO"] = t
    y_to = y
    t_to = t

    # --- Ergebnisse --------------------------------------------------------
    q_to, u_to = y_to[:NQ], y_to[NQ:2 * NQ]
    cto = G.com(q_to, u_to, an.p)
    H_y, H_seg = angular_momentum_y(cfg, q_to, u_to)
    I_to = inertia_about_com(cfg, q_to)
    H_ref = p["athlete.height"]
    inert = {
        "gestreckt": p["flight.I_layout_ratio"] * M * H_ref ** 2,
        "gehechtet": p["flight.I_pike_ratio"] * M * H_ref ** 2,
        "gehockt": p["flight.I_tuck_ratio"] * M * H_ref ** 2,
    }
    z_entry = -p["board.height_above_water"] + p["technique.entry_offset_ratio"] * H_ref
    fr = flight(cto[1], cto[3], cto[0], cto[2], g, z_entry, H_y=H_y, inertias=inert)

    E_to = mechanical_energy(cfg, y_to)
    acc = dict(zip(ACC, y_to[26:]))
    lhs = E_to - E0
    rhs_bal = acc["W_act"] + acc["W_pas"] + acc["W_c"] - acc["D_w"] - acc["D_b"]
    E_ref = max(abs(E0), abs(E_to), 0.5 * M * (cto[2] ** 2 + cto[3] ** 2), 1.0)
    bal = abs(lhs - rhs_bal) / E_ref
    if bal > 0.005:
        warnings.append(f"Energiebilanz-Abweichung {bal * 100:.2f} % > 0,5 %")

    # Zeitreihen (1 kHz) im Kontakt
    rate = p["numerics.output_rate"]
    tg = np.arange(0, math.floor(t_to * rate) + 1) / rate
    if tg[-1] < t_to:
        tg = np.append(tg, t_to)
    Y = np.empty((len(tg), N_STATE))
    seg_idx = np.empty(len(tg), dtype=int)
    for k, tk in enumerate(tg):
        for si, s in enumerate(segs):
            if s.t0 - 1e-12 <= tk <= s.t1 + 1e-12:
                Y[k] = s.sol.sol(min(max(tk, s.t0), s.t1))
                seg_idx[k] = si
                break
    nt = len(tg)
    F = np.zeros((nt, 6))
    act_t = np.zeros((nt, 6))
    pas_t = np.zeros((nt, 6))
    acts = np.zeros((nt, len(cfg.gens)))
    pts_t = np.zeros((nt, 24))
    com_t = np.zeros((nt, 4))
    Hs = np.zeros((nt, 10))
    E_mech = np.zeros(nt)
    for k in range(nt):
        q, u = Y[k, :NQ], Y[k, NQ:2 * NQ]
        F[k] = contact_forces(cfg, q, u, Y[k, IDX_ZB], Y[k, IDX_VB], segs[seg_idx[k]].anchors)[0]
        act_t[k], pas_t[k] = joint_torques(cfg, tg[k], q[3:9], u[3:9])
        acts[k] = gen_activations(cfg, tg[k])
        pts_t[k] = G.points(q, an.p)
        com_t[k] = G.com(q, u, an.p)
        Hs[k] = angular_momentum_y(cfg, q, u)[1]
        E_mech[k] = mechanical_energy(cfg, Y[k])
    Fz = F[:, 1] + F[:, 3] + F[:, 5]
    Fx = F[:, 0] + F[:, 2] + F[:, 4]
    th = Y[:, 3:9]
    om = Y[:, NQ + 3:NQ + 9]
    tau_net = act_t + pas_t
    power = tau_net * om
    BW = M * g
    zb_t = Y[:, IDX_ZB]

    t_lp = events.get("LP", float("nan"))
    i_lp = int(np.argmin(np.abs(tg - t_lp))) if "LP" in events else nt - 1
    m50 = (tg > 0) & (tg <= 0.05)
    rfd = float(np.max(np.diff(Fz)[m50[1:]] * rate)) if m50[1:].any() else float("nan")
    dep = tg <= t_lp
    W_dep = float(np.trapezoid(np.where(dep, Fz * -Y[:, IDX_VB], 0.0), tg))
    W_rec = float(np.trapezoid(np.where(~dep, Fz * Y[:, IDX_VB], 0.0), tg))

    # Freigang: KSP und Körper beim Passieren der Brettebene (Haltung ab TO eingefroren, ω = H/I)
    t_bp = fr.t_board_plane
    om_fl = -H_y / I_to  # dφ/dt (CCW) im Flug
    pts_to = np.array(G.points(q_to, an.p)).reshape(-1, 2)
    c_to = np.array(cto[:2])

    def body_at(tf):
        ang = om_fl * tf
        R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
        cpos = c_to + np.array(cto[2:]) * tf + np.array([0, -0.5 * g * tf * tf])
        return (pts_to - c_to) @ R.T + cpos

    body_bp = body_at(t_bp) if t_bp > 0 else pts_to
    x_body_min = float(np.min(body_bp[:, 0]))

    deg = 180 / math.pi
    metrics: dict[str, Any] = {
        "board_k_s": b.k_s, "board_m_b": b.m_b, "board_f0": b.f0, "board_f_loaded": b.f_loaded(M),
        "board_phase_td_deg": board_phase_deg(y0[IDX_ZB], y0[IDX_VB], b.omega0) if (y0[IDX_ZB] or y0[IDX_VB]) else float("nan"),
        "hurdle_flight_time": -events["HTO"] if "HTO" in events else None,
        "v_z_td": float(com_t[0, 3]), "v_x_td": float(com_t[0, 2]), "v_b_td": float(y0[IDX_VB]),
        "v_rel_td": float(com_t[0, 3] - y0[IDX_VB]),
        "z_b_min": float(np.min(zb_t)), "v_b_min": float(np.min(Y[:, IDX_VB])),
        "v_z_lp": float(com_t[i_lp, 3]), "z_c_lp": float(com_t[i_lp, 1]),
        "v_z_to": float(cto[3]), "v_x_to": float(cto[2]), "z_c_to": float(cto[1]), "z_b_to": float(y_to[IDX_ZB]),
        "v_b_to": float(y_to[IDX_VB]), "takeoff_angle_deg": math.degrees(math.atan2(cto[3], cto[2])),
        "F_peak": float(Fz.max()), "F_peak_bw": float(Fz.max() / BW), "t_F_peak": float(tg[int(np.argmax(Fz))]),
        "F_mean_bw": float(np.trapezoid(Fz, tg) / max(t_to, 1e-9) / BW),
        "F_impact_bw": float(Fz[tg <= 0.03].max() / BW),
        "F_active_peak_bw": float(Fz[tg > 0.03].max() / BW) if (tg > 0.03).any() else float("nan"),
        "Fx_peak_bw": float(Fx[np.argmax(np.abs(Fx))] / BW),
        "board_spring_force_max": float(b.k_s * -np.min(zb_t)), "rfd_max": rfd,
        "impulse_z": float(acc["J_z"]), "impulse_x": float(acc["J_x"]),
        "impulse_dep": float(np.trapezoid(np.where(dep, Fz, 0), tg)), "impulse_rec": float(np.trapezoid(np.where(~dep, Fz, 0), tg)),
        "t_depression": t_lp, "t_recoil": t_to - t_lp, "t_contact": t_to, "t_flight": fr.t_water, "t_apex": fr.t_apex,
        "h_max_board": fr.z_apex, "h_max_water": fr.z_apex + p["board.height_above_water"], "h_rise": fr.h_rise,
        "x_board_plane": fr.x_board_plane, "x_body_board_plane": x_body_min, "x_water": fr.x_water, "z_entry": z_entry,
        "E_kin_to": float(G.energy(q_to, u_to, an.p)[0]), "E_board_max": 0.5 * b.k_s * float(np.min(zb_t)) ** 2,
        "W_act": acc["W_act"], "W_act_per_kg": acc["W_act"] / M, "W_pas": acc["W_pas"], "W_contact": acc["W_c"],
        "D_leg": acc["D_w"], "D_board": acc["D_b"],
        "W_athlete_to_board": W_dep, "W_board_to_athlete": W_rec, "board_efficiency": W_rec / W_dep if W_dep > 0 else float("nan"),
        "energy_balance_rel": bal,
        "leg_power_peak": float(np.max(power[:, :4].sum(1))), "leg_power_peak_per_kg": float(np.max(power[:, :4].sum(1)) / M),
        "H_y": H_y, "I_to": I_to, "rotation_potential": fr.rotation_potential,
        "somersaults_layout": fr.somersaults["gestreckt"], "somersaults_pike": fr.somersaults["gehechtet"], "somersaults_tuck": fr.somersaults["gehockt"],
    }
    for j, name in enumerate(JOINTS):
        metrics[f"{name}_angle_td_deg"] = float(th[0, j] * deg)
        metrics[f"{name}_angle_lp_deg"] = float(th[i_lp, j] * deg)
        metrics[f"{name}_angle_to_deg"] = float(th[-1, j] * deg)
        metrics[f"{name}_angle_max_deg"] = float(th[:, j].max() * deg)
        metrics[f"{name}_torque_peak"] = float(tau_net[np.argmax(np.abs(tau_net[:, j])), j])
        metrics[f"{name}_power_peak"] = float(power[:, j].max())
        metrics[f"{name}_work_pos"] = float(np.trapezoid(np.clip(power[:, j], 0, None), tg))
        metrics[f"{name}_work_neg"] = float(np.trapezoid(np.clip(power[:, j], None, 0), tg))
        metrics[f"{name}_omega_to"] = float(om[-1, j])
    # Zeitpunkt maximaler Knie-/Hüftbeugung nach TD (SPEC 9.2: Flexion bis ~100 ms)
    metrics["t_knee_flex_max"] = float(tg[int(np.argmax(th[:, 2]))])
    metrics["t_hip_flex_max"] = float(tg[int(np.argmax(th[:, 3]))])

    out_series: dict[str, np.ndarray] = {}
    if series:
        out_series = {
            "t": tg, "Fz": Fz, "Fx": Fx, "F_points": F, "z_b": zb_t, "v_b": Y[:, IDX_VB],
            "com": com_t, "theta": th, "omega": om, "tau_act": act_t, "tau_pas": pas_t, "tau_net": tau_net,
            "power": power, "act": acts, "points": pts_t, "H_seg": Hs, "E_mech": E_mech, "wobble": Y[:, 9:12],
            "acc": Y[:, 26:],
        }
        # Flug (1 kHz), Haltung eingefroren
        tf = np.arange(1, math.floor(fr.t_water * rate) + 1) / rate
        fl_pts = np.array([body_at(x).ravel() for x in tf]) if len(tf) else np.zeros((0, 24))
        cx = cto[0] + cto[2] * tf
        cz = cto[1] + cto[3] * tf - 0.5 * g * tf * tf
        out_series["flight_t"] = t_to + tf
        out_series["flight_points"] = fl_pts
        out_series["flight_com"] = np.stack([cx, cz], 1) if len(tf) else np.zeros((0, 2))
        # Brett nach TO frei weiter
        rp = integrate(rhs_free(replace(Level1Config.from_params(p), board=b)), t_to, [0, 0, y_to[IDX_ZB], y_to[IDX_VB], 0, 0, 0, 0, 0], 1e-4, t_to + fr.t_water)
        out_series["flight_z_b"] = np.interp(t_to + tf, rp.t, [yy[2] for yy in rp.y]) if len(tf) else np.zeros(0)
        if hurdle_series is not None:
            th_, zc_, zb_ = hurdle_series
            hg = np.arange(math.ceil(th_[0] * rate), 0) / rate
            out_series["hurdle_t"] = hg
            out_series["hurdle_com_z"] = np.interp(hg, th_, zc_)
            out_series["hurdle_z_b"] = np.interp(hg, th_, zb_)
            out_series["hurdle_offset"] = np.array([h_td])
    return Level2Result(events=events, metrics=metrics, series=out_series, warnings=warnings)
