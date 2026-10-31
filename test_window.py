"""Change la période analysée via l'API, attend le recalcul et affiche le résultat (serveur lancé sur :8000)."""
import sys
import time

import requests

B = "http://localhost:8000"


def wait():
    t0 = time.time()
    time.sleep(1)
    while time.time() - t0 < 300:
        j = requests.get(B + "/api/status").json()["jobs"].get("profile")
        if j and j["state"] != "running":
            return j, time.time() - t0
        time.sleep(2)
    return None, 0


for days in [int(x) for x in sys.argv[1:]] or [180, 365]:
    r = requests.put(B + "/api/settings", json={"window_days": days})
    j, dt = wait()
    f = requests.get(B + "/api/profile").json()
    print(f"{days:4d} j -> HTTP {r.status_code} | {j['state'] if j else '?'} en {dt:.0f} s | {f['n_runs']} courses sur {f['span_days']:.0f} j,"
          f" {f['files_selected']}/{f['files_total']} fichiers | CS {f['cs_kmh']} km/h, CP {f['cp_w']} W, plus longue {f['longest_h']} h")
r = requests.put(B + "/api/settings", json={"window_days": 7})
print("période invalide ->", r.status_code, r.text[:80])
