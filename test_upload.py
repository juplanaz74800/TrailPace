"""Test de bout en bout des dépôts (serveur lancé sur :8000). Utilise des copies : ne touche pas à data/ sauf via l'API."""
import io
import json
import sys
import time
import zipfile

import requests

B = "http://localhost:8000"

# 1) fichier invalide refusé
r = requests.post(B + "/api/upload/gpx", files={"file": ("x.gpx", b"pas un gpx")})
print("GPX invalide ->", r.status_code, r.text[:100])

# 2) zip sans activité refusé
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("notes.txt", "rien")
    z.writestr("../evil.fit", "x")
r = requests.post(B + "/api/upload/archive", files=[("files", ("a.zip", buf.getvalue()))])
print("zip sans activité ->", r.status_code, r.text[:100])

# 3) origine étrangère refusée
r = requests.post(B + "/api/upload/archive", headers={"Origin": "http://evil.example"}, files=[("files", ("a.zip", buf.getvalue()))])
print("origine étrangère ->", r.status_code)

# 4) statut
s = requests.get(B + "/api/status").json()
print(json.dumps({k: s[k] for k in ("gpx", "archive")}, ensure_ascii=False)[:400])
