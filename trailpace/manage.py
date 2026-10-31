"""Dépôt et gestion des fichiers de l'utilisateur : GPX de course, archive d'activités, ravitos."""
import json
import os
import re
import shutil
import zipfile

from . import course as C
from . import jobs
from . import osm as O
from . import service
from . import store
from .fit_import import _base_ext, list_files

ON_CHANGE = []          # fonctions à appeler quand les données changent (vidage des caches)
_summary = {}


def invalidate():
    _summary.clear()
    for fn in ON_CHANGE:
        fn()


class UploadError(ValueError):
    pass


def _safe_name(name):
    base = os.path.basename(name.replace("\\", "/"))
    base = re.sub(r"[^\w.\-]+", "_", base).strip("._") or "fichier"
    return base[:120]


def _unique(folder, name):
    root, ext = os.path.splitext(name)
    p, i = os.path.join(folder, name), 1
    while os.path.exists(p):
        p = os.path.join(folder, f"{root}_{i}{ext}")
        i += 1
    return p


def _copy_capped(src, dest, cap):
    """Copie par blocs ; abandonne (et supprime) au-delà de la taille maximale."""
    n = 0
    with open(dest, "wb") as out:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            n += len(chunk)
            if n > cap:
                out.close()
                os.remove(dest)
                return False
            out.write(chunk)
    return True


# ---------------------------------------------------------------- GPX de course
def save_gpx(fileobj, filename):
    os.makedirs(store.DATA, exist_ok=True)
    tmp = os.path.join(store.DATA, "course.upload.tmp")
    if not _copy_capped(fileobj, tmp, 30 * 1024 * 1024):
        raise UploadError("Fichier GPX trop volumineux (maximum 30 Mo).")
    try:
        name, lat, lon, ele, d, wps = C.load_gpx(tmp)
    except Exception as e:
        store.remove(tmp)
        raise UploadError(f"GPX illisible : {e}")
    import numpy as np
    if len(lat) < 50 or d[-1] < 1000:
        store.remove(tmp)
        raise UploadError("La trace est trop courte ou vide (aucun point de parcours trouvé).")
    if np.isnan(ele).mean() > 0.2:
        store.remove(tmp)
        raise UploadError("Ce GPX n'a pas d'altitude : le profil et le plan de course en ont besoin.")
    os.replace(tmp, store.GPX)
    store.remove(store.OSM_CACHE)       # la technicité est propre à la trace
    store.remove(store.AIDS)            # nouveaux ravitos à détecter
    invalidate()
    return {"name": name, "km": float(d[-1] / 1000), "points": int(len(lat)), "waypoints": len(wps)}


# ---------------------------------------------------------------- archive d'activités
def _accepted(low):
    return _base_ext(low) in store.ACTIVITY_EXT


def _extract_zip(fileobj):
    saved = skipped = 0
    total = 0
    try:
        zf = zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile:
        raise UploadError("Archive zip invalide ou corrompue.")
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > store.MAX_ZIP_FILES:
        raise UploadError(f"Archive trop grosse ({len(infos)} fichiers, maximum {store.MAX_ZIP_FILES}).")
    for info in infos:
        low = info.filename.lower()
        if not _accepted(low) or info.file_size > store.MAX_FILE_BYTES:
            skipped += 1
            continue
        total += info.file_size
        if total > store.MAX_ZIP_TOTAL:
            raise UploadError("Archive trop volumineuse une fois décompressée (maximum 2 Go).")
        dest = _unique(store.FIT_DIR, _safe_name(info.filename))   # on ne reprend jamais le chemin de l'archive
        with zf.open(info) as src:
            if _copy_capped(src, dest, store.MAX_FILE_BYTES):
                saved += 1
            else:
                skipped += 1
    return saved, skipped


def save_archive(items, replace=False):
    """items : [(nom, fichier)] — .zip, .fit, .gpx, .tcx (et .gz de ceux-ci)."""
    store.ensure()
    if replace:
        for p in list_files(store.FIT_DIR):
            os.remove(p)
    saved = skipped = 0
    for name, f in items:
        low = name.lower()
        if low.endswith(".zip"):
            s, k = _extract_zip(f)
        elif _accepted(low):
            dest = _unique(store.FIT_DIR, _safe_name(name))
            s, k = (1, 0) if _copy_capped(f, dest, store.MAX_FILE_BYTES) else (0, 1)
        else:
            s, k = 0, 1
        saved += s
        skipped += k
    if saved == 0:
        raise UploadError("Aucune activité (.fit, .gpx, .tcx) trouvée dans ce dépôt.")
    store.remove(store.PROFILE_CACHE)
    invalidate()
    return {"saved": saved, "skipped": skipped}


def clear_archive():
    for p in list_files(store.FIT_DIR):
        os.remove(p)
    store.remove(store.PROFILE_CACHE)
    invalidate()


# ---------------------------------------------------------------- ravitos
def get_aids():
    r = _course_summary()
    return {"manual": os.path.exists(store.AIDS), "total_km": r["total_km"],
            "aids": [{"name": a["name"], "km": round(a["km"], 2), "cutoff": a.get("cutoff")} for a in r["aid_stations"]]}


def set_aids(aids):
    clean = []
    for a in aids:
        try:
            km = float(a["km"])
        except (KeyError, TypeError, ValueError):
            raise UploadError("Chaque ravito doit avoir une distance (km).")
        if not 0 < km < 1000:
            raise UploadError("Distance de ravito invalide.")
        clean.append({"name": str(a.get("name") or "Ravitaillement")[:60], "km": km, "cutoff": str(a.get("cutoff") or "")[:12]})
    with open(store.AIDS, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False)
    invalidate()


def reset_aids():
    store.remove(store.AIDS)
    invalidate()


# ---------------------------------------------------------------- statut
def _course_summary():
    if "course" not in _summary:
        _summary["course"] = C.analyse(store.GPX, aids_override=service.load_aids())
    return _summary["course"]


def status():
    out = {"jobs": jobs.snapshot(), "gpx": {"present": os.path.exists(store.GPX)}, "archive": {}}
    if out["gpx"]["present"]:
        try:
            r = _course_summary()
            out["gpx"].update(name=r["name"].replace("�", "é"), km=round(r["total_km"], 1), gain=round(r["gain"]),
                              loss=round(r["loss"]), aids=len(r["aid_stations"]), osm=os.path.exists(store.OSM_CACHE),
                              aids_manual=os.path.exists(store.AIDS), mtime=os.path.getmtime(store.GPX))
        except Exception as e:
            out["gpx"]["error"] = str(e)
    files = list_files(store.FIT_DIR) if os.path.isdir(store.FIT_DIR) else []
    exts = {}
    for p in files:
        exts[_base_ext(p)] = exts.get(_base_ext(p), 0) + 1
    out["archive"] = {"files": len(files), "by_type": exts, "profile_ready": os.path.exists(store.PROFILE_CACHE)}
    if out["archive"]["profile_ready"]:
        with open(store.PROFILE_CACHE, encoding="utf-8") as f:
            pr = json.load(f)
        out["archive"].update(n_runs=pr["n_runs"], span_days=pr["span_days"], longest_h=pr["longest_h"],
                              mtime=os.path.getmtime(store.PROFILE_CACHE))
    return out


# ---------------------------------------------------------------- tâches
def prepare_course(report):
    report(0.03, "Analyse de la trace…")
    r = C.analyse(store.GPX, aids_override=service.load_aids())
    if not os.path.exists(store.OSM_CACHE):
        report(0.08, "Téléchargement de la technicité OpenStreetMap…")
        try:
            O.fetch_ways(r["lat"], r["lon"], store.OSM_CACHE, progress=lambda x: report(0.08 + 0.85 * x))
        except Exception:
            report(0.95, "OpenStreetMap indisponible : technicité ignorée pour l'instant (relance le traitement plus tard).", final=True)
    invalidate()


def prepare_profile(report):
    store.remove(store.PROFILE_CACHE)
    service.profile_json(force=True, progress=report)
    invalidate()
