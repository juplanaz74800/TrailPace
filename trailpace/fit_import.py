"""Lecture des activités (FIT, TCX, GPX, éventuellement .gz) et aperçu de l'archive."""
import bisect
import glob
import gzip
import json
import math
import os
import re
import warnings
from datetime import datetime

import fitdecode
import numpy as np
from defusedxml import ElementTree as ET

warnings.filterwarnings("ignore", category=UserWarning, module="fitdecode")   # définitions FIT atypiques, sans effet sur les données

SEMI = 180.0 / 2 ** 31
KEYS = ("t", "dist", "alt", "speed", "hr", "power", "lat", "lon", "cad")
EXT_PRIORITY = {".fit": 0, ".tcx": 1, ".gpx": 2}


def _pack(rec, sport, path):
    """rec : dict de listes (None = valeur manquante) -> (info, tableaux) ou None."""
    if len(rec["t"]) < 60:
        return None
    arr = {k: np.array([np.nan if v is None else v for v in rec[k]], dtype=float) for k in KEYS}
    t0 = arr["t"][0]
    arr["t"] = arr["t"] - t0
    if arr["t"][-1] <= 0:
        return None
    if np.isfinite(arr["lat"]).sum() > 10 and not np.isfinite(arr["dist"]).sum() > 10:
        arr["dist"] = _cum_dist(arr["lat"], arr["lon"])
    if sport in (None, "None", "unknown", "generic"):
        d = arr["dist"]
        v = (np.nanmax(d) / arr["t"][-1]) if np.isfinite(d).any() else 0
        sport = "running" if 1.5 <= v <= 4.4 else "other"      # > 16 km/h de moyenne : plutôt vélo ou véhicule
    return {"file": os.path.basename(path), "start": float(t0), "sport": str(sport),
            "duration_s": float(arr["t"][-1]), "n": len(arr["t"])}, arr


def _cum_dist(lat, lon):
    ok = np.isfinite(lat) & np.isfinite(lon)
    la, lo = np.interp(np.arange(len(lat)), np.where(ok)[0], lat[ok]), np.interp(np.arange(len(lat)), np.where(ok)[0], lon[ok])
    kx = 111320 * math.cos(math.radians(float(np.nanmean(la))))
    d = np.hypot(np.diff(la) * 111320, np.diff(lo) * kx)
    d[d > 100] = 0          # sauts GPS
    return np.concatenate([[0], np.cumsum(d)])


def _open(path):
    return gzip.open(path, "rb") if path.lower().endswith(".gz") else open(path, "rb")


def _base_ext(path):
    p = path.lower()
    if p.endswith(".gz"):
        p = p[:-3]
    return os.path.splitext(p)[1]


def read_fit(path):
    rec = {k: [] for k in KEYS}
    sport = None
    try:
        with _open(path) as f, fitdecode.FitReader(f, check_crc=fitdecode.CrcCheck.DISABLED) as fr:
            for frame in fr:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue
                if frame.name in ("sport", "session") and sport is None:
                    sport = frame.get_value("sport", fallback=None)
                if frame.name != "record":
                    continue
                d = {fl.name: fl.value for fl in frame.fields}      # un seul passage sur les champs
                ts = d.get("timestamp")
                if ts is None:
                    continue
                g = d.get
                rec["t"].append(ts.timestamp())
                rec["dist"].append(g("distance"))
                alt = g("enhanced_altitude")
                rec["alt"].append(alt if alt is not None else g("altitude"))
                sp = g("enhanced_speed")
                rec["speed"].append(sp if sp is not None else g("speed"))
                rec["hr"].append(g("heart_rate"))
                rec["power"].append(g("power"))
                la, lo = g("position_lat"), g("position_long")
                rec["lat"].append(la * SEMI if la is not None else None)
                rec["lon"].append(lo * SEMI if lo is not None else None)
                rec["cad"].append(g("cadence"))
    except Exception:
        return None
    return _pack(rec, sport, path)


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _ts(txt):
    return datetime.fromisoformat(txt.strip().replace("Z", "+00:00")).timestamp()


def _num(txt):
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None


def read_gpx(path):
    rec = {k: [] for k in KEYS}
    sport = None
    try:
        with _open(path) as f:
            root = ET.parse(f).getroot()
        for el in root.iter():
            tag = _local(el.tag)
            if tag == "type" and sport is None and el.text:
                sport = "running" if "run" in el.text.lower() or "trail" in el.text.lower() else el.text.strip().lower()
            if tag != "trkpt":
                continue
            vals = {"alt": None, "t": None, "hr": None, "power": None, "cad": None}
            for ch in el.iter():
                n = _local(ch.tag)
                if n == "ele":
                    vals["alt"] = _num(ch.text)
                elif n == "time" and ch.text:
                    vals["t"] = _ts(ch.text)
                elif n in ("hr", "heartrate"):
                    vals["hr"] = _num(ch.text)
                elif n in ("power", "watts"):
                    vals["power"] = _num(ch.text)
                elif n in ("cad", "cadence"):
                    vals["cad"] = _num(ch.text)
            if vals["t"] is None:
                continue
            rec["t"].append(vals["t"]); rec["alt"].append(vals["alt"]); rec["hr"].append(vals["hr"])
            rec["power"].append(vals["power"]); rec["cad"].append(vals["cad"])
            rec["lat"].append(_num(el.get("lat"))); rec["lon"].append(_num(el.get("lon")))
            rec["dist"].append(None); rec["speed"].append(None)
    except Exception:
        return None
    return _pack(rec, sport, path)


def read_tcx(path):
    rec = {k: [] for k in KEYS}
    sport = None
    try:
        with _open(path) as f:
            root = ET.parse(f).getroot()
        for el in root.iter():
            tag = _local(el.tag)
            if tag == "activity" and sport is None:
                s = (el.get("Sport") or "").lower()
                sport = "running" if s == "running" else "cycling" if s == "biking" else s or None
            if tag != "trackpoint":
                continue
            v = {k: None for k in KEYS}
            for ch in el.iter():
                n = _local(ch.tag)
                if n == "time" and ch.text:
                    v["t"] = _ts(ch.text)
                elif n == "latitudedegrees":
                    v["lat"] = _num(ch.text)
                elif n == "longitudedegrees":
                    v["lon"] = _num(ch.text)
                elif n == "altitudemeters":
                    v["alt"] = _num(ch.text)
                elif n == "distancemeters":
                    v["dist"] = _num(ch.text)
                elif n == "value" and _local(el.tag) == "trackpoint":
                    v["hr"] = v["hr"] if v["hr"] is not None else _num(ch.text)
                elif n == "watts":
                    v["power"] = _num(ch.text)
                elif n in ("cadence", "runcadence"):
                    v["cad"] = _num(ch.text)
            if v["t"] is None:
                continue
            for k in KEYS:
                rec[k].append(v[k])
    except Exception:
        return None
    return _pack(rec, sport, path)


def read_activity(path):
    ext = _base_ext(path)
    return {".fit": read_fit, ".gpx": read_gpx, ".tcx": read_tcx}.get(ext, lambda p: None)(path)


def summarize(info, a):
    d = a["dist"]
    dist_km = float(np.nanmax(d) / 1000) if np.isfinite(d).any() else 0.0
    alt = a["alt"]
    gain = 0.0
    if np.isfinite(alt).sum() > 10:
        from .course import smooth, gain_loss
        ok = np.nan_to_num(alt, nan=np.nanmean(alt))
        gain, _ = gain_loss(smooth(ok, 9), 3.0)
    return {**info, "dist_km": dist_km, "gain": gain,
            "has_hr": bool(np.isfinite(a["hr"]).mean() > 0.8),
            "has_power": bool(np.isfinite(a["power"]).mean() > 0.8),
            "has_gps": bool(np.isfinite(a["lat"]).mean() > 0.8),
            "avg_hr": float(np.nanmean(a["hr"])) if np.isfinite(a["hr"]).any() else None}


def list_files(folder):
    files = [p for p in glob.glob(os.path.join(folder, "*")) if _base_ext(p) in EXT_PRIORITY]
    return sorted(files, key=lambda p: (EXT_PRIORITY[_base_ext(p)], p))


def quick_start(path):
    """Date de début d'une activité (epoch) lue sans décoder tout le fichier ; None si introuvable."""
    try:
        if _base_ext(path) == ".fit":
            with _open(path) as f, fitdecode.FitReader(f) as fr:
                for i, frame in enumerate(fr):
                    if i > 300:
                        break
                    if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                        continue
                    if frame.name == "file_id":
                        t = frame.get_value("time_created", fallback=None)
                    elif frame.name in ("record", "session", "lap", "event"):
                        t = frame.get_value("timestamp", fallback=None) or frame.get_value("start_time", fallback=None)
                    else:
                        continue
                    if t:
                        return t.timestamp()
            return None
        with _open(path) as f:
            head = f.read(65536).decode("utf-8", "ignore")
        m = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", head)
        if m:
            txt = m.group(0)
            return _ts(txt if re.search(r"(Z|[+-]\d{2}:?\d{2})$", txt) else txt + "Z")
    except Exception:
        pass
    return None


def _load_one(path):
    r = read_activity(path)
    if r is None:
        return None
    info, a = r
    return summarize(info, a), a


def _workers(n_files):
    return max(1, min(8, (os.cpu_count() or 2) - 1, n_files // 8))


START_CACHE = "data/.start_cache.json"


def _start_one(path):
    return quick_start(path)


def read_starts(files):
    """Dates de début de tous les fichiers : cache disque (nom, taille, date de modification) + lecture parallèle des nouveaux."""
    cache = {}
    if os.path.exists(START_CACHE):
        try:
            with open(START_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    sig = {p: (os.path.getsize(p), int(os.path.getmtime(p))) for p in files}
    todo = [p for p in files if cache.get(os.path.basename(p), [None])[:2] != list(sig[p])]
    if todo:
        n = _workers(len(todo))
        res = None
        if n > 1:
            try:
                from concurrent.futures import ProcessPoolExecutor
                with ProcessPoolExecutor(n) as ex:
                    res = list(ex.map(_start_one, todo, chunksize=16))
            except Exception:
                res = None
        if res is None:
            res = [quick_start(p) for p in todo]
        for p, st in zip(todo, res):
            cache[os.path.basename(p)] = [sig[p][0], sig[p][1], st]
        try:
            os.makedirs(os.path.dirname(START_CACHE), exist_ok=True)
            with open(START_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except OSError:
            pass
    return {p: cache[os.path.basename(p)][2] for p in files}


def select_recent(files, days):
    """Garde les fichiers dont le départ est dans les `days` jours précédant l'activité la plus récente,
    et écarte les doublons (même départ à 60 s près ; l'ordre de `files` donne la priorité : FIT d'abord).
    Un fichier sans date lisible est conservé et filtré après décodage."""
    starts = read_starts(files)
    known = [s for s in starts.values() if s]
    ref = max(known) if known and days else None
    cutoff = ref - days * 86400 if ref else None
    kept, seen = [], []
    for p in files:
        st = starts[p]
        if st is not None:
            if cutoff is not None and st < cutoff:
                continue
            i = bisect.bisect_left(seen, st)
            if any(abs(st - seen[j]) < 60 for j in (i - 1, i) if 0 <= j < len(seen)):
                continue
            seen.insert(i, st)
        kept.append(p)
    return kept, cutoff, ref


def load_archive(folder, progress=None, days=None, meta=None):
    """Charge les activités du dossier (optionnellement les `days` derniers jours), en parallèle.

    Ignore les doublons (même départ et même durée, FIT prioritaire). `meta` (dict) reçoit le détail du filtrage."""
    all_files = list_files(folder)
    if progress:
        progress(0.0, "Recherche des dates des activités…")
    files, cutoff, ref = select_recent(all_files, days)
    if meta is not None:
        meta.update(total_files=len(all_files), selected_files=len(files), cutoff=cutoff, ref=ref)
    results = None
    n = _workers(len(files))
    if n > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(n) as ex:
                results = []
                for i, r in enumerate(ex.map(_load_one, files, chunksize=4)):
                    results.append(r)
                    if progress and i % 20 == 0:
                        progress(i / max(len(files), 1), f"Lecture des activités ({i}/{len(files)})…")
        except Exception:
            results = None          # repli sur la lecture en série
    if results is None:
        results = []
        for i, p in enumerate(files):
            if progress and i % 20 == 0:
                progress(i / max(len(files), 1), f"Lecture des activités ({i}/{len(files)})…")
            results.append(_load_one(p))
    acts, kept = [], []
    for r in results:
        if r is None:
            continue
        s, a = r
        if cutoff is not None and s["start"] < cutoff:
            continue
        if any(abs(s["start"] - k) < 120 and abs(s["duration_s"] - d) < 120 for k, d in kept):
            continue
        kept.append((s["start"], s["duration_s"]))
        acts.append((s, a))
    if meta is not None:
        meta["loaded"] = len(acts)
    if progress:
        progress(1.0)
    return acts
