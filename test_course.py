import sys
sys.path.insert(0, ".")
from trailpace.course import analyse

r = analyse(sys.argv[1] if len(sys.argv) > 1 else "data/course.gpx")
print(r["name"], round(r["total_km"], 1), round(r["gain"]), round(r["loss"]), r["alt_min"], r["alt_max"])
for a in r["aid_stations"]:
    print(round(a["km"], 1), a["name"], a["cutoff"])
for s in r["sections"]:
    print(s["n"], round(s["dist_km"], 1), round(s["gain"]), round(s["loss"]), s["from"], "->", s["to"])
print({k: round(v, 1) for k, v in r["dist_by_class"].items()})
for c in r["climbs"]:
    print(c["type"], round(c["start_km"], 1), round(c["dist_km"], 1), round(c["gain"]), round(c["avg_grade"], 1))
