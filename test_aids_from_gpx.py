"""Projette les waypoints d'un autre GPX (ravitos, barrières) sur la trace courante (data/course.gpx)."""
import sys

sys.path.insert(0, ".")
from trailpace import course as C

cur = C.analyse("data/course.gpx", aids_override=[])
print(f"trace courante : {cur['name']} · {cur['total_km']:.1f} km · D+ {cur['gain']:.0f} m")

old = sys.argv[1]
name, lat, lon, ele, d, wps = C.load_gpx(old)
print(f"autre GPX : {name} · {d[-1] / 1000:.1f} km · {len(wps)} waypoints")
wp = C.project_waypoints(cur["lat"], cur["lon"], cur["grid_m"], [(a, b, n) for a, b, n in wps])
for w in wp:
    print(f"  km {w['km']:6.1f}  écart à la trace {w['off_track_m']:6.0f} m  {w['kind']:6s} {w['name']}")
