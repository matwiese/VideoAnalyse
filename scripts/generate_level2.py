"""Erzeugt die Bewegungsgleichungen des planaren Level-2-Modells symbolisch
(SymPy, sympy.physics.mechanics, Kane-Methode) und schreibt sie als Python-Code nach
core/models/level2_generated.py (SPEC 6.2, CLAUDE.md: nie von Hand abtippen).

Aufruf (Repo-Root):  python -m scripts.generate_level2

Modell (Sagittalebene x–z, beide Körperhälften zusammengefasst):
  Segmente  Zehen, Rückfuß, Unterschenkel, Oberschenkel, Rumpf+Kopf, Oberarm, Unterarm+Hand
  Schwabbelmassen  Unterschenkel, Oberschenkel, Rumpf (je 1 FG entlang der Segmentachse)
  Generalisierte Koordinaten (12):
    q0 x, q1 z      Zehenspitze [m]
    q2 φ_toe        absoluter Winkel Zehenspitze→MTP [rad] (π = Zehen flach, nach vorn)
    q3 θ_MTP        Dorsalflexion Zehen (Ferse hebt) [rad]
    q4 θ_ankle      Dorsalflexion [rad]
    q5 θ_knee       Flexion [rad]
    q6 θ_hip        Flexion [rad]
    q7 θ_shoulder   Flexion (Arm nach vorn/oben) [rad]
    q8 θ_elbow      Flexion [rad]
    q9..q11 w_trunk, w_thigh, w_shank  Schwabbelmassen-Verschiebung [m]
Winkelkonvention: e(φ) = (cos φ, sin φ), φ gegen den Uhrzeigersinn von +x nach +z.
Gelenkmomente τ_j sind generalisierte Kräfte der θ_j (τ > 0 wirkt in +θ-Richtung).
"""
from __future__ import annotations

import time
from pathlib import Path

import sympy as sp
import sympy.physics.mechanics as me

OUT = Path(__file__).resolve().parent.parent / "core" / "models" / "level2_generated.py"

PARAM_NAMES = [
    "g", "L_toe", "L_rf", "alpha_f", "L_heel", "L_sh", "L_th", "L_tr", "L_sho", "L_head", "L_ua", "L_fa", "L_hand",
    "m_toe", "c_toe", "I_toe",
    "m_rf", "r_rf_a", "r_rf_b", "I_rf",
    "m_sh", "m_shw", "c_sh", "I_sh",
    "m_th", "m_thw", "c_th", "I_th",
    "m_tr", "c_tr", "c_trw", "m_trw", "I_tr",
    "m_ua", "c_ua", "I_ua",
    "m_fa", "c_fa", "I_fa",
]
JOINTS = ["mtp", "ankle", "knee", "hip", "shoulder", "elbow"]
CONTACTS = ["toe", "ball", "heel"]


def build():
    t0 = time.time()
    P = dict(zip(PARAM_NAMES, sp.symbols(PARAM_NAMES, real=True)))
    q = me.dynamicsymbols("q0:12")
    u = me.dynamicsymbols("u0:12")
    tau = sp.symbols("tau_mtp tau_ankle tau_knee tau_hip tau_shoulder tau_elbow", real=True)
    Fc = sp.symbols("Fx_toe Fz_toe Fx_ball Fz_ball Fx_heel Fz_heel", real=True)
    Fw = sp.symbols("Fw_trunk Fw_thigh Fw_shank", real=True)
    x, z, phi_t, th_mtp, th_ank, th_kn, th_hip, th_sh, th_el, w_tr, w_th, w_sh = q

    N = me.ReferenceFrame("N")
    O = me.Point("O")
    O.set_vel(N, 0)

    a_f = P["alpha_f"]
    phi = {
        "toe": phi_t,
        "rf": phi_t - a_f - th_mtp,
    }
    phi["sh"] = phi["rf"] - (sp.pi / 2 - a_f) - th_ank
    phi["th"] = phi["sh"] + th_kn
    phi["tr"] = phi["th"] - th_hip
    phi["ua"] = phi["tr"] - sp.pi + th_sh
    phi["fa"] = phi["ua"] + th_el
    # Vorzeichen s_j = ∂φ_child/∂θ_j und Eltern/Kind je Gelenk
    joint_pairs = {"mtp": ("toe", "rf", -1), "ankle": ("rf", "sh", -1), "knee": ("sh", "th", 1),
                   "hip": ("th", "tr", -1), "shoulder": ("tr", "ua", 1), "elbow": ("ua", "fa", 1)}

    F = {}
    for k, ang in phi.items():
        Fr = me.ReferenceFrame(f"B_{k}")
        Fr.orient_axis(N, N.y, -ang)  # B.x = e(φ) in der x–z-Ebene
        F[k] = Fr

    def e(ang):
        return sp.cos(ang) * N.x + sp.sin(ang) * N.z

    pos = {}
    pos["toe"] = x * N.x + z * N.z
    pos["ball"] = pos["toe"] + P["L_toe"] * e(phi["toe"])
    pos["ankle"] = pos["ball"] + P["L_rf"] * e(phi["rf"])
    pos["heel"] = pos["ball"] + P["L_heel"] * e(phi["rf"] + a_f)
    pos["knee"] = pos["ankle"] + P["L_sh"] * e(phi["sh"])
    pos["hip"] = pos["knee"] + P["L_th"] * e(phi["th"])
    pos["shoulder"] = pos["hip"] + P["L_sho"] * e(phi["tr"])
    pos["neck"] = pos["hip"] + P["L_tr"] * e(phi["tr"])
    pos["vertex"] = pos["neck"] + P["L_head"] * e(phi["tr"])
    pos["elbow"] = pos["shoulder"] + P["L_ua"] * e(phi["ua"])
    pos["wrist"] = pos["elbow"] + P["L_fa"] * e(phi["fa"])
    pos["fingertip"] = pos["wrist"] + P["L_hand"] * e(phi["fa"])

    com = {
        "toe": (pos["toe"] + P["c_toe"] * e(phi["toe"]), P["m_toe"], P["I_toe"], "toe"),
        "rf": (pos["ball"] + P["r_rf_a"] * e(phi["rf"]) + P["r_rf_b"] * e(phi["rf"] + sp.pi / 2), P["m_rf"], P["I_rf"], "rf"),
        "sh": (pos["ankle"] + P["c_sh"] * e(phi["sh"]), P["m_sh"], P["I_sh"], "sh"),
        "th": (pos["knee"] + P["c_th"] * e(phi["th"]), P["m_th"], P["I_th"], "th"),
        "tr": (pos["hip"] + P["c_tr"] * e(phi["tr"]), P["m_tr"], P["I_tr"], "tr"),
        "ua": (pos["shoulder"] + P["c_ua"] * e(phi["ua"]), P["m_ua"], P["I_ua"], "ua"),
        "fa": (pos["elbow"] + P["c_fa"] * e(phi["fa"]), P["m_fa"], P["I_fa"], "fa"),
    }
    wob_base = {
        "trunk": (pos["hip"] + P["c_trw"] * e(phi["tr"]), w_tr, P["m_trw"], "tr", Fw[0]),
        "thigh": (pos["knee"] + P["c_th"] * e(phi["th"]), w_th, P["m_thw"], "th", Fw[1]),
        "shank": (pos["ankle"] + P["c_sh"] * e(phi["sh"]), w_sh, P["m_shw"], "sh", Fw[2]),
    }

    qd_map = dict(zip([qi.diff() for qi in q], u))

    def mk_point(name, vec):
        pt = me.Point(name)
        pt.set_pos(O, vec)
        pt.set_vel(N, vec.dt(N).subs(qd_map))
        return pt

    bodies, loads = [], []
    g = P["g"]
    for k, (vec, m, I, fr) in com.items():
        pt = mk_point(f"P_{k}", vec)
        F[fr].set_ang_vel(N, F[fr].ang_vel_in(N).subs(qd_map))
        rb = me.RigidBody(f"RB_{k}", pt, F[fr], m, (me.inertia(F[fr], I, I, I), pt))
        bodies.append(rb)
        loads.append((pt, -m * g * N.z))
    for k, (base, w, m, fr, fw) in wob_base.items():
        bpt = mk_point(f"WB_{k}", base)
        wpt = mk_point(f"W_{k}", base + w * e(phi[fr]))
        bodies.append(me.Particle(f"PW_{k}", wpt, m))
        loads.append((wpt, -m * g * N.z))
        loads.append((wpt, fw * e(phi[fr])))
        loads.append((bpt, -fw * e(phi[fr])))
    for j, (par, chi) in ((j, joint_pairs[j][:2]) for j in JOINTS):
        s = joint_pairs[j][2]
        tj = tau[JOINTS.index(j)]
        loads.append((F[chi], s * tj * (-N.y)))
        loads.append((F[par], -s * tj * (-N.y)))
    for i, c in enumerate(CONTACTS):
        cpt = mk_point(f"C_{c}", pos[c])
        loads.append((cpt, Fc[2 * i] * N.x + Fc[2 * i + 1] * N.z))

    kd = [qi.diff() - ui for qi, ui in zip(q, u)]
    KM = me.KanesMethod(N, q_ind=q, u_ind=u, kd_eqs=kd)
    KM.kanes_equations(bodies, loads)
    Mm = KM.mass_matrix
    fo = KM.forcing
    print(f"Kane fertig in {time.time() - t0:.1f} s")

    # Kinematik: Punkte, Kontaktgeschwindigkeiten, KSP, Drehimpuls
    qs = sp.symbols("q0:12", real=True)
    us = sp.symbols("u0:12", real=True)
    to_plain = {**dict(zip(q, qs)), **dict(zip(u, us))}

    def xz(vec):
        return [vec.dot(N.x), vec.dot(N.z)]

    point_names = ["toe", "ball", "heel", "ankle", "knee", "hip", "shoulder", "neck", "vertex", "elbow", "wrist", "fingertip"]
    pts = sum((xz(pos[n]) for n in point_names), [])
    cvel = sum((xz(pos[c].dt(N).subs(qd_map)) for c in CONTACTS), [])
    masses = [m for (_v, m, _I, _f) in com.values()] + [m for (_b, _w, m, _f, _fw) in wob_base.values()]
    mpos = [v for (v, _m, _I, _f) in com.values()] + [b + w * e(phi[f]) for (b, w, _m, f, _fw) in wob_base.values()]
    M_tot = sum(masses)
    rc = sum((m * r for m, r in zip(masses, mpos)), sp.S(0) * N.x) / M_tot
    vc = rc.dt(N).subs(qd_map)
    H = 0
    seg_H = []
    for (v, m, I, fr) in com.values():
        rv = v - rc
        vv = v.dt(N).subs(qd_map)
        ang_rate = sp.diff(phi[fr], me.dynamicsymbols._t).subs(qd_map)
        hk = m * (rv.dot(N.x) * vv.dot(N.z) - rv.dot(N.z) * vv.dot(N.x)) + I * ang_rate
        seg_H.append(hk)
    for (b, w, m, f, _fw) in wob_base.values():
        r = b + w * e(phi[f])
        rv = r - rc
        vv = r.dt(N).subs(qd_map)
        seg_H.append(m * (rv.dot(N.x) * vv.dot(N.z) - rv.dot(N.z) * vv.dot(N.x)))
    seg_names = list(com.keys()) + [f"w_{k}" for k in wob_base]
    # Kinetische und potenzielle Energie (Kontrolle der Bilanz)
    KE = 0
    PE = 0
    for (v, m, I, fr) in com.values():
        vv = v.dt(N).subs(qd_map)
        KE += m * vv.dot(vv) / 2 + I * sp.diff(phi[fr], me.dynamicsymbols._t).subs(qd_map) ** 2 / 2
        PE += m * g * v.dot(N.z)
    for (b, w, m, f, _fw) in wob_base.values():
        r = b + w * e(phi[f])
        vv = r.dt(N).subs(qd_map)
        KE += m * vv.dot(vv) / 2
        PE += m * g * r.dot(N.z)
    angles = [phi[k] for k in ["toe", "rf", "sh", "th", "tr", "ua", "fa"]]

    out = {
        "mass_matrix": (list(Mm.subs(to_plain)), "q"),
        "forcing": (list(fo.subs(to_plain)), "qu_tau_F"),
        "points": ([sp.sympify(e_).subs(to_plain) for e_ in pts], "q"),
        "contact_velocities": ([sp.sympify(e_).subs(to_plain) for e_ in cvel], "qu"),
        "com": ([rc.dot(N.x).subs(to_plain), rc.dot(N.z).subs(to_plain), vc.dot(N.x).subs(to_plain), vc.dot(N.z).subs(to_plain)], "qu"),
        "segment_momentum": ([h.subs(to_plain) for h in seg_H], "qu"),
        "energy": ([KE.subs(to_plain), PE.subs(to_plain)], "qu"),
        "segment_angles": ([a.subs(to_plain) for a in angles], "q"),
        "segment_coms": ([c_.subs(to_plain) for r_ in mpos for c_ in xz(r_)], "q"),
    }
    return out, qs, us, tau, Fc, Fw, P, point_names, seg_names


def emit(out, qs, us, tau, Fc, Fw, P, point_names, seg_names) -> str:
    from sympy.printing.pycode import PythonCodePrinter

    pr = PythonCodePrinter({"fully_qualified_modules": False, "standard": "python3"})
    lines = [
        '"""AUTOMATISCH ERZEUGT von scripts/generate_level2.py (SymPy, Kane-Methode). Nicht von Hand ändern."""',
        "# flake8: noqa",
        "from math import cos, sin, pi",
        "",
        f"PARAM_NAMES = {PARAM_NAMES!r}",
        f"JOINTS = {JOINTS!r}",
        f"CONTACTS = {CONTACTS!r}",
        f"POINT_NAMES = {point_names!r}",
        f"SEGMENT_NAMES = {seg_names!r}",
        "MASS_PARAMS = ['m_toe', 'm_rf', 'm_sh', 'm_th', 'm_tr', 'm_ua', 'm_fa', 'm_trw', 'm_thw', 'm_shw']",
        "INERTIA_PARAMS = ['I_toe', 'I_rf', 'I_sh', 'I_th', 'I_tr', 'I_ua', 'I_fa', None, None, None]",
        "N_Q = 12",
        "",
    ]
    sig = {
        "q": "q, p",
        "qu": "q, u, p",
        "qu_tau_F": "q, u, p, tau, Fc, Fw",
    }
    for name, (exprs, kind) in out.items():
        repl, reduced = sp.cse(exprs, symbols=sp.numbered_symbols("x"), optimizations="basic")
        lines.append(f"def {name}({sig[kind]}):")
        lines.append(f"    {', '.join(str(s) for s in qs)}, = q")
        if "u" in kind:
            lines.append(f"    {', '.join(str(s) for s in us)}, = u")
        lines.append(f"    {', '.join(PARAM_NAMES)}, = p")
        if "tau" in kind:
            lines.append(f"    {', '.join(str(s) for s in tau)}, = tau")
            lines.append(f"    {', '.join(str(s) for s in Fc)}, = Fc")
            lines.append(f"    {', '.join(str(s) for s in Fw)}, = Fw")
        for s, ex in repl:
            lines.append(f"    {s} = {pr.doprint(ex)}")
        lines.append("    return [" + ", ".join(pr.doprint(ex) for ex in reduced) + "]")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    t0 = time.time()
    res = build()
    code = emit(*res)
    OUT.write_text(code)
    print(f"geschrieben: {OUT} ({len(code) / 1024:.0f} kB) in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
