import sys
sys.path.insert(0, ".")
from trailpace import planservice

for q in ({}, {"target_h": 11.0}, {"target_h": 9.0}):
    p = planservice.plan_json(q)
    print(q, "-> total", p["total"], "arrivée", p["finish_clock"], "pct", round(p["pct"], 3),
          "rec", round(p["recommended_pct"], 3), "ref", round(p["pct_ref"], 3), "alt réf", round(p["ref_alt"]), p["weather_source"])
    if not q:
        for s in p["sections"]:
            print(s["n"], round(s["dist_km"], 1), s["time"], round(s["pace_min_km"], 1), s["arrival"], s["clock"], "bar", s["cutoff"],
                  s["cutoff_margin_min"] and round(s["cutoff_margin_min"]), "FC", round(s["hr_target"]),
                  "T", s["temp"] and round(s["temp"], 1), "pluie", s["rain_mm_h"] and round(s["rain_mm_h"], 2),
                  "vent", s["wind_kmh"] and round(s["wind_kmh"]))
