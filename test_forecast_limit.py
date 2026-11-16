"""Teste jusqu'à quelle date l'API de prévisions Open-Meteo répond (outil de développement)."""
from datetime import date, timedelta

import requests

today = date.today()
for k in (7, 14, 15, 16, 17):
    d = today + timedelta(days=k)
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": 45.45, "longitude": 4.40, "hourly": "temperature_2m", "timezone": "Europe/Paris",
        "start_date": d.isoformat(), "end_date": d.isoformat()}, timeout=30)
    ok = r.status_code == 200
    n = len([x for x in r.json().get("hourly", {}).get("temperature_2m", []) if x is not None]) if ok else 0
    print(f"aujourd'hui + {k:2d} j ({d}) -> HTTP {r.status_code}", f"{n} valeurs" if ok else r.json().get("reason", "")[:90])
