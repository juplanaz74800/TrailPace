"""Emplacements des données de l'utilisateur (tout vit dans data/)."""
import os

DATA = "data"
GPX = f"{DATA}/course.gpx"
FIT_DIR = f"{DATA}/activities"
OSM_CACHE = f"{DATA}/osm_cache.json"
PROFILE_CACHE = f"{DATA}/profile.json"
AIDS = f"{DATA}/aids.json"
SETTINGS = f"{DATA}/settings.json"
NUTRITION = f"{DATA}/nutrition.json"
DEFAULT_SETTINGS = {"window_days": 365}          # 0 = toute l'archive

ACTIVITY_EXT = (".fit", ".tcx", ".gpx")
MAX_FILE_BYTES = 150 * 1024 * 1024
MAX_ZIP_TOTAL = 2 * 1024 ** 3
MAX_ZIP_FILES = 6000


def ensure():
    os.makedirs(FIT_DIR, exist_ok=True)


def remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
