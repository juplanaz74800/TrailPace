"""Exécute le calcul du profil hors serveur, avec trace de la progression (outil de développement)."""
import sys
import time

sys.path.insert(0, ".")
from trailpace import service

if __name__ == "__main__":
    t0 = time.time()
    last = [None]

    def rep(p=None, m=None, final=False):
        if m != last[0]:
            print(f"{time.time() - t0:6.1f} s  {p if p is None else round(p, 3)}  {m}", flush=True)
            last[0] = m

    f = service.profile_json(force=True, progress=rep)
    print(f"{time.time() - t0:6.1f} s  terminé :", {k: f[k] for k in ("n_runs", "span_days", "longest_h", "hrmax", "cs_kmh", "cp_w", "files_total", "files_selected", "window_days")})
    print(f["durability"])
