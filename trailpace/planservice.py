"""Plan de course : assemble parcours, profil athlète, météo et moteur de simulation."""
import json
import os
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np

from . import course as C
from . import osm as O
from . import plan as PL
from . import weather as WX
from .fit_import import load_archive
from .service import GPX, FIT_DIR, OSM_CACHE, PROFILE_CACHE, load_aids, profile_json

START_DEFAULT = "2026-12-05T23:30"


@lru_cache(maxsize=1)
def _course_full():
    r = C.analyse(GPX, aids_override=load_aids())
    if os.path.exists(OSM_CACHE):
        ways = O.fetch_ways(r["lat"], r["lon"], OSM_CACHE)
        factor, _ = O.technicality(r["lat"], r["lon"], ways)
    else:                                  # OSM pas encore téléchargé : terrain supposé standard
        factor = np.full(len(r["lat"]), PL.TECH_REF)
    r["tech"] = factor
    r["aid_km"] = [a["km"] for a in r["aid_stations"]]
    return r


def _median_alt():
    pr = profile_json()
    if pr.get("median_alt") is not None:
        return pr["median_alt"]
    return None          # profil ancien sans altitude d'entraînement : l'effet d'altitude est alors ignoré


def _parse_cutoff(txt):
    if not txt:
        return None
    h, _, m = txt.lower().partition("h")
    return int(h) * 3600 + (int(m) * 60 if m.strip() else 0)


def plan_json(q):
    """q : dict de paramètres (valeurs absentes = défauts)."""
    r = _course_full()
    pr = profile_json()
    table = PL.SpeedTable(pr["grade_profile"], pr["cs_kmh"])
    start = datetime.fromisoformat(q.get("start") or START_DEFAULT)
    n_aid = len(r["aid_km"])
    stops = (list(q.get("stops_min") or []) + [3.0] * n_aid)[:n_aid]
    params = {"pct": None, "aggr": q.get("aggr", 0.0), "climb": q.get("climb", 0.0), "descent": q.get("descent", 0.0),
              "drift_pct_h": q.get("drift", 1.5), "tech_sens": q.get("tech_sens", 1.0),
              "night_pen_pct": q.get("night", 4.0), "heat_sens_pct": q.get("heat", 0.4),
              "alt_sens": q.get("alt_sens", 1.0), "stops_min": stops, "start": start}

    # météo : départ, chaque ravito, arrivée
    grid = r["grid_m"]
    pts = [(float(r["lat"][0]), float(r["lon"][0]), float(r["ele"][0]))]
    kms = [0.0]
    for a in r["aid_stations"]:
        i = int(np.argmin(np.abs(grid - a["km"] * 1000)))
        pts.append((float(r["lat"][i]), float(r["lon"][i]), float(r["ele"][i])))
        kms.append(a["km"])
    pts.append((float(r["lat"][-1]), float(r["lon"][-1]), float(r["ele"][-1])))
    kms.append(r["total_km"])
    wx = None
    try:
        wx = WX.fetch(pts, start.replace(minute=0), hours=24)
    except Exception:
        pass

    def wx_at(var, km_m, clock):
        if wx is None:
            return None
        h = int(np.clip(round((clock - start.replace(minute=0)).total_seconds() / 3600), 0, len(wx["hours"]) - 1))
        ok = [(k, wx[var][i][h]) for i, k in enumerate(kms) if wx[var][i][h] is not None]
        if not ok:
            return None
        return float(np.interp(km_m / 1000, [k for k, _ in ok], [v for _, v in ok]))

    weather = (lambda km_m, clock: wx_at("temperature_2m", km_m, clock)) if wx else None
    kw = {"weather": weather, "ref_alt": _median_alt()}

    # effort recommandé selon la durée (itération : durée -> % -> durée)
    T = 10.0
    for _ in range(4):
        T = PL.simulate(r, table, {**params, "pct": PL.recommended_pct(T)}, **kw)["total_s"] / 3600
    rec = PL.recommended_pct(T)

    solved = None
    target_s = q.get("target_h") * 3600 if q.get("target_h") else None
    if q.get("pct") is not None:
        pct = q["pct"]
    elif target_s:
        solved = pct = PL.solve_pct(r, table, params, target_s, **kw)
    else:
        pct = rec
    params["pct"] = pct
    res = PL.simulate(r, table, params, **kw)

    hr_cs = pr["hr_at_best"].get("1800") or pr["hr_at_best"].get("1200")
    sections = []
    prev_dep = 0.0
    nsec = len(r["sections"])
    for i, s in enumerate(r["sections"]):
        last = i == nsec - 1
        if last:
            arr = dep = res["t"][-1]
        else:
            arr, dep = res["arrive_aid"][i]
        i0 = int(np.argmin(np.abs(grid - s["start_km"] * 1000)))
        i1 = len(grid) - 1 if last else int(np.argmin(np.abs(grid - s["end_km"] * 1000)))
        mid = (s["start_km"] + s["end_km"]) / 2 / r["total_km"]
        pct_mid = pct * (1 + 0.06 * params["aggr"] * (1 - 2 * mid))
        cut = _parse_cutoff(r["aid_stations"][i]["cutoff"]) if not last else None
        mid_clock = start + timedelta(seconds=(prev_dep + arr) / 2)
        km_mid = (s["start_km"] + s["end_km"]) / 2 * 1000
        sections.append({
            "n": s["n"], "from": s["from"], "to": s["to"], "start_km": s["start_km"], "end_km": s["end_km"],
            "dist_km": s["dist_km"], "gain": s["gain"], "loss": s["loss"],
            "time_s": arr - prev_dep, "time": PL.fmt_hm(arr - prev_dep),
            "pace_min_km": (arr - prev_dep) / 60 / s["dist_km"],
            "arrival": PL.fmt_hm(arr), "clock": (start + timedelta(seconds=arr)).strftime("%H:%M"),
            "stop_min": 0 if last else stops[i],
            "effort_pct": pct_mid, "hr_target": PL.hr_target(pct_mid, table, hr_cs),
            "cutoff": r["aid_stations"][i]["cutoff"] if cut else None,
            "cutoff_margin_min": (cut - arr) / 60 if cut else None,
            "tech": float(np.mean(r["tech"][i0:i1 + 1])),
            "temp": wx_at("temperature_2m", km_mid, mid_clock),
            "rain_mm_h": wx_at("precipitation", km_mid, mid_clock),
            "wind_kmh": wx_at("wind_speed_10m", km_mid, mid_clock),
        })
        prev_dep = dep

    k, win = 4, 40
    t = res["t"].copy()
    for j, (arr, dep) in res["arrive_aid"].items():   # allure = temps de déplacement, arrêts exclus
        t[int(np.searchsorted(grid, r["aid_km"][j] * 1000)):] -= dep - arr
    pace = np.full(len(grid), np.nan)
    for i in range(win, len(grid)):
        pace[i] = (t[i] - t[i - win]) / 60 / ((grid[i] - grid[i - win]) / 1000)
    pace[:win] = pace[win]
    return {
        "params": {**{kk: vv for kk, vv in params.items() if kk != "start"}, "start": start.isoformat()},
        "recommended_pct": rec, "solved_pct": solved, "pct": pct,
        "cs_kmh": pr["cs_kmh"], "pct_ref": table.pct_ref, "ref_alt": kw["ref_alt"],
        "total_s": res["total_s"], "total": PL.fmt_hm(res["total_s"]), "stops_s": res["stop_s"],
        "finish_clock": (start + timedelta(seconds=res["total_s"])).strftime("%a %d/%m %H:%M"),
        "target_h": q.get("target_h"),
        "weather_source": wx["source"] if wx else None,
        "sections": sections,
        "profile": {"km": [round(float(x) / 1000, 2) for x in grid[::k]],
                    "ele": [round(float(x)) for x in r["ele"][::k]],
                    "t_h": [round(float(x) / 3600, 3) for x in res["t"][::k]],
                    "pace": [None if np.isnan(x) else round(float(x), 2) for x in pace[::k]]},
    }
