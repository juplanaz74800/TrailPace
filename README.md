# Trailpace

Planification de l'allure d'une course trail/ultra à partir d'une trace GPX, du profil de l'athlète
(archive d'activités FIT/GPX/TCX), de la technicité du terrain (OpenStreetMap) et de la météo (Open-Meteo).

## Lancer

```bash
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

Puis ouvrir http://localhost:8000 et déposer le GPX et l'archive dans l'onglet « Mes données ».

## Contenu

- `trailpace/course.py` : analyse du parcours (profil, pentes, sections, ravitos)
- `trailpace/osm.py` : technicité déduite d'OpenStreetMap (Overpass)
- `trailpace/fit_import.py` : lecture FIT / GPX / TCX
- `trailpace/profile.py` : vitesse par pente, vitesse/puissance critique, durabilité (Theil-Sen)
- `trailpace/plan.py`, `planservice.py` : moteur de plan de course
- `trailpace/weather.py` : prévisions ou climatologie Open-Meteo
- `trailpace/manage.py`, `jobs.py`, `store.py` : dépôts de fichiers et tâches de fond
- `static/` : interface web

## Données personnelles

Tout ce que dépose l'utilisateur vit dans `data/`, exclu de git (`.gitignore`) :
activités avec GPS et fréquence cardiaque, profil calculé, caches.

## Limites connues

Plusieurs coefficients sont des hypothèses à calibrer (% de vitesse critique selon la durée, ralentissement de nuit,
dérive de fatigue). Altitude : Wehrlin & Hallén 2006. Chaleur : Ely et al. 2007. Voir les notes dans l'interface.
