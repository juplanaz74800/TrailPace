import sys
import numpy as np
sys.path.insert(0, ".")
from collections import Counter
from trailpace.course import analyse
from trailpace.osm import fetch_ways, technicality

r = analyse(sys.argv[1] if len(sys.argv) > 1 else "data/course.gpx")
lat, lon = r["lat"], r["lon"]

ways = fetch_ways(lat, lon, "data/osm_cache.json")
print("ways:", len(ways))
f, t = technicality(lat, lon, ways)
print("moyenne facteur:", f.mean().round(3), "non apparié:", (np.array(t) == "?").mean().round(3))
print(Counter(t).most_common(10))
