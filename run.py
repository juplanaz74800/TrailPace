"""Lance Trailpace : python run.py  (puis ouvrir http://localhost:8000)

Se place dans le dossier du projet, quel que soit l'endroit d'où il est lancé : les données (data/) et
l'interface (static/) sont cherchées par rapport à ce dossier."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

if __name__ == "__main__":      # nécessaire au multiprocessing sous Windows
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
