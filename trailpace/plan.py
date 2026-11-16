"""Moteur de plan de course : intègre le temps point par point le long de la trace.

Vitesse en un point = vitesse mesurée de l'athlète pour cette pente (à ~75 % de sa vitesse critique)
x effort demandé x technicité x altitude x nuit x chaleur x fatigue.
"""
import math
from datetime import datetime, timedelta

import numpy as np

from .profile import minetti_cost

# --- paramètres issus de la littérature (voir notes dans l'interface) ---
ALT_LOSS_PER_KM = 0.063   # perte de VO2max par 1000 m (Wehrlin & Hallén 2006, J Appl Physiol / Eur J Appl Physiol)
HEAT_START_C = 8.0        # température (°C) à partir de laquelle on ralentit (Ely 2007 : ralentissement progressif dès WBGT 5-10 °C)
DESCENT_ELASTICITY = 0.5  # en descente, la vitesse varie moins que l'effort (freinage, technique)
TECH_REF = 1.05           # technicité moyenne supposée de l'entraînement de l'athlète


def recommended_pct(hours):
    """% de la vitesse critique tenable en moyenne selon la durée (heuristique à calibrer, pas une loi publiée)."""
    return float(np.clip(0.97 - 0.12 * math.log(max(hours, 0.5)), 0.5, 1.0))


class SpeedTable:
    """Vitesse (m/s) de l'athlète par pente, interpolée sur ses mesures sous-maximales."""

    def __init__(self, grade_profile, cs_kmh, cp_w=None):
        rows = [r for r in grade_profile if r.get("speed_kmh")]
        rows.sort(key=lambda r: r["grade_med"])
        self.g = np.array([r["grade_med"] for r in rows])
        self.v = np.array([r["speed_kmh"] for r in rows]) / 3.6
        flat = min(rows, key=lambda r: abs(r["grade_med"]))
        self.pct_ref = flat["speed_kmh"] / cs_kmh      # fraction de CS correspondant à ces mesures
        self.flat_hr = flat["hr"]
        # puissance : mesurée par pente à l'effort de référence, mise à l'échelle entre cet effort et la CP
        prow = [r for r in rows if r.get("power")]
        self.has_power = bool(cp_w) and len(prow) >= 4 and bool(flat.get("power")) and cp_w > flat["power"]
        if self.has_power:
            self.pg = np.array([r["grade_med"] for r in prow])
            self.p = np.array([r["power"] for r in prow], dtype=float)
            self.p_flat, self.cp = float(flat["power"]), float(cp_w)

    def power(self, grade_pct, pct):
        """Puissance cible (W) sur une pente donnée pour un effort pct (fraction de la vitesse critique)."""
        scale = 1 + (self.cp / self.p_flat - 1) * (pct - self.pct_ref) / (1 - self.pct_ref)
        return float(np.interp(grade_pct, self.pg, self.p)) * max(0.3, scale)

    def speed(self, grade_pct):
        if grade_pct <= self.g[0]:      # plus raide que les mesures : on garde la vitesse mesurée la plus proche
            return float(self.v[0])
        if grade_pct >= self.g[-1]:     # montée plus raide que les mesures : extrapolation Minetti
            return float(self.v[-1] * minetti_cost(self.g[-1] / 100) / minetti_cost(min(grade_pct, 45) / 100))
        return float(np.interp(grade_pct, self.g, self.v))


def night_bump(clock):
    """0..1, maximum vers 4h30 du matin, nul avant minuit et après 9h (rythme circadien, hypothèse)."""
    h = clock.hour + clock.minute / 60
    d = ((h - 4.5 + 12) % 24) - 12
    return max(0.0, math.cos(math.pi * d / 9)) if abs(d) < 4.5 else 0.0


def simulate(course, table, params, weather=None, ref_alt=None):
    """Retourne résultats par point et par section.

    course: dict avec grid_m, ele, grade, tech (facteur par point), aid_km (liste), section bounds
    params: pct (départ, fraction de CS), aggr (-1..1), climb (-0.1..0.1), descent (-0.1..0.1), drift_pct_h,
            tech_sens, night_pen_pct, heat_sens_pct, alt_sens (0..1), stops_min (liste par ravito), start (datetime)
    """
    grid, grade, tech, ele = course["grid_m"], course["grade"], course["tech"], course["ele"]
    total = grid[-1]
    start = params["start"]
    stops = dict(zip([round(k, 3) for k in course["aid_km"]], params["stops_min"]))
    aid_km = list(course["aid_km"])
    nxt = 0

    t = 0.0   # secondes écoulées
    times = np.zeros(len(grid))
    speeds = np.zeros(len(grid))
    mults = np.zeros(len(grid))
    powers = np.zeros(len(grid))      # puissance cible (W) en chaque point
    dts = np.zeros(len(grid))         # temps de déplacement (s) du pas, arrêts exclus
    stop_total = 0.0
    arrive_aid = {}
    for i in range(1, len(grid)):
        d = grid[i] - grid[i - 1]
        g = float(grade[i])
        x = grid[i] / total
        # effort demandé (fraction de CS) : départ plus rapide ou progressif
        pct = params["pct"] * (1 + 0.06 * params["aggr"] * (1 - 2 * x))
        e = DESCENT_ELASTICITY if g < -3 else 1.0
        eff = (pct / table.pct_ref) ** e
        if g > 3:
            eff *= 1 + params["climb"]
        elif g < -3:
            eff *= 1 + params["descent"]
        v = table.speed(g) * eff
        # technicité relative à l'entraînement (plus marquée en descente)
        tf = max(tech[i], 1.0) / TECH_REF
        v /= tf ** (params["tech_sens"] * (1.5 if g < -3 else 1.0))
        # altitude relative à l'altitude d'entraînement
        if ref_alt is not None and params["alt_sens"] > 0:
            dalt = (ele[i] - ref_alt) / 1000
            v *= 1 - float(np.clip(ALT_LOSS_PER_KM * dalt * params["alt_sens"], -0.05, 0.08))
        clock = start + timedelta(seconds=t)
        v *= 1 - params["night_pen_pct"] / 100 * night_bump(clock)
        if weather is not None:
            temp = weather(grid[i], clock)
            if temp is not None and temp > HEAT_START_C:
                v *= 1 - params["heat_sens_pct"] / 100 * (temp - HEAT_START_C)
        # fatigue : perte linéaire par heure après la 1re heure
        hrs = t / 3600
        v *= max(0.55, 1 - params["drift_pct_h"] / 100 * max(0.0, hrs - 1))
        v = max(v, 0.3)
        if table.has_power:       # l'effort visé (donc la puissance) n'est pas réduit par la fatigue : c'est la vitesse qui baisse
            powers[i] = table.power(g, pct) * ((1 + params["climb"]) if g > 3 else 1.0)
        dts[i] = d / v
        t += d / v
        times[i] = t
        speeds[i] = v
        mults[i] = v / table.speed(g)
        while nxt < len(aid_km) and grid[i] >= aid_km[nxt] * 1000:
            m = stops.get(round(aid_km[nxt], 3), 0.0)
            t += m * 60
            stop_total += m * 60
            arrive_aid[nxt] = (times[i], t)
            nxt += 1
        times[i] = t
    speeds[0] = speeds[1]
    powers[0] = powers[1]
    return {"t": times, "v": speeds, "p": powers, "dt": dts, "total_s": t, "stop_s": stop_total, "arrive_aid": arrive_aid}


def solve_pct(course, table, params, target_s, **kw):
    """Cherche la fraction de CS de départ pour finir en target_s (bissection)."""
    lo, hi = 0.30, 1.10
    for _ in range(30):
        mid = (lo + hi) / 2
        res = simulate(course, table, {**params, "pct": mid}, **kw)
        if res["total_s"] > target_s:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def hr_target(pct, table, hr_cs):
    """FC attendue par interpolation entre FC à l'effort de référence et FC à la vitesse critique."""
    if hr_cs is None:
        return None
    frac = (pct - table.pct_ref) / (1.0 - table.pct_ref)
    return table.flat_hr + (hr_cs - table.flat_hr) * frac


def fmt_hm(s):
    s = int(round(s))
    return f"{s // 3600}h{(s % 3600) // 60:02d}"
