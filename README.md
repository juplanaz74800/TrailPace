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

## Dérive de fatigue (durabilité)

La dérive d'efficience (vitesse perdue à effort égal, par heure après la 1re heure) est propre à chaque profil : mesurée sur les sorties longues
(pente de Theil-Sen de l'efficience vitesse/FC, terrain modéré uniquement). Dans « Plan de course > Hypothèses », l'utilisateur choisit
**sa dérive mesurée** ou une **valeur manuelle**. Par défaut, la mesure n'est reprise que si elle est fiable (intervalle de confiance entièrement du côté de la dérive,
au moins 20 blocs de données) ; sinon la valeur par défaut est de 1,5 %/h. La source est rappelée dans le PDF.

## Puissance et exports

Si les sorties contiennent de la puissance, le plan donne aussi une **puissance cible** par section (W et % de la CP),
adaptée à la pente à partir de tes mesures par type de terrain.
Le plan s'exporte depuis l'onglet « Plan de course » :

- **Fiche PDF** (A4 paysage) : profil avec ravitos et repères horaires, tableau par section (temps, allure, passage, FC, puissance, barrière, météo).
- **GPX avec temps de passage** : trace horodatée selon le plan, ravitos en waypoints (heure de passage, arrêt, allure et puissance de la section suivante).
  L'heure de départ est interprétée dans le fuseau de la machine.

## Nutrition et hydratation

Onglet « Nutrition » (calculateur général, valable pour toute course) :

- **Profil nutrition** : poids, habitudes (g/h en sortie longue), tolérance digestive, caféine, produits réels (glucides, sodium, volume, fructose, part des glucides) et **tests de sudation** (pesées avant/après).
- **Bilan** : volume d'entraînement des 28 derniers jours, besoins quotidiens en glucides (g/kg), dépense estimée, comparaison de l'apport habituel aux repères par durée.
- **Plan par section** : glucides (g/h selon la durée : seuils de la revue Morton et al. 2026, d'après la vidéo Courir Mieux), ratio glucose:fructose conseillé selon la dose,
  quantités de produits, liquide (sudation estimée, jamais au-delà de la sueur) et sodium, avec avertissements ; inclus dans l'export PDF et GPX.

Sources et statut de chaque chiffre : `docs/nutrition_recherche.md`. Les données saisies sont dans `data/nutrition.json` (exclu de git).

## Contenu

- `trailpace/nutrition.py` : calculs nutrition et hydratation

- `trailpace/export.py` : exports PDF et GPX

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
