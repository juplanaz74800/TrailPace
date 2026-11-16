"""Météo gratuite (Open-Meteo) : prévisions réelles dès qu'elles existent, climatologie pour le reste.

L'API de prévisions couvre aujourd'hui + 15 jours (vérifié : au-delà, erreur « out of allowed range »). Pour chaque heure de la course :
prévision si disponible, sinon moyenne des mêmes jours sur les années passées. Une course qui chevauche la limite est donc « mixte »."""
import json
import os
from datetime import date, datetime, timedelta

import numpy as np
import requests

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
VARS = "temperature_2m,precipitation,wind_speed_10m,cloud_cover"
VAR_LIST = VARS.split(",")
CACHE = "data/weather_cache.json"
FORECAST_DAYS = 15          # dernier jour de prévision = aujourd'hui + 15
CACHE_MAX = 12


def forecast_from(start_date):
    """Premier jour où la course est couverte par les prévisions."""
    return start_date - timedelta(days=FORECAST_DAYS)


def _get(url, params):
    r = requests.get(url, params=params, timeout=60, headers={"User-Agent": "trailpace/0.1"})
    r.raise_for_status()
    j = r.json()
    return j if isinstance(j, list) else [j]


def _forecast(base, start_dt, end_dt, hour_keys, n, last_day):
    """Prévisions alignées sur hour_keys (None là où l'API n'en donne pas)."""
    s, e = start_dt.date(), min(end_dt.date(), last_day)
    res = _get(FORECAST, {**base, "start_date": s.isoformat(), "end_date": e.isoformat()})
    out = {v: [[None] * len(hour_keys) for _ in range(n)] for v in VAR_LIST}
    for i, loc in enumerate(res):
        idx = {t: j for j, t in enumerate(loc["hourly"]["time"])}
        for hi, key in enumerate(hour_keys):
            j = idx.get(key)
            if j is not None:
                for v in VAR_LIST:
                    out[v][i][hi] = loc["hourly"][v][j]
    return out


def _climatology(base, start_dt, hours, hour_keys, n, years):
    """Moyenne, heure par heure, des mêmes jours sur les `years` années passées."""
    samples = {v: [[[] for _ in hour_keys] for _ in range(n)] for v in VAR_LIST}
    for k in range(1, years + 1):
        try:
            s = start_dt.replace(year=start_dt.year - k)
        except ValueError:                      # 29 février
            s = (start_dt - timedelta(days=1)).replace(year=start_dt.year - k)
        e = s + timedelta(hours=hours)
        try:
            res = _get(ARCHIVE, {**base, "start_date": s.date().isoformat(), "end_date": e.date().isoformat()})
        except requests.RequestException:
            continue
        for i, loc in enumerate(res):
            idx = {t: j for j, t in enumerate(loc["hourly"]["time"])}
            for hi in range(len(hour_keys)):
                j = idx.get((s + timedelta(hours=hi)).strftime("%Y-%m-%dT%H:00"))
                if j is None:
                    continue
                for v in VAR_LIST:
                    x = loc["hourly"][v][j]
                    if x is not None:
                        samples[v][i][hi].append(x)
    return {v: [[float(np.mean(c)) if c else None for c in row] for row in samples[v]] for v in VAR_LIST}


def fetch(points, start_dt, hours=24, years=5, today=None):
    """points: [(lat, lon, alt)]. Retourne {'source', 'forecast_until', 'hours': [...], <variable>: [[...] par point]}
    couvrant `hours` heures à partir de start_dt (heure locale Europe/Paris)."""
    today = today or date.today()
    last_day = today + timedelta(days=FORECAST_DAYS)
    in_window = today <= start_dt.date() <= last_day
    now = datetime.now()
    stamp = f"{now:%Y-%m-%d}-{now.hour // 3}" if in_window else today.isoformat()   # les prévisions sont rafraîchies toutes les 3 h
    key = f"{start_dt.isoformat()}|{hours}|{stamp}|" + ";".join(f"{a:.3f},{b:.3f}" for a, b, _ in points)
    cache = {}
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
    if key in cache:
        return cache[key]

    base = {"latitude": ",".join(f"{p[0]:.4f}" for p in points), "longitude": ",".join(f"{p[1]:.4f}" for p in points),
            "elevation": ",".join(f"{p[2]:.0f}" for p in points), "hourly": VARS, "timezone": "Europe/Paris"}
    n = len(points)
    end_dt = start_dt + timedelta(hours=hours)
    hour_keys = [(start_dt + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(hours + 1)]
    out = {"hours": hour_keys}

    fc = None
    if in_window:
        try:
            fc = _forecast(base, start_dt, end_dt, hour_keys, n, last_day)
        except requests.RequestException:
            fc = None
    missing = fc is None or any(x is None for row in fc["temperature_2m"] for x in row)
    clim = _climatology(base, start_dt, hours, hour_keys, n, years) if missing else None

    for v in VAR_LIST:
        out[v] = []
        for i in range(n):
            row = []
            for hi in range(len(hour_keys)):
                x = fc[v][i][hi] if fc is not None else None
                row.append(x if x is not None else (clim[v][i][hi] if clim is not None else None))
            out[v].append(row)

    fc_hours = [hour_keys[hi] for hi in range(len(hour_keys)) if fc is not None and fc["temperature_2m"][0][hi] is not None]
    out["forecast_until"] = fc_hours[-1] if fc_hours else None
    if not fc_hours:
        out["source"] = f"climatologie Open-Meteo (moyenne des {years} dernières années à la même date)"
    elif not missing:
        out["source"] = "prévisions Open-Meteo"
    else:
        out["source"] = (f"prévisions Open-Meteo jusqu'au {datetime.fromisoformat(out['forecast_until']):%d/%m à %Hh}, "
                         f"puis climatologie ({years} dernières années)")
    os.makedirs("data", exist_ok=True)
    cache[key] = out
    for old in list(cache)[:-CACHE_MAX]:
        del cache[old]
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    return out
