"""Petites tâches de fond (une par nom) avec progression, interrogeables par l'interface."""
import threading
import time

JOBS = {}
_lock = threading.Lock()


def start(name, fn):
    """Lance fn(report) en arrière-plan ; report(progress 0..1, message). Refuse si déjà en cours."""
    with _lock:
        if JOBS.get(name, {}).get("state") == "running":
            return False
        JOBS[name] = {"state": "running", "progress": 0.0, "message": "Démarrage…", "started": time.time()}

    def report(progress=None, message=None, final=False):
        j = JOBS[name]
        if progress is not None:
            j["progress"] = float(progress)
        if message:
            j["message"] = message
            j["final"] = final      # message à conserver tel quel à la fin de la tâche

    def target():
        try:
            fn(report)
            j = JOBS[name]
            j.update(state="done", progress=1.0, ended=time.time(), message=j["message"] if j.get("final") else "Terminé")
        except Exception as e:  # on remonte le message à l'interface
            JOBS[name].update(state="error", message=f"{type(e).__name__}: {e}", ended=time.time())

    threading.Thread(target=target, daemon=True).start()
    return True


def snapshot():
    return {k: dict(v) for k, v in JOBS.items()}
