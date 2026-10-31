# Trailpace

Planification de l'allure d'une course trail/ultra à partir d'une trace GPX, du profil de l'athlète
(archive d'activités FIT/GPX/TCX), de la technicité du terrain (OpenStreetMap) et de la météo (Open-Meteo).

## Lancer

```bash
pip install -r requirements.txt
python run.py
```

Puis ouvrir http://localhost:8000 et déposer le GPX et l'archive dans l'onglet « Mes données ».

## Grosses archives

Le profil n'utilise par défaut que les **12 derniers mois** de l'archive (réglable : 6 mois, 12 mois, 2 ans, tout).
Les fichiers hors période sont écartés avant décodage (date lue rapidement, mise en cache dans `data/.start_cache.json`),
les doublons FIT/TCX/GPX d'une même sortie sont ignorés, et la lecture se fait en parallèle.
Exemple : 5 050 fichiers → 436 retenus, profil calculé en environ 30 s.
Les records (CS/CP) exigent un effort réel (FC moyenne ≥ 70 % de la FCmax) en terrain plat ou montant.

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
