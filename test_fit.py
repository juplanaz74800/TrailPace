import sys
sys.path.insert(0, ".")
from datetime import datetime
from trailpace.fit_import import load_archive

acts = load_archive("data/activities")
print(len(acts), "activités exploitables")
rows = sorted(acts, key=lambda x: x[0]["start"])
for s, _ in rows:
    print(datetime.fromtimestamp(s["start"]).strftime("%Y-%m-%d"), f"{s['dist_km']:6.1f}km", f"D+{s['gain']:5.0f}",
          f"{s['duration_s']/3600:4.1f}h", "HR" if s["has_hr"] else "--", "PW" if s["has_power"] else "--",
          "GPS" if s["has_gps"] else "---", s["sport"][:10], s["file"][:40])
