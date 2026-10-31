"""Analyse d'une trace GPX : profil lissé, pentes, sections, ravitos."""
import math
import numpy as np
import gpxpy

AID_WORDS = ("ravitaillement", "bouteille", "ravito")
CUTOFF_WORDS = ("barrière", "barriere")

GRADE_CLASSES = ["descente raide (<-15%)", "descente (-15/-8%)", "descente douce (-8/-3%)", "roulant (±3%)",
                 "montée douce (3/8%)", "montée (8/15%)", "montée raide (>15%)"]


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_gpx(path):
    with open(path, encoding="utf-8") as f:
        g = gpxpy.parse(f)
    pts = [p for t in g.tracks for s in t.segments for p in s.points] or [p for r in g.routes for p in r.points]
    lat = np.array([p.latitude for p in pts])
    lon = np.array([p.longitude for p in pts])
    ele = np.array([p.elevation if p.elevation is not None else np.nan for p in pts])
    d = np.zeros(len(pts))
    for i in range(1, len(pts)):
        d[i] = d[i - 1] + _haversine(lat[i - 1], lon[i - 1], lat[i], lon[i])
    waypoints = [(w.latitude, w.longitude, (w.name or "").strip()) for w in g.waypoints]
    name = g.tracks[0].name if g.tracks and g.tracks[0].name else "Parcours"
    return name, lat, lon, ele, d, waypoints


def resample(d, arrays, step=25.0):
    grid = np.append(np.arange(0, d[-1], step), d[-1])
    return grid, [np.interp(grid, d, a) for a in arrays]


def smooth(x, window):
    k = max(1, int(window))
    if k % 2 == 0:
        k += 1
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.convolve(xp, np.ones(k) / k, mode="valid")


def gain_loss(ele, threshold=3.0):
    """D+/D- avec hystérésis pour ignorer le bruit d'altitude."""
    up = down = 0.0
    ref = ele[0]
    for e in ele[1:]:
        if e - ref >= threshold:
            up += e - ref
            ref = e
        elif ref - e >= threshold:
            down += ref - e
            ref = e
    return up, down


def project_waypoints(lat, lon, d, waypoints):
    out = []
    for wlat, wlon, name in waypoints:
        dist = np.hypot((lat - wlat) * 111320, (lon - wlon) * 111320 * math.cos(math.radians(wlat)))
        i = int(np.argmin(dist))
        low = name.lower()
        kind = "aid" if any(w in low for w in AID_WORDS) else "cutoff" if any(w in low for w in CUTOFF_WORDS) else "other"
        out.append({"name": name, "kind": kind, "km": d[i] / 1000, "off_track_m": float(dist[i]), "idx": i})
    return sorted(out, key=lambda w: w["km"])


def merge_aid_stations(wps, radius_km=0.3):
    """Fusionne les ravitos proches (ravito + ravito chaud) et rattache les barrières horaires."""
    aids = [w for w in wps if w["kind"] == "aid"]
    cuts = [w for w in wps if w["kind"] == "cutoff"]
    merged = []
    for a in aids:
        if merged and a["km"] - merged[-1]["km"] < radius_km:
            merged[-1]["name"] += " + " + a["name"]
            continue
        merged.append(dict(a))
    for m in merged:
        near = [c for c in cuts if abs(c["km"] - m["km"]) < radius_km]
        m["cutoff"] = near[0]["name"].split("-")[-1].strip() if near else None
    return merged


def detect_climbs(ele, min_gain=100, drop_tol=30):
    """Montées/descentes significatives : suivi des extrema avec tolérance de retour."""
    segs = []
    start = hi = lo = 0
    direction = 0
    for i in range(1, len(ele)):
        if ele[i] > ele[hi]:
            hi = i
        if ele[i] < ele[lo]:
            lo = i
        if direction == 0:
            if ele[hi] - ele[start] >= drop_tol:
                direction = 1
            elif ele[start] - ele[lo] >= drop_tol:
                direction = -1
        elif direction == 1 and ele[hi] - ele[i] >= drop_tol:
            if ele[hi] - ele[start] >= min_gain:
                segs.append(("climb", start, hi))
            start, direction, lo = hi, -1, i
        elif direction == -1 and ele[i] - ele[lo] >= drop_tol:
            if ele[start] - ele[lo] >= min_gain:
                segs.append(("descent", start, lo))
            start, direction, hi = lo, 1, i
    if direction == 1 and ele[hi] - ele[start] >= min_gain:
        segs.append(("climb", start, hi))
    if direction == -1 and ele[start] - ele[lo] >= min_gain:
        segs.append(("descent", start, lo))
    return segs


def grade_class(g):
    if g <= -15: return GRADE_CLASSES[0]
    if g <= -8: return GRADE_CLASSES[1]
    if g <= -3: return GRADE_CLASSES[2]
    if g < 3: return GRADE_CLASSES[3]
    if g < 8: return GRADE_CLASSES[4]
    if g < 15: return GRADE_CLASSES[5]
    return GRADE_CLASSES[6]


def analyse(path, step=25.0, aids_override=None):
    name, lat, lon, ele, d, wps = load_gpx(path)
    if np.isnan(ele).any():
        raise ValueError("Altitude manquante dans la trace")
    grid, (la, lo, el) = resample(d, [lat, lon, ele], step)
    el_s = smooth(el, 5)
    gr = smooth(np.gradient(el_s, grid) * 100, 5)
    up, down = gain_loss(el_s)
    wp = project_waypoints(lat, lon, d, wps)
    aids = merge_aid_stations(wp)
    finish_km = grid[-1] / 1000
    aids = [a for a in aids if finish_km - a["km"] > 0.5]  # ravito à l'arrivée = pas une section
    if aids_override is not None:      # ravitos saisis à la main
        aids = []
        for a in sorted(aids_override, key=lambda x: float(x["km"])):
            km = float(a["km"])
            if 0.2 < km < finish_km - 0.5:
                aids.append({"name": (a.get("name") or "Ravitaillement").strip(), "kind": "aid", "km": km,
                             "idx": int(np.argmin(np.abs(grid - km * 1000))), "cutoff": (a.get("cutoff") or "").strip() or None})

    cuts_km = [0.0] + [a["km"] for a in aids] + [grid[-1] / 1000]
    sections = []
    for i in range(len(cuts_km) - 1):
        a, b = cuts_km[i] * 1000, cuts_km[i + 1] * 1000
        m = (grid >= a) & (grid <= b)
        u, dn = gain_loss(el_s[m])
        sections.append({
            "n": i + 1,
            "from": "Départ" if i == 0 else aids[i - 1]["name"],
            "to": "Arrivée" if i == len(cuts_km) - 2 else aids[i]["name"],
            "start_km": cuts_km[i], "end_km": cuts_km[i + 1],
            "dist_km": cuts_km[i + 1] - cuts_km[i],
            "gain": u, "loss": dn,
            "alt_min": float(el_s[m].min()), "alt_max": float(el_s[m].max()),
        })

    cls = np.array([grade_class(g) for g in gr[:-1]])
    seglen = np.diff(grid)
    dist_by_class = {c: float(seglen[cls == c].sum() / 1000) for c in GRADE_CLASSES}

    climbs = [{"type": t, "start_km": grid[s] / 1000, "end_km": grid[e] / 1000,
               "dist_km": (grid[e] - grid[s]) / 1000, "gain": abs(el_s[e] - el_s[s]),
               "avg_grade": (el_s[e] - el_s[s]) / (grid[e] - grid[s]) * 100,
               "alt_start": float(el_s[s]), "alt_end": float(el_s[e])}
              for t, s, e in detect_climbs(el_s)]

    return {
        "name": name, "total_km": grid[-1] / 1000, "gain": up, "loss": down,
        "alt_min": float(el_s.min()), "alt_max": float(el_s.max()),
        "grid_m": grid, "lat": la, "lon": lo, "ele": el_s, "grade": gr,
        "waypoints": wp, "aid_stations": aids, "sections": sections,
        "dist_by_class": dist_by_class, "climbs": climbs,
    }
