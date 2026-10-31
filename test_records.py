"""Diagnostic : quelles activités produisent les meilleurs efforts de 20 min ? (outil de développement)"""
import sys

sys.path.insert(0, ".")
import numpy as np

from trailpace import fit_import as F
from trailpace import profile as P

if __name__ == "__main__":
    acts = F.load_archive("data/activities", days=365)
    runs = [(s, a) for s, a in acts if s["sport"] == "running" and s["has_gps"] and s["duration_s"] > 600]
    print(len(acts), "activités,", len(runs), "courses")
    rows = []
    for s, a in runs:
        g = P.to_1hz(a)
        v = np.diff(g["dist"], prepend=g["dist"][0])
        ok = np.isfinite(v) & (v >= 0) & (v < 8)
        vv = np.where(ok, v, 0.0)
        m, i = P.mean_max(vv, 1200)
        if m:
            hr = g["hr"][i:i + 1200]
            rows.append((m * 3.6, s["file"], s["sport"], F._base_ext(s["file"]), float(np.nanmean(hr)) if np.isfinite(hr).any() else None,
                         s["dist_km"], s["duration_s"] / 60))
    rows.sort(reverse=True)
    for r in rows[:8]:
        print(f"{r[0]:5.1f} km/h brut 20 min | FC {r[4] and round(r[4])} | {r[3]} {r[1][:34]:34s} | {r[5]:.1f} km en {r[6]:.0f} min")
