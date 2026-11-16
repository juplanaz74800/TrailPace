"""Serveur local : uvicorn app:app --port 8000"""
import os
from functools import lru_cache
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from trailpace import export, jobs, manage, nutrition, planservice, service, store
from trailpace.fit_import import list_files

app = FastAPI(title="Trailpace")


@app.middleware("http")
async def same_origin_only(request: Request, call_next):
    """Les écritures ne sont acceptées que depuis la page de l'application elle-même (anti-CSRF local)."""
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Origine refusée"}, status_code=403)
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"      # l'interface est revalidée à chaque chargement (mises à jour visibles)
    return response


@lru_cache(maxsize=1)
def _course():
    return service.course_json()


def _clear():
    _course.cache_clear()
    planservice._course_full.cache_clear()


manage.ON_CHANGE.append(_clear)


@app.on_event("startup")
def startup():
    store.ensure()
    if os.path.exists(store.GPX) and not os.path.exists(store.OSM_CACHE):
        jobs.start("course", manage.prepare_course)
    if list_files(store.FIT_DIR) and not os.path.exists(store.PROFILE_CACHE):
        jobs.start("profile", manage.prepare_profile)


# ---------------------------------------------------------------- lecture
@app.get("/api/course")
def course():
    if not os.path.exists(store.GPX):
        raise HTTPException(404, "no_gpx")
    return _course()


@app.get("/api/profile")
def profile():
    if not os.path.exists(store.PROFILE_CACHE):
        raise HTTPException(404, "profile_pending" if jobs.JOBS.get("profile", {}).get("state") == "running" else "no_archive")
    return service.profile_json()


def _plan_query(start: str = None, pct: float = None, target_h: float = None, aggr: float = 0.0, climb: float = 0.0,
                descent: float = 0.0, drift: float = None, drift_src: str = None, tech_sens: float = 1.0, night: float = 4.0, heat: float = 0.4,
                alt_sens: float = 1.0, stops: str = None):
    """Paramètres du plan (communs à l'affichage et aux exports)."""
    if not os.path.exists(store.GPX):
        raise HTTPException(404, "no_gpx")
    if not os.path.exists(store.PROFILE_CACHE):
        raise HTTPException(404, "no_archive")
    try:
        stops_min = [float(x) for x in stops.split(",")] if stops else None
    except ValueError:
        raise HTTPException(400, "Temps d'arrêt invalides.")
    return {"start": start, "pct": pct, "target_h": target_h, "aggr": aggr, "climb": climb, "descent": descent,
            "drift": drift, "drift_src": drift_src, "tech_sens": tech_sens, "night": night, "heat": heat, "alt_sens": alt_sens,
            "stops_min": stops_min}


@app.get("/api/plan")
def plan(q: dict = Depends(_plan_query)):
    return planservice.plan_json(q)


def _nutrition_for(p, carb, fluid_pct, na_pct):
    prof = nutrition.load_profile()
    return nutrition.build(p, prof, carb, fluid_pct, na_pct), prof


@app.get("/api/plan/export/{fmt}")
def plan_export(fmt: str, q: dict = Depends(_plan_query), nut: int = 1, carb: float = None, fluid_pct: float = 70.0,
                na_pct: float = 40.0):
    """Exporte le plan : fiche PDF imprimable ou GPX avec heures de passage (nutrition incluse si le profil nutrition existe)."""
    if fmt not in ("pdf", "gpx"):
        raise HTTPException(404, "Format inconnu (pdf ou gpx).")
    p = planservice.plan_json(q)
    nut_plan = _nutrition_for(p, carb, fluid_pct, na_pct)[0] if nut and os.path.exists(store.NUTRITION) else None
    if fmt == "pdf":
        body, media = export.plan_pdf(p, nut_plan), "application/pdf"
    else:
        body, media = export.plan_gpx(p, nut_plan).encode("utf-8"), "application/gpx+xml"
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{export.filename(p, fmt)}"'})


@app.get("/api/nutrition/profile")
def nutrition_profile():
    return nutrition.load_profile()


@app.get("/api/nutrition/catalog")
def nutrition_catalog():
    return nutrition.load_catalog()


@app.post("/api/nutrition/catalog")
def upload_catalog(file: UploadFile = File(...)):
    """Remplace le catalogue par le CSV de l'utilisateur (enregistré dans data/catalog.csv)."""
    try:
        n, ignored = nutrition.save_catalog_csv(file.file.read(2 * 1024 * 1024 + 1))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"products": n, "ignored_lines": ignored}


@app.delete("/api/nutrition/catalog")
def reset_catalog():
    nutrition.reset_catalog()
    return nutrition.load_catalog()["file"]


@app.get("/api/nutrition/defaults")
def nutrition_defaults():
    return {"products": nutrition.DEFAULT_PRODUCTS}


@app.put("/api/nutrition/profile")
async def put_nutrition_profile(request: Request):
    try:
        return nutrition.save_profile(await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/nutrition/plan")
def nutrition_plan(q: dict = Depends(_plan_query), carb: float = None, fluid_pct: float = 70.0, na_pct: float = 40.0):
    """Plan nutrition par section, bilan de l'athlète et avertissements pour le plan de course courant."""
    p = planservice.plan_json(q)
    nut, prof = _nutrition_for(p, carb, fluid_pct, na_pct)
    sessions = service.profile_json().get("sessions", [])
    return {"race": {"total": p["total"], "total_s": p["total_s"], "finish_clock": p["finish_clock"], "course_name": p["course_name"]},
            "nutrition": nut, "bilan": nutrition.bilan(prof, sessions, p["total_s"] / 3600),
            "default_carb": nutrition.default_carb_target(p["total_s"] / 3600, prof.get("habit_g_h"))}


@app.get("/api/status")
def status():
    return manage.status()


# ---------------------------------------------------------------- dépôts
@app.post("/api/upload/gpx")
def upload_gpx(file: UploadFile = File(...)):
    try:
        info = manage.save_gpx(file.file, file.filename or "course.gpx")
    except manage.UploadError as e:
        raise HTTPException(400, str(e))
    jobs.start("course", manage.prepare_course)
    return info


@app.post("/api/upload/archive")
def upload_archive(files: list[UploadFile] = File(...), replace: bool = Form(False)):
    try:
        res = manage.save_archive([(f.filename or "", f.file) for f in files], replace=replace)
    except manage.UploadError as e:
        raise HTTPException(400, str(e))
    res["started"] = jobs.start("profile", manage.prepare_profile)
    return res


@app.put("/api/settings")
async def put_settings(request: Request):
    body = await request.json()
    try:
        manage.set_window(int(body.get("window_days")))
    except (manage.UploadError, TypeError, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"started": jobs.start("profile", manage.prepare_profile)}


@app.post("/api/recompute")
def recompute():
    started = {"profile": jobs.start("profile", manage.prepare_profile)}
    if os.path.exists(store.GPX):
        started["course"] = jobs.start("course", manage.prepare_course)
    return started


@app.delete("/api/archive")
def delete_archive():
    manage.clear_archive()
    return {"ok": True}


# ---------------------------------------------------------------- ravitos
@app.get("/api/aids")
def get_aids():
    if not os.path.exists(store.GPX):
        raise HTTPException(404, "no_gpx")
    return manage.get_aids()


@app.put("/api/aids")
async def put_aids(request: Request):
    try:
        manage.set_aids(await request.json())
    except manage.UploadError as e:
        raise HTTPException(400, str(e))
    return manage.get_aids()


@app.delete("/api/aids")
def reset_aids():
    manage.reset_aids()
    return manage.get_aids()


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
