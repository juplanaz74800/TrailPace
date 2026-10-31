"""Météo gratuite (Open-Meteo) : prévisions si la course est dans les 16 jours, sinon climatologie
(moyenne des mêmes jours sur les années passées)."""
import json
import os
from datetime import date, datetime, timedelta

import numpy as np
import requests

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
VARS = "temperature_2m,precipitation,wind_speed_10m,cloud_cover"
CACHE = "data/weather_cache.json"


def _get(url, params):
    r = requests.get(url, params=params, timeout=60, headers={"User-Agent": "trailpace/0.1"})
    r.raise_for_status()
    j = r.json()
    return j if isinstance(j, list) else [j]


def fetch(points, start_dt, hours=24, years=5, today=None):
    """points: [(lat, lon, alt)]. Retourne {'source', 'hours': [datetimes], 'temp': [[...] par point], ...}
    couvrant `hours` heures à partir de start_dt (heure locale Europe/Paris)."""
    today = today or date.today()
    key = f"{start_dt.isoformat()}|{hours}|{today.isoformat()}|" + ";".join(f"{a:.3f},{b:.3f}" for a, b, _ in points)
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    if key in cache:
        return cache[key]

    lat = ",".join(f"{p[0]:.4f}" for p in points)
    lon = ",".join(f"{p[1]:.4f}" for p in points)
    elev = ",".join(f"{p[2]:.0f}" for p in points)
    base = {"latitude": lat, "longitude": lon, "elevation": elev, "hourly": VARS, "timezone": "Europe/Paris"}
    end_dt = start_dt + timedelta(hours=hours)
    n = len(points)
    out = {"hours": [(start_dt + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(hours + 1)]}

    if (start_dt.date() - today).days <= 15 and start_dt.date() >= today:
        res = _get(FORECAST, {**base, "start_date": start_dt.date().isoformat(), "end_date": end_dt.date().isoformat()})
        out["source"] = "prévisions Open-Meteo"
        acc = {v: [{} for _ in range(n)] for v in VARS.split(",")}
        for i, loc in enumerate(res):
            for v in VARS.split(","):
                for t, x in zip(loc["hourly"]["time"], loc["hourly"][v]):
                    acc[v][i][t] = x
        for v in acc:
            out[v] = [[acc[v][i].get(h) for h in out["hours"]] for i in range(n)]
    else:
        out["source"] = f"climatologie Open-Meteo (moyenne des {years} dernières années à la même date)"
        samples = {v: [[[] for _ in out["hours"]] for _ in range(n)] for v in VARS.split(",")}
        for k in range(1, years + 1):
            s = start_dt.replace(year=start_dt.year - k)
            e = s + timedelta(hours=hours)
            try:
                res = _get(ARCHIVE, {**base, "start_date": s.date().isoformat(), "end_date": e.date().isoformat()})
            except requests.RequestException:
                continue
            for i, loc in enumerate(res):
                times = loc["hourly"]["time"]
                idx = {t: j for j, t in enumerate(times)}
                for hi in range(len(out["hours"])):
                    t = (s + timedelta(hours=hi)).strftime("%Y-%m-%dT%H:00")
                    j = idx.get(t)
                    if j is None:
                        continue
                    for v in VARS.split(","):
                        x = loc["hourly"][v][j]
                        if x is not None:
                            samples[v][i][hi].append(x)
        for v in samples:
            out[v] = [[float(np.mean(c)) if c else None for c in row] for row in samples[v]]
    os.makedirs("data", exist_ok=True)
    cache[key] = out
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    return out
