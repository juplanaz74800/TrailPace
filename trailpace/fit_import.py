"""Lecture des activités (FIT, TCX, GPX, éventuellement .gz) et aperçu de l'archive."""
import glob
import gzip
import math
import os
from datetime import datetime

import fitdecode
import numpy as np
from defusedxml import ElementTree as ET

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
        sport = "running" if 1.5 <= v <= 6.5 else "other"
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
        with _open(path) as f, fitdecode.FitReader(f) as fr:
            for frame in fr:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue
                if frame.name == "sport":
                    sport = frame.get_value("sport", fallback=None)
                if frame.name != "record":
                    continue
                g = lambda n: frame.get_value(n, fallback=None)
                ts = g("timestamp")
                if ts is None:
                    continue
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


def load_archive(folder, progress=None):
    """Charge toutes les activités du dossier ; ignore les doublons (même départ et même durée, FIT prioritaire)."""
    files = list_files(folder)
    acts, kept = [], []
    for i, p in enumerate(files):
        if progress:
            progress(i / max(len(files), 1))
        r = read_activity(p)
        if r is None:
            continue
        info, a = r
        if any(abs(info["start"] - s) < 120 and abs(info["duration_s"] - d) < 120 for s, d in kept):
            continue
        kept.append((info["start"], info["duration_s"]))
        acts.append((summarize(info, a), a))
    if progress:
        progress(1.0)
    return acts
