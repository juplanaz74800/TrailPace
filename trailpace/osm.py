"""Technicité du terrain déduite d'OpenStreetMap (Overpass API)."""
import json
import math
import os
import time
import numpy as np
import requests

OVERPASS = "https://overpass-api.de/api/interpreter"
MIRRORS = ["https://overpass.openstreetmap.fr/api/interpreter", OVERPASS, "https://overpass.private.coffee/api/interpreter"]

# Coefficient de ralentissement (1.0 = roulant). Valeurs de départ, à calibrer sur les données de l'athlète.
SURFACE_FACTOR = {
    "asphalt": 1.00, "paved": 1.00, "concrete": 1.00, "paving_stones": 1.03,
    "compacted": 1.03, "fine_gravel": 1.04, "gravel": 1.06, "ground": 1.10,
    "dirt": 1.10, "earth": 1.10, "grass": 1.12, "mud": 1.25, "sand": 1.25,
    "rock": 1.25, "pebblestone": 1.20, "unpaved": 1.08,
}
HIGHWAY_FACTOR = {
    "motorway": 1.0, "trunk": 1.0, "primary": 1.0, "secondary": 1.0, "tertiary": 1.0,
    "unclassified": 1.0, "residential": 1.0, "service": 1.0, "track": 1.06,
    "path": 1.15, "footway": 1.08, "bridleway": 1.10, "steps": 1.40, "cycleway": 1.0,
}
SAC_FACTOR = {
    "hiking": 1.05, "mountain_hiking": 1.15, "demanding_mountain_hiking": 1.35,
    "alpine_hiking": 1.55, "demanding_alpine_hiking": 1.8, "difficult_alpine_hiking": 2.0,
}
TRACKTYPE_FACTOR = {"grade1": 1.0, "grade2": 1.04, "grade3": 1.08, "grade4": 1.14, "grade5": 1.20}


def way_factor(tags):
    f = HIGHWAY_FACTOR.get(tags.get("highway"), 1.08)
    s = SURFACE_FACTOR.get(tags.get("surface"))
    if s is not None:
        # sur un sentier le revêtement s'ajoute à la difficulté du chemin ; sur route il la remplace
        f = max(f, s) if tags.get("highway") in ("path", "footway", "steps", "track", "bridleway") else s
    t = TRACKTYPE_FACTOR.get(tags.get("tracktype"))
    if t is not None and s is None:
        f = max(f, t)
    sac = SAC_FACTOR.get(tags.get("sac_scale"))
    if sac is not None:
        f = max(f, sac)
    vis = tags.get("trail_visibility")
    if vis in ("bad", "horrible", "no"):
        f *= 1.10
    return f


def _query(points):
    poly = ",".join(f"{la:.5f},{lo:.5f}" for la, lo in points)
    return f"""[out:json][timeout:60];
way["highway"](around:25,{poly});
out tags geom;"""


def _fetch_chunk(part):
    for attempt in range(8):
        try:
            r = requests.post(MIRRORS[attempt % len(MIRRORS)], data={"data": _query(part)}, timeout=90,
                              headers={"User-Agent": "trailpace/0.1 (course planning)"})
            if r.status_code == 200:
                return r.json()["elements"]
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (attempt + 1))
    raise RuntimeError("Overpass indisponible")


def fetch_ways(lat, lon, cache_path=None, every=4, chunk=30, workers=3, progress=None):
    """Télécharge les chemins OSM à moins de 25 m de la trace, par morceaux de ~3 km, en parallèle."""
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    from concurrent.futures import ThreadPoolExecutor
    pts = list(zip(lat[::every], lon[::every]))
    parts = [pts[max(0, k - 1):k + chunk] for k in range(0, len(pts), chunk)]
    seen, data = set(), []
    with ThreadPoolExecutor(workers) as ex:
        for i, elements in enumerate(ex.map(_fetch_chunk, parts), 1):
            if progress:
                progress(i / len(parts))
            for el in elements:
                if el["id"] not in seen:
                    seen.add(el["id"])
                    data.append(el)
    if cache_path and data:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    return data


def technicality(lat, lon, ways):
    """Pour chaque point de la trace : facteur de technicité du chemin OSM le plus proche (<25 m)."""
    lat0 = float(np.mean(lat))
    kx, ky = 111320 * math.cos(math.radians(lat0)), 111320
    seg_a, seg_b, seg_f, seg_t = [], [], [], []
    for w in ways:
        geom = [g for g in (w.get("geometry") or []) if g]
        if not geom or len(geom) < 2:
            continue
        tags = w.get("tags", {})
        f = way_factor(tags)
        for p, q in zip(geom[:-1], geom[1:]):
            seg_a.append((p["lon"] * kx, p["lat"] * ky))
            seg_b.append((q["lon"] * kx, q["lat"] * ky))
            seg_f.append(f)
            seg_t.append(tags.get("highway", "?") + ("/" + tags["surface"] if "surface" in tags else ""))
    A, B, F = np.array(seg_a), np.array(seg_b), np.array(seg_f)
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-9)
    out_f = np.ones(len(lat))
    out_t = ["?"] * len(lat)
    out_d = np.full(len(lat), np.inf)
    for i in range(len(lat)):
        p = np.array([lon[i] * kx, lat[i] * ky])
        # pré-filtre rapide par boîte englobante
        near = (np.minimum(A[:, 0], B[:, 0]) - 30 < p[0]) & (np.maximum(A[:, 0], B[:, 0]) + 30 > p[0]) & \
               (np.minimum(A[:, 1], B[:, 1]) - 30 < p[1]) & (np.maximum(A[:, 1], B[:, 1]) + 30 > p[1])
        idx = np.where(near)[0]
        if idx.size == 0:
            continue
        t = np.clip(((p - A[idx]) * AB[idx]).sum(1) / L2[idx], 0, 1)
        proj = A[idx] + AB[idx] * t[:, None]
        dist = np.hypot(*(proj - p).T)
        j = int(np.argmin(dist))
        if dist[j] <= 25:
            out_f[i], out_d[i], out_t[i] = F[idx[j]], dist[j], seg_t[idx[j]]
    return out_f, out_t
