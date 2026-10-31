import json
import time

import requests

B = "http://localhost:8000"
import sys

# usage : python test_upload_real.py course.gpx archive.zip   (serveur lancé sur :8000 ; remplace l'archive existante !)
GPX, ZIP = sys.argv[1], sys.argv[2]


def wait(name, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = requests.get(B + "/api/status").json()["jobs"].get(name)
        if j and j["state"] != "running":
            return j
        time.sleep(2)
    return {"state": "timeout"}


with open(GPX, "rb") as f:
    r = requests.post(B + "/api/upload/gpx", files={"file": ("saintelyon.gpx", f)})
print("GPX ->", r.status_code, r.json())
print("job course ->", wait("course"))
s = requests.get(B + "/api/status").json()
print("gpx:", {k: s["gpx"].get(k) for k in ("name", "km", "gain", "aids", "osm")})
print("course API ->", requests.get(B + "/api/course").status_code, "| plan API ->", requests.get(B + "/api/plan").status_code)

with open(ZIP, "rb") as f:
    r = requests.post(B + "/api/upload/archive", files=[("files", ("archive.zip", f))], data={"replace": "true"})
print("archive ->", r.status_code, r.json())
t = time.time()
print("job profile ->", wait("profile"), round(time.time() - t), "s")
s = requests.get(B + "/api/status").json()
print("archive:", s["archive"])
p = requests.get(B + "/api/plan").json()
print("plan:", p["total"], p["finish_clock"], round(p["pct"], 3))
