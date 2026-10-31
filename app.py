"""Serveur local : uvicorn app:app --port 8000"""
import os
from functools import lru_cache
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from trailpace import jobs, manage, planservice, service, store
from trailpace.fit_import import list_files

app = FastAPI(title="Trailpace")


@app.middleware("http")
async def same_origin_only(request: Request, call_next):
    """Les écritures ne sont acceptées que depuis la page de l'application elle-même (anti-CSRF local)."""
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Origine refusée"}, status_code=403)
    return await call_next(request)


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


@app.get("/api/plan")
def plan(start: str = None, pct: float = None, target_h: float = None, aggr: float = 0.0, climb: float = 0.0,
         descent: float = 0.0, drift: float = 1.5, tech_sens: float = 1.0, night: float = 4.0, heat: float = 0.4,
         alt_sens: float = 1.0, stops: str = None):
    if not os.path.exists(store.GPX):
        raise HTTPException(404, "no_gpx")
    if not os.path.exists(store.PROFILE_CACHE):
        raise HTTPException(404, "no_archive")
    q = {"start": start, "pct": pct, "target_h": target_h, "aggr": aggr, "climb": climb, "descent": descent,
         "drift": drift, "tech_sens": tech_sens, "night": night, "heat": heat, "alt_sens": alt_sens,
         "stops_min": [float(x) for x in stops.split(",")] if stops else None}
    return planservice.plan_json(q)


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
