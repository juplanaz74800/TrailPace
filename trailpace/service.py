"""Calculs mis en forme pour l'API (avec cache disque)."""
import json
import os
import numpy as np

from . import course as C
from . import osm as O
from . import profile as P
from .fit_import import load_archive

from .store import AIDS, DEFAULT_SETTINGS, FIT_DIR, GPX, OSM_CACHE, PROFILE_CACHE, SETTINGS


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS):
        with open(SETTINGS, encoding="utf-8") as f:
            s.update(json.load(f))
    return s


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def load_aids():
    """Ravitos saisis à la main (remplacent la détection automatique), ou None."""
    if not os.path.exists(AIDS):
        return None
    with open(AIDS, encoding="utf-8") as f:
        return json.load(f)


def course_json():
    r = C.analyse(GPX, aids_override=load_aids())
    tech = None
    if os.path.exists(OSM_CACHE):
        ways = O.fetch_ways(r["lat"], r["lon"], OSM_CACHE)
        factor, kind = O.technicality(r["lat"], r["lon"], ways)
        tech = {"factor": factor, "kind": kind}
    # sous-échantillonnage pour le front (1 point / 100 m)
    k = 4
    km = r["grid_m"][::k] / 1000
    out = {
        "name": r["name"].replace("\ufffd", "é"), "total_km": _r(r["total_km"]), "gain": _r(r["gain"], 0),
        "loss": _r(r["loss"], 0), "alt_min": _r(r["alt_min"], 0), "alt_max": _r(r["alt_max"], 0),
        "profile": {"km": [_r(x, 2) for x in km], "ele": [_r(x, 0) for x in r["ele"][::k]],
                    "grade": [_r(x, 1) for x in r["grade"][::k]],
                    "lat": [round(float(x), 5) for x in r["lat"][::k]],
                    "lon": [round(float(x), 5) for x in r["lon"][::k]]},
        "aid_stations": [{"name": a["name"], "km": _r(a["km"], 1), "cutoff": a["cutoff"],
                          "alt": _r(r["ele"][a["idx"] // 1] if False else float(np.interp(a["km"] * 1000, r["grid_m"], r["ele"])), 0),
                          "lat": _r(np.interp(a["km"] * 1000, r["grid_m"], r["lat"]), 5),
                          "lon": _r(np.interp(a["km"] * 1000, r["grid_m"], r["lon"]), 5)} for a in r["aid_stations"]],
        "sections": [{k2: (_r(v, 1) if isinstance(v, float) else v) for k2, v in s.items()} for s in r["sections"]],
        "dist_by_class": {k2: _r(v) for k2, v in r["dist_by_class"].items()},
        "climbs": [{k2: (_r(v, 1) if isinstance(v, float) else v) for k2, v in c.items()} for c in r["climbs"]],
        "technicality": None,
    }
    if tech:
        f = tech["factor"][::k]
        out["profile"]["tech"] = [_r(x, 2) for x in f]
        matched = np.array(tech["kind"]) != "?"
        # technicité moyenne par section
        grid = r["grid_m"]
        for s, sec in zip(r["sections"], out["sections"]):
            m = (grid >= s["start_km"] * 1000) & (grid <= s["end_km"] * 1000)
            sec["tech_mean"] = _r(tech["factor"][m].mean(), 3)
        from collections import Counter
        kinds = Counter(t.split("/")[0] for t in tech["kind"] if t != "?")
        out["technicality"] = {"matched_pct": _r(matched.mean() * 100, 0),
                               "mean_factor": _r(tech["factor"].mean(), 3),
                               "by_highway": {k2: _r(v / len(tech["kind"]) * 100, 0) for k2, v in kinds.most_common(6)}}
    return out


def profile_json(force=False, progress=None):
    """Profil coureur (mis en cache). progress(fraction, message) facultatif pour le suivi."""
    if os.path.exists(PROFILE_CACHE) and not force:
        with open(PROFILE_CACHE, encoding="utf-8") as f:
            return json.load(f)
    rep = progress or (lambda *a, **k: None)
    rep(0.0, "Lecture des fichiers…")
    meta = {}
    window_days = int(load_settings()["window_days"])
    allacts = load_archive(FIT_DIR, progress=lambda x, m=None: rep(0.5 * x, m), days=window_days or None, meta=meta)
    runs = [(s, a) for s, a in allacts if s["sport"] == "running" and s["has_gps"] and s["duration_s"] > 600]
    if len(runs) < 5:
        raise ValueError(f"Seulement {len(runs)} sortie(s) de course à pied avec GPS exploitable(s) : il en faut au moins 5.")
    rep(0.5, "Analyse des pentes et vitesses…")
    wl = [(s, P.windows(a)) for s, a in runs]
    wl = [(s, w) for s, w in wl if w is not None]
    if not any(np.isfinite(w["hr"]).any() for _, w in wl):
        raise ValueError("Aucune donnée de fréquence cardiaque dans ces sorties.")
    hrmax = P.estimate_hrmax([w for _, w in wl])
    prof = P.grade_profile([w for _, w in wl], hrmax)
    rep(0.7, "Courbe vitesse/puissance critique…")
    cm = P.critical_model([P.to_1hz(a) for _, a in runs], hrmax=hrmax)
    rep(0.9, "Durabilité…")
    per, agg = P.durability(wl, hrmax)
    starts = [s["start"] for s, _ in runs]
    alts = np.concatenate([a["alt"][np.isfinite(a["alt"])] for _, a in runs])
    sessions = []          # bilan d'entraînement : durée et dépense (modèle de coût de Minetti, kcal par kg de poids de corps)
    for s, w in wl:
        kcal_kg = float((P.minetti_cost(w["grade"]) * w["v"] * P.W).sum() / 4184)
        sessions.append({"start": s["start"], "dur_h": round(s["duration_s"] / 3600, 2), "dist_km": round(s["dist_km"], 1),
                         "gain": round(s["gain"]), "kcal_per_kg": round(kcal_kg, 2)})
    out = {
        "sessions": sessions,
        "median_alt": float(np.median(alts)) if alts.size else None,
        "window_days": window_days, "files_total": meta.get("total_files"), "files_selected": meta.get("selected_files"),
        "period_start": meta.get("cutoff") if window_days else min(s["start"] for s, _ in runs), "period_end": meta.get("ref"),
        "n_activities": len(allacts), "n_runs": len(runs),
        "span_days": _r((max(starts) - min(starts)) / 86400, 0),
        "longest_h": _r(max(s["duration_s"] for s, _ in runs) / 3600),
        "hrmax": _r(hrmax, 0),
        "has_power": bool(sum(s["has_power"] for s, _ in runs) > len(runs) / 2),
        "grade_profile": [{k: (_r(v, 2) if isinstance(v, float) else v) for k, v in row.items()} for row in prof],
        "cs_kmh": _r(cm.get("gap_cs", 0) * 3.6), "d_prime_m": _r(cm.get("gap_dprime"), 0),
        "cp_w": _r(cm.get("power_cs"), 0), "w_prime_j": _r(cm.get("power_dprime"), 0),
        "mean_max_gap_kmh": {str(k): _r(v * 3.6) for k, v in cm["gap"].items()},
        "mean_max_power": {str(k): _r(v, 0) for k, v in cm["power"].items()},
        "hr_at_best": {str(k): _r(v, 0) for k, v in cm["hr_at_best"].items()},
        "hr_at_best_power": {str(k): _r(v, 0) for k, v in cm["hr_at_best_power"].items()},
        "durability_runs": [{k: (_r(v, 1) if isinstance(v, float) else v) for k, v in p.items()} for p in per],
        "durability": {k: _r(v, 2) for k, v in (agg or {}).items()},
    }
    os.makedirs("data", exist_ok=True)
    with open(PROFILE_CACHE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out
