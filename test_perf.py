"""Mesure : filtrage par date puis lecture parallèle de l'archive (data/activities)."""
import sys
import time
from datetime import datetime

sys.path.insert(0, ".")
from trailpace.fit_import import list_files, load_archive, select_recent

if __name__ == "__main__":          # nécessaire pour le multiprocessing sous Windows
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    files = list_files("data/activities")
    t = time.time()
    sel, cutoff, ref = select_recent(files, days)
    print(f"{len(files)} fichiers ; dates lues en {time.time() - t:.1f} s ; retenus : {len(sel)}"
          f" (du {datetime.fromtimestamp(cutoff):%Y-%m-%d} au {datetime.fromtimestamp(ref):%Y-%m-%d})")
    meta = {}
    t = time.time()
    acts = load_archive("data/activities", days=days, meta=meta)
    print(f"lecture : {time.time() - t:.1f} s ; activités chargées : {len(acts)} ; meta : {meta}")
    from collections import Counter
    print(Counter(s["sport"] for s, _ in acts).most_common(6))
