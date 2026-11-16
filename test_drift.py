"""Teste les trois sources de dérive du plan via l'API (serveur lancé sur :8000)."""
import requests

B = "http://localhost:8000/api/plan"
for name, params in [("auto (par défaut)", {}), ("mesurée (forcée)", {"drift_src": "measured"}),
                     ("manuelle 1,5 %/h", {"drift": 1.5}), ("manuelle 0 %/h", {"drift": 0}), ("manuelle 4 %/h", {"drift": 4})]:
    p = requests.get(B, params=params, timeout=150).json()
    di = p["drift_info"]
    print(f"{name:20s} -> dérive utilisée {di['used']:.2f} %/h ({di['source']}) | plan {p['total']} | arrivée {p['finish_clock']}")
m = p["drift_info"]["measured"]
print("mesure du profil :", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()}, "| fiable :", p["drift_info"]["reliable"])
