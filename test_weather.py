"""Teste la météo en trois situations : prévisions seules, mixte (limite J+15 franchie), climatologie seule."""
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")
from trailpace import weather as W

pts = [(45.45, 4.40, 494.0), (45.73, 4.82, 300.0)]
today = date.today()
cases = [("prévisions seules (J+4, 24 h)", datetime.combine(today + timedelta(days=4), datetime.min.time()).replace(hour=8), 24),
         ("mixte (départ J+14 à 22 h, 36 h)", datetime.combine(today + timedelta(days=14), datetime.min.time()).replace(hour=22), 36),
         ("climatologie seule (J+19, 36 h)", datetime.combine(today + timedelta(days=19), datetime.min.time()).replace(hour=23, minute=0), 36)]
for name, start, hours in cases:
    w = W.fetch(pts, start, hours=hours)
    t = w["temperature_2m"][0]
    miss = sum(x is None for x in t)
    print(f"{name}\n   source : {w['source']}\n   prévision jusqu'à : {w['forecast_until']} | heures sans valeur : {miss}/{len(t)} | T départ {t[0] and round(t[0], 1)} °C, T fin {t[-1] and round(t[-1], 1)} °C")
print("prévisions disponibles pour la course du 05/12/2026 à partir du :", W.forecast_from(date(2026, 12, 5)))
