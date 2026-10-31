import sys
sys.path.insert(0, ".")
import numpy as np
from trailpace.fit_import import load_archive
from trailpace import profile as P

acts = [(s, a) for s, a in load_archive("data/activities")
        if s["sport"] == "running" and s["has_gps"] and s["duration_s"] > 600]
print(len(acts), "sorties running avec GPS")
wl = [(s, P.windows(a)) for s, a in acts]
wl = [(s, w) for s, w in wl if w is not None]
hrmax = P.estimate_hrmax([w for _, w in wl])
print("FCmax estimée (99.8e percentile):", round(hrmax))
prof = P.grade_profile([w for _, w in wl], hrmax)
for r in prof:
    if r["speed_kmh"] is None:
        print(f"{r['label']:26s} données insuffisantes ({r['n_min']:.0f} min)")
    else:
        print(f"{r['label']:26s} {r['n_min']:5.0f} min  {r['speed_kmh']:5.1f} km/h  FC{r['hr']:4.0f}  "
              f"attendu {r['expected_kmh']:5.1f}  idx {r['index']:.2f}  rel {r['index_rel']:.2f}  "
              f"VAM {r['vam'] if r['vam'] else 0:5.0f}  P {r['power'] or 0:4.0f}W")
g1 = [P.to_1hz(a) for s, a in acts]
cm = P.critical_model(g1)
print({k: round(v, 2) for k, v in cm["gap"].items()})
print({k: round(v) for k, v in cm["power"].items()})
print("CS (GAP) m/s:", round(cm.get("gap_cs", 0), 2), "km/h", round(cm.get("gap_cs", 0) * 3.6, 1), "D'", round(cm.get("gap_dprime", 0)))
print("CP W:", round(cm.get("power_cs", 0)), "W'", round(cm.get("power_dprime", 0)))
print("FC aux meilleurs efforts:", {k: (round(v) if v else None) for k, v in cm["hr_at_best"].items()})
per, agg = P.durability(wl, hrmax)
for p in per:
    print(f"{p['file'][:40]:40s} {p['dur_h']:.1f}h blocs {p['n_blocks']:2d} pente {p['pct_per_h']:+.1f} %/h [{p['ci_lo']:+.1f}; {p['ci_hi']:+.1f}]")
print(agg)
