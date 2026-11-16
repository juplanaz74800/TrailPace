"""Teste la saisie manuelle des ravitos via l'API puis restaure l'état initial (serveur sur :8000)."""
import requests

B = "http://localhost:8000"

before = requests.get(B + "/api/aids").json()
print("avant :", before["manual"], len(before["aids"]), "ravito(s)")

rows = [{"name": "R1 test", "km": "17.1", "cutoff": "4h30"}, {"name": "R2 test", "km": "32", "cutoff": ""},
        {"name": "Hors trace", "km": "999"}]
r = requests.put(B + "/api/aids", json=rows)
print("km hors trace ->", r.status_code, r.text[:90])

r = requests.put(B + "/api/aids", json=rows[:2])
d = r.json()
print("2 ravitos ->", r.status_code, d["manual"], [(a["name"], a["km"], a["cutoff"]) for a in d["aids"]])
c = requests.get(B + "/api/course").json()
print("parcours :", len(c["aid_stations"]), "ravitos,", len(c["sections"]), "sections", [s["to"] for s in c["sections"]])
p = requests.get(B + "/api/plan").json()
print("plan :", p["total"], "| barrières :", [s["cutoff"] for s in p["sections"]])

r = requests.put(B + "/api/aids", json=[{"name": "x", "km": "abc"}])
print("km invalide ->", r.status_code, r.text[:80])

d = requests.delete(B + "/api/aids").json()
print("après restauration :", d["manual"], len(d["aids"]), "ravito(s)")
