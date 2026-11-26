"""Athletenmodell Level 2: Segmentparameter aus Körpergröße, -masse und Geschlecht
(SPEC 5.1, 5.5). Grundlage: de Leva (1996), data/anthropometry_de_leva.json.

Beide Körperhälften sind in der Sagittalebene zusammengefasst (Massen und Trägheiten ×2
für Extremitäten). Rumpf und Kopf bilden einen starren Körper (Hals gesperrt).
Die Schwabbelmasse ist eine Punktmasse auf der Segmentachse am Segmentschwerpunkt; das
Segment-Trägheitsmoment bleibt vollständig beim starren Anteil (Vereinfachung, siehe
docs/validation/model-notes.md).

Einheiten: m, kg, kg m².
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .models.level2_generated import PARAM_NAMES
from .params import DATA_DIR, ParamSet

# Referenz-Schwabbelmassen des Elite-Springers (Kong, Yeadon & King) für die k_w-Skalierung
WOBBLE_REF_MASS = {"shank": 6.03, "thigh": 16.74, "trunk": 21.86}


def load_de_leva() -> dict:
    with open(DATA_DIR / "anthropometry_de_leva.json", encoding="utf-8") as fh:
        return json.load(fh)


@dataclass(frozen=True)
class Anthropometry:
    """Abgeleitete Segmentparameter. ``p`` ist der Parametervektor für level2_generated."""

    p: tuple[float, ...]
    named: dict[str, float]
    wobble_k: dict[str, float]  # N/m³
    wobble_c: dict[str, float]  # N s/m
    total_mass: float

    def __getitem__(self, k: str) -> float:
        return self.named[k]


def build_anthropometry(ps: ParamSet) -> Anthropometry:
    dl = load_de_leva()
    sex = ps["athlete.sex"]
    H = ps["athlete.height"]
    M = ps["athlete.mass"]
    scale = H / (dl["_meta"]["reference_stature_mm"][sex] / 1000.0)
    S = dl["segments"]

    def L(seg):
        return S[seg]["length_mm"][sex] / 1000.0 * scale

    def m(seg, both=True):
        return S[seg]["mass_pct"][sex] / 100.0 * M * (2 if both else 1)

    def com(seg):
        return S[seg]["com_pct_from_origin"][sex] / 100.0

    def rs(seg):
        return S[seg]["r_sagittal_pct"][sex] / 100.0

    n: dict[str, float] = {"g": ps["numerics.g"]}

    # --- Fuß (zweiteilig) -------------------------------------------------
    Lf = L("foot")
    r_mtp = ps["body.foot_mtp_ratio"]
    r_ax = ps["body.foot_ankle_x_ratio"]
    h_a = ps["body.ankle_height_ratio"] * H
    m_foot = m("foot")
    m_toe = ps["body.toes_mass_ratio"] * m_foot
    m_rf = m_foot - m_toe
    n["L_toe"] = Lf * (1 - r_mtp)
    dx = (r_mtp - r_ax) * Lf
    n["L_rf"] = math.hypot(dx, h_a)
    n["alpha_f"] = math.atan2(h_a, dx)
    n["L_heel"] = r_mtp * Lf
    n["m_toe"] = m_toe
    n["c_toe"] = n["L_toe"] / 2
    n["I_toe"] = m_toe * n["L_toe"] ** 2 / 12
    # Fuß-KSP (de Leva, auf der Linie Ferse–Zehenspitze); Rückfuß-KSP so, dass der Gesamt-KSP stimmt
    x_cm = com("foot") * Lf
    x_toe = Lf - n["L_toe"] / 2
    x_rf = (m_foot * x_cm - m_toe * x_toe) / m_rf
    z_rf = 0.4 * h_a  # Schätzung: Rückfuß-KSP oberhalb der Sohle
    a = n["alpha_f"]
    d = (x_rf - r_mtp * Lf, z_rf)
    e_ax = (-math.cos(a), math.sin(a))
    e_perp = (-math.sin(a), -math.cos(a))
    n["m_rf"] = m_rf
    n["r_rf_a"] = d[0] * e_ax[0] + d[1] * e_ax[1]
    n["r_rf_b"] = d[0] * e_perp[0] + d[1] * e_perp[1]
    n["I_rf"] = m_rf * (rs("foot") * Lf) ** 2

    # --- Unterschenkel, Oberschenkel mit Schwabbelmasse ---------------------
    for key, seg, ratio_key in (("sh", "shank", "wobble.shank_ratio"), ("th", "thigh", "wobble.thigh_ratio")):
        Ls = L(seg)
        mt = m(seg)
        r = ps[ratio_key]
        n[f"L_{key}"] = Ls
        n[f"m_{key}"] = mt * (1 - r)
        n[f"m_{key}w"] = mt * r
        n[f"c_{key}"] = Ls * (1 - com(seg))  # ab distalem Gelenk
        n[f"I_{key}"] = mt * (rs(seg) * Ls) ** 2

    # --- Rumpf + Kopf ---------------------------------------------------------
    Ltr = L("trunk")
    Lh = L("head")
    m_trunk = m("trunk", both=False)
    m_head = m("head", both=False)
    r = ps["wobble.trunk_ratio"]
    c_trunk = Ltr * (1 - com("trunk"))  # ab Hüfte (MIDH)
    c_head = Ltr + Lh * (1 - com("head"))
    m_rig = (1 - r) * m_trunk + m_head
    c_tr = ((1 - r) * m_trunk * c_trunk + m_head * c_head) / m_rig
    I_trunk = m_trunk * (rs("trunk") * Ltr) ** 2
    I_head = m_head * (rs("head") * Lh) ** 2
    n.update({
        "L_tr": Ltr, "L_sho": ps["body.shoulder_ratio"] * Ltr, "L_head": Lh,
        "m_tr": m_rig, "c_tr": c_tr, "c_trw": c_trunk, "m_trw": r * m_trunk,
        "I_tr": I_trunk + (1 - r) * m_trunk * (c_trunk - c_tr) ** 2 + I_head + m_head * (c_head - c_tr) ** 2,
    })

    # --- Arme ----------------------------------------------------------------
    Lua = L("upperarm")
    n.update({"L_ua": Lua, "m_ua": m("upperarm"), "c_ua": com("upperarm") * Lua, "I_ua": m("upperarm") * (rs("upperarm") * Lua) ** 2})
    Lfa, Lha = L("forearm"), L("hand")
    mfa, mha = m("forearm"), m("hand")
    cfa, cha = com("forearm") * Lfa, Lfa + com("hand") * Lha
    mt = mfa + mha
    c = (mfa * cfa + mha * cha) / mt
    n.update({
        "L_fa": Lfa, "L_hand": Lha, "m_fa": mt, "c_fa": c,
        "I_fa": mfa * (rs("forearm") * Lfa) ** 2 + mfa * (cfa - c) ** 2 + mha * (rs("hand") * Lha) ** 2 + mha * (cha - c) ** 2,
    })

    total = sum(n[k] for k in ("m_toe", "m_rf", "m_sh", "m_shw", "m_th", "m_thw", "m_tr", "m_trw", "m_ua", "m_fa"))
    scale_w = ps["wobble.scale_k_with_mass"] == "ja"
    wk, wc = {}, {}
    for seg, mk in (("shank", "m_shw"), ("thigh", "m_thw"), ("trunk", "m_trw")):
        f = n[mk] / WOBBLE_REF_MASS[seg] if scale_w else 1.0
        wk[seg] = ps[f"wobble.{seg}_k"] * f
        wc[seg] = ps[f"wobble.{seg}_c"] * f
    return Anthropometry(p=tuple(n[k] for k in PARAM_NAMES), named=n, wobble_k=wk, wobble_c=wc, total_mass=total)
