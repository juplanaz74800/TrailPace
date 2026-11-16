"""Nutrition et hydratation : repères glucides par durée, sudation, sodium, bilan et plan par section.

Sources : voir docs/nutrition_recherche.md. Seuils glucides par durée = revue Morton et al. 2026 (J Nutr), telle que présentée dans
la vidéo « NUTRITION en TRAIL » ; sudation de population = Baker 2016 / Barnes 2019 ; hydratation = ACSM 2007, consensus EAH 2015.
"""
import csv
import io
import json
import math
import os
import re
import statistics
import unicodedata
from datetime import datetime

from . import store

NA_MG_PER_MMOL = 23.0          # 1 mmol de sodium = 23 mg
DEFAULT_SWEAT_NA = 36.0        # mmol/L, sueur du corps entier (Baker 2016 : 35,9 ± 10,4)
DEFAULT_SWEAT_20C = 1.0        # L/h à 20 °C : valeur de repli (population endurance : 1,28 ± 0,57 L/h, conditions variées)

DEFAULT_PRODUCTS = [   # exemples génériques, à remplacer par les produits réels de l'athlète
    {"name": "Boisson glucidique (40 g / 500 mL)", "type": "drink", "carbs_g": 40, "sodium_mg": 300, "volume_ml": 500, "fructose_pct": 33, "share_pct": 50},
    {"name": "Gel (25 g)", "type": "gel", "carbs_g": 25, "sodium_mg": 50, "volume_ml": 0, "fructose_pct": 33, "share_pct": 40},
    {"name": "Gomme / pâte de fruit (20 g)", "type": "chew", "carbs_g": 20, "sodium_mg": 20, "volume_ml": 0, "fructose_pct": 30, "share_pct": 10},
    {"name": "Barre (30 g)", "type": "bar", "carbs_g": 30, "sodium_mg": 100, "volume_ml": 0, "fructose_pct": 20, "share_pct": 0},
    {"name": "Électrolytes (comprimé)", "type": "electrolyte", "carbs_g": 0, "sodium_mg": 300, "volume_ml": 0, "fructose_pct": 0, "share_pct": 0},
]
TYPES = ("drink", "gel", "chew", "bar", "real", "maltodextrin", "electrolyte")

DEFAULT_PROFILE = {"weight_kg": None, "height_cm": None, "age": None, "sex": None, "habit_g_h": None,
                   "gi": "none", "caffeine": "none", "sweat_na_mmol_l": None, "products": DEFAULT_PRODUCTS, "tests": []}


# ------------------------------------------------------------------ catalogue des produits (fichier CSV de l'utilisateur)
CATALOG_BUNDLED = os.path.join(os.path.dirname(__file__), "catalog.csv")
CATALOG_USER = os.path.join(store.DATA, "catalog.csv")          # remplace le fichier fourni s'il existe
CATALOG_ECARTS = os.path.join(os.path.dirname(__file__), "catalog_ecarts.json")
_TYPES = {"boisson": "drink", "boissons": "drink", "gel": "gel", "gels": "gel", "barre": "bar", "barres": "bar", "gomme": "chew", "gommes": "chew",
          "pate": "chew", "pates": "chew", "pate de fruit": "chew", "chews": "chew", "electrolyte": "electrolyte", "electrolytes": "electrolyte",
          "puree": "real", "purees": "real", "aliment": "real", "solide": "real"}
_cache = {}


def _norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()).strip()


def _num_or_none(x):
    x = str(x or "").strip().replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


def _fructose_pct(ratio):
    """Part de fructose (%) déduite d'un ratio chiffré glucose:fructose (2:1, 1:0.8…) ; None si le ratio n'est pas chiffré."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)", str(ratio or ""))
    if not m:
        return None
    g, f = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
    return round(100 * f / (g + f)) if g + f else None


def parse_catalog_csv(text):
    """Convertit le CSV en produits ; lève ValueError si les colonnes indispensables manquent.

    Colonnes : marque, type_produit, nom_produit, glucides_g, sodium_mg (obligatoires) ; id, pays, gamme, portion_g_ml, unite, dilution_ml,
    energie_kcal, dont_sucres_g, proteines_g, ratio_glu_fru, sources_glucides, caffeine_mg, source_url, date_releve, statut (facultatives)."""
    first = text.splitlines()[0] if text.strip() else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    need = {"marque", "type_produit", "nom_produit", "glucides_g", "sodium_mg"}
    if not rows or need - set(rows[0].keys()):
        raise ValueError("Colonnes manquantes : " + ", ".join(sorted(need - set(rows[0].keys() if rows else [])) or ["fichier vide"]))
    ecarts = {}
    if os.path.exists(CATALOG_ECARTS):
        with open(CATALOG_ECARTS, encoding="utf-8") as f:
            ecarts = json.load(f)
    products, ignored, seen = [], 0, {}
    for r in rows:
        name, brand = (r.get("nom_produit") or "").strip(), (r.get("marque") or "").strip()
        cat = _TYPES.get(_norm(r.get("type_produit")))
        if not name or not brand or cat is None:
            ignored += 1
            continue
        qty, unit = (r.get("portion_g_ml") or "").strip(), (r.get("unite") or "g").strip()
        vol = _num_or_none(r.get("dilution_ml"))
        serving = f"{qty} {unit}".strip() + (f" dans {vol:g} mL" if cat in ("drink", "electrolyte") and vol else "")
        pid = (r.get("id") or "").strip() or f"{_norm(brand)}-{_norm(name)}"
        seen[pid] = seen.get(pid, 0) + 1
        extras = []
        if r.get("pays"):
            extras.append(r["pays"].strip())
        kcal, prot, sug = _num_or_none(r.get("energie_kcal")), _num_or_none(r.get("proteines_g")), _num_or_none(r.get("dont_sucres_g"))
        if kcal is not None:
            extras.append(f"{kcal:g} kcal")
        if sug is not None:
            extras.append(f"dont sucres {sug:g} g")
        if prot:
            extras.append(f"protéines {prot:g} g")
        if r.get("sources_glucides"):
            extras.append("glucides : " + r["sources_glucides"].strip())
        ratio = (r.get("ratio_glu_fru") or "").strip()
        if ratio and _fructose_pct(ratio) is None:
            extras.append(f"ratio non chiffré (« {ratio} ») : part de fructose à renseigner")
        note = " · ".join(extras)
        if ecarts.get(pid):
            note += ("\n" if note else "") + "Écart relevé : " + ecarts[pid]
        stat = _norm(r.get("statut"))
        products.append({
            "id": pid if seen[pid] == 1 else f"{pid}-{seen[pid]}", "brand": brand, "gamme": (r.get("gamme") or "").strip(), "category": cat, "name": name,
            "serving": serving, "carbs_g": _num_or_none(r.get("glucides_g")), "sodium_mg": _num_or_none(r.get("sodium_mg")),
            "volume_ml": vol or 0, "fructose_pct": _fructose_pct(ratio), "ratio": ratio, "caffeine_mg": _num_or_none(r.get("caffeine_mg")),
            "source": (r.get("source_url") or "").strip(), "confidence": "verifie" if stat.startswith("verifi") else "base_utilisateur",
            "note": note, "date": (r.get("date_releve") or "").strip(), "country": (r.get("pays") or "").strip()})
    return products, ignored


def load_catalog():
    """Catalogue des produits : data/catalog.csv s'il existe (fichier de l'utilisateur), sinon le fichier fourni avec l'application."""
    path = CATALOG_USER if os.path.exists(CATALOG_USER) else CATALOG_BUNDLED
    mt = os.path.getmtime(path)
    if _cache.get("key") == (path, mt):
        return _cache["val"]
    with open(path, encoding="utf-8-sig") as f:
        products, ignored = parse_catalog_csv(f.read())
    brands = {}
    for p in products:
        b = brands.setdefault(p["brand"], {"site": "", "country": p["country"], "n": 0})
        b["n"] += 1
    for b in brands.values():
        b["coverage"] = f"{b['n']} produit(s) de la base" + (f" ({b['country']})" if b["country"] else "")
    val = {"file": "data/catalog.csv" if path == CATALOG_USER else "fichier fourni (trailpace/catalog.csv)", "ignored_lines": ignored,
           "retrieved": datetime.fromtimestamp(mt).strftime("%Y-%m-%d"),
           "note": "Base de produits de l'utilisateur : valeurs non vérifiées sur emballage, sauf mention contraire. Les compositions changent : vérifie toujours l'emballage. "
                   "Tu peux remplacer le fichier (bouton « Importer mon CSV »).",
           "brands": dict(sorted(brands.items(), key=lambda kv: kv[0].lower())), "gammes": sorted({p["gamme"] for p in products if p["gamme"]}), "products": products}
    _cache.update(key=(path, mt), val=val)
    return val


def save_catalog_csv(raw):
    """Valide et enregistre un CSV de produits envoyé par l'utilisateur (octets) ; retourne le nombre de produits."""
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Fichier trop volumineux (maximum 2 Mo).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", "replace")
    products, ignored = parse_catalog_csv(text)
    if not products:
        raise ValueError("Aucun produit exploitable (types reconnus : Boisson, Gel, Barre, Gomme, Électrolyte, Purée).")
    os.makedirs(store.DATA, exist_ok=True)
    with open(CATALOG_USER, "w", encoding="utf-8") as f:
        f.write(text)
    _cache.clear()
    return len(products), ignored


def reset_catalog():
    store.remove(CATALOG_USER)
    _cache.clear()


# ------------------------------------------------------------------ persistance
def load_profile():
    p = json.loads(json.dumps(DEFAULT_PROFILE))
    if os.path.exists(store.NUTRITION):
        with open(store.NUTRITION, encoding="utf-8") as f:
            p.update(json.load(f))
    return p


def _num(v, lo, hi, name, allow_none=True):
    if v in (None, ""):
        if allow_none:
            return None
        raise ValueError(f"{name} manquant")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} invalide")
    if not lo <= x <= hi:
        raise ValueError(f"{name} doit être entre {lo:g} et {hi:g}")
    return x


def save_profile(data):
    """Valide puis enregistre le profil nutrition (champs inconnus ignorés)."""
    p = load_profile()
    out = {"weight_kg": _num(data.get("weight_kg"), 30, 200, "Poids"), "height_cm": _num(data.get("height_cm"), 120, 230, "Taille"),
           "age": _num(data.get("age"), 10, 100, "Âge"), "sex": data.get("sex") if data.get("sex") in ("f", "m") else None,
           "habit_g_h": _num(data.get("habit_g_h"), 0, 200, "Apport habituel (g/h)"),
           "gi": data.get("gi") if data.get("gi") in ("none", "sometimes", "often") else "none",
           "caffeine": data.get("caffeine") if data.get("caffeine") in ("none", "occasional", "regular") else "none",
           "sweat_na_mmol_l": _num(data.get("sweat_na_mmol_l"), 5, 120, "Sodium de la sueur (mmol/L)")}
    prods = []
    for q in data.get("products", p["products"]):
        if q.get("type") not in TYPES:
            raise ValueError("Type de produit invalide")
        prods.append({"name": str(q.get("name") or "Produit")[:60], "type": q["type"],
                      "carbs_g": _num(q.get("carbs_g") or 0, 0, 200, "Glucides du produit", False),
                      "sodium_mg": _num(q.get("sodium_mg") or 0, 0, 5000, "Sodium du produit", False),
                      "volume_ml": _num(q.get("volume_ml") or 0, 0, 2000, "Volume du produit", False),
                      "fructose_pct": _num(q.get("fructose_pct") or 0, 0, 60, "Fructose (%)", False),
                      "share_pct": _num(q.get("share_pct") or 0, 0, 100, "Part des glucides (%)", False)})
    out["products"] = prods
    tests = []
    for t in data.get("tests", p["tests"]):
        tests.append(clean_test(t))
    out["tests"] = tests
    os.makedirs(store.DATA, exist_ok=True)
    with open(store.NUTRITION, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


def clean_test(t):
    c = {"date": str(t.get("date") or "")[:10], "duration_min": _num(t.get("duration_min"), 20, 600, "Durée du test", False),
         "temp_c": _num(t.get("temp_c"), -30, 50, "Température", False),
         "mass_before_kg": _num(t.get("mass_before_kg"), 30, 200, "Poids avant", False),
         "mass_after_kg": _num(t.get("mass_after_kg"), 30, 200, "Poids après", False),
         "fluid_ml": _num(t.get("fluid_ml") or 0, 0, 10000, "Liquide bu", False), "urine_ml": _num(t.get("urine_ml") or 0, 0, 5000, "Urines", False),
         "avg_power_w": _num(t.get("avg_power_w"), 50, 600, "Puissance moyenne")}
    r = test_rate(c)
    if not 0.1 <= r <= 4.5:
        raise ValueError(f"Sudation calculée de {r:.2f} L/h : vérifie les poids, le liquide bu et la durée")
    return c


# ------------------------------------------------------------------ repères glucides par durée (seuils de la vidéo)
def carb_band(hours):
    """Fourchette glucides (g/h) selon la durée. Revue Morton et al. 2026, via la vidéo [secondaire]."""
    if hours < 1:
        return {"label": "moins de 1 h", "lo": 0, "hi": 0, "note": "pas d'apport nécessaire dans la grande majorité des cas"}
    if hours < 2:
        return {"label": "1 à 2 h", "lo": 30, "hi": 60, "note": "une seule source de glucide suffit (glucose ou maltodextrine)"}
    if hours < 3:
        return {"label": "2 à 3 h", "lo": 60, "hi": 90, "note": "mélange glucose + fructose, ratio 2:1"}
    if hours <= 6:
        return {"label": "3 à 6 h", "lo": 90, "hi": 120, "note": "90 g/h, jusqu'à 120 g/h pour les athlètes préparés et entraînés"}
    return {"label": "plus de 6 h", "lo": 60, "hi": 90, "note": "viser le maximum toléré, au minimum 60 g/h de façon constante"}


def ratio_for(dose):
    """Ratio glucose:fructose conseillé selon la dose et part de fructose attendue (vidéo)."""
    if dose <= 60:
        return {"ratio": "source unique", "fructose": 0.0, "note": "glucose ou maltodextrine seul ; le fructose n'apporte rien en dessous de ~60 g/h"}
    if dose <= 90:
        return {"ratio": "2:1", "fructose": 1 / 3, "note": "glucose (ou maltodextrine) : fructose = 2:1"}
    if dose <= 120:
        return {"ratio": "1:0,8", "fructose": 0.444, "note": "plus de fructose au-dessus de 90 g/h"}
    return {"ratio": "1:1", "fructose": 0.5, "note": "au-delà de 120 g/h"}


def default_carb_target(hours, habit):
    b = carb_band(hours)
    if b["hi"] == 0:
        return 0
    t = (b["lo"] + b["hi"]) / 2
    if habit:                                   # on ne propose pas plus de +20 g/h au-delà de l'habitude (entraînement digestif)
        t = min(t, max(b["lo"], habit + 20))
    return int(round(t / 5.0) * 5)


# ------------------------------------------------------------------ sudation
def test_rate(t):
    """Sudation (L/h) = (poids avant - poids après + liquide bu - urines) / durée."""
    loss = t["mass_before_kg"] - t["mass_after_kg"] + (t.get("fluid_ml", 0) - t.get("urine_ml", 0)) / 1000
    return loss / (t["duration_min"] / 60)


def temp_factor(t):
    """Facteur de température (1,0 à 25 °C). Hypothèse : ~0,5 à 0 °C d'après une étude à 0 et 25 °C (effort modéré), pente linéaire."""
    return max(0.4, min(1.3, 0.5 + 0.02 * t))


def base_sweat(tests):
    """Sudation de référence à 20 °C (L/h) : moyenne des tests ramenés à 20 °C ; valeur de population à défaut."""
    if not tests:
        return DEFAULT_SWEAT_20C, False
    vals = [test_rate(t) / temp_factor(t["temp_c"]) * temp_factor(20) for t in tests]
    return statistics.mean(vals), True


# ------------------------------------------------------------------ bilan d'entraînement
def training_summary(sessions, weight):
    """sessions : liste {start, dur_h, kcal_per_kg} issue du profil (courses à pied) ; fenêtre = 28 jours avant la dernière."""
    if not sessions:
        return None
    last = max(s["start"] for s in sessions)
    rec = [s for s in sessions if s["start"] >= last - 28 * 86400]
    hours = sum(s["dur_h"] for s in rec)
    longs = [s["dur_h"] for s in rec if s["dur_h"] >= 1.5]
    out = {"days": 28, "sessions": len(rec), "hours_week": hours / 4, "hours_day": hours / 28,
           "n_90min": len(longs), "n_2h": sum(1 for s in rec if s["dur_h"] >= 2), "longest_h": max((s["dur_h"] for s in rec), default=0),
           "typical_long_h": statistics.median(longs) if longs else None}
    heavy = out["hours_day"] >= 2
    out["carb_day"] = {"lo": 8 if heavy else 6, "hi": 12 if heavy else 10, "label": "entraînement lourd" if heavy else "entraînement modéré",
                       "src": "Burke 2011 (résumé GSSI) [secondaire]"}
    if weight:
        out["carb_day_g"] = {"lo": round(out["carb_day"]["lo"] * weight), "hi": round(out["carb_day"]["hi"] * weight)}
        out["kcal_week"] = sum(s["kcal_per_kg"] for s in rec) * weight / 4
    return out


def bilan(profile, sessions, race_hours):
    """Bilan de l'athlète : entraînement, habitudes vs repères, points d'attention."""
    w = profile.get("weight_kg")
    ts = training_summary(sessions, w)
    habit = profile.get("habit_g_h")
    items = []
    if ts and ts["typical_long_h"]:
        b = carb_band(ts["typical_long_h"])
        item = {"what": f"sortie longue typique (~{ts['typical_long_h']:.1f} h)", "band": b}
        if habit is not None and b["hi"]:
            item["status"] = "sous" if habit < b["lo"] else "dans" if habit <= b["hi"] else "au-dessus"
        items.append(item)
    if race_hours:
        b = carb_band(race_hours)
        item = {"what": f"course prévue (~{race_hours:.1f} h)", "band": b}
        if habit is not None and b["hi"]:
            item["status"] = "sous" if habit < b["lo"] else "dans" if habit <= b["hi"] else "au-dessus"
            item["gap"] = max(0, b["lo"] - habit)
        items.append(item)
    notes = []
    if profile.get("gi") in ("sometimes", "often"):
        notes.append("Troubles digestifs signalés : monter la dose progressivement en sortie longue (entraînement du tube digestif) "
                     "et éviter protéines, lipides et fibres pendant l'effort.")
    if habit is not None and race_hours and habit < carb_band(race_hours)["lo"]:
        notes.append(f"Ton apport habituel ({habit:g} g/h) est sous le bas de la fourchette pour la durée de la course : "
                     "prévois des sorties longues où tu t'exposes progressivement à la dose cible.")
    if not w:
        notes.append("Renseigne ton poids pour obtenir les besoins en g/kg, la caféine et la dépense estimée.")
    return {"training": ts, "habit_g_h": habit, "items": items, "notes": notes,
            "caffeine_mg": {"lo": round(3 * w), "hi": round(6 * w)} if w else None}


# ------------------------------------------------------------------ plan par section
def build(plan, profile, carb=None, fluid_pct=70.0, na_pct=40.0):
    """Plan nutrition à partir du plan de course (plan_json) et du profil nutrition."""
    hours = plan["total_s"] / 3600
    band = carb_band(hours)
    habit = profile.get("habit_g_h")
    dose = float(carb) if carb is not None else default_carb_target(hours, habit)
    dose = max(0.0, dose)
    rat = ratio_for(dose)

    prods = [p for p in profile["products"] if p["carbs_g"] > 0 and p["share_pct"] > 0]
    tot_share = sum(p["share_pct"] for p in prods)
    shares = {p["name"]: p["share_pct"] / tot_share for p in prods} if tot_share else {}
    fruct = sum(shares[p["name"]] * p["fructose_pct"] / 100 for p in prods) if prods else 0.0

    base, from_tests = base_sweat(profile["tests"])
    tpow = [t["avg_power_w"] for t in profile["tests"] if t.get("avg_power_w")]
    test_power = statistics.mean(tpow) if tpow else None
    na_conc = profile.get("sweat_na_mmol_l") or DEFAULT_SWEAT_NA
    elec = next((p for p in profile["products"] if p["type"] == "electrolyte" and p["sodium_mg"] > 0), None)

    sections, tot = [], {"carbs": 0.0, "fluid": 0.0, "sodium_need": 0.0, "sodium_prod": 0.0, "hours": 0.0, "sweat_l": 0.0}
    per_product = {p["name"]: 0.0 for p in profile["products"]}
    over_drink = False
    all_t = [s["temp"] for s in plan["sections"] if s.get("temp") is not None]
    mean_t = statistics.mean(all_t) if all_t else 15.0
    for s in plan["sections"]:
        h = s["time_s"] / 3600
        temp = s["temp"] if s.get("temp") is not None else mean_t
        pf = 1.0
        if test_power and s.get("power_w"):
            pf = max(0.6, min(1.4, s["power_w"] / test_power))
        sweat = base * temp_factor(temp) / temp_factor(20) * pf          # L/h
        fluid = min(800.0, fluid_pct / 100 * sweat * 1000)                # mL/h, jamais au-delà de la sueur
        na_loss = sweat * na_conc * NA_MG_PER_MMOL                        # mg/h
        grams = dose * h
        drinks_ml = 0.0
        na_prod = 0.0
        lines = []
        for p in prods:
            g = grams * shares[p["name"]]
            n = g / p["carbs_g"]
            per_product[p["name"]] += n
            if p["type"] == "drink":
                drinks_ml += n * p["volume_ml"]
            na_prod += n * p["sodium_mg"]
            lines.append({"name": p["name"], "type": p["type"], "servings": n, "grams": g})
        na_target = na_pct / 100 * na_loss * h
        extra_na = max(0.0, na_target - na_prod)
        tabs = extra_na / elec["sodium_mg"] if elec else None
        if elec:
            per_product[elec["name"]] += tabs
            na_prod += tabs * elec["sodium_mg"]
        fl = fluid * h
        if drinks_ml > fl * 1.02:          # la boisson prévue dépasse la cible de liquide : le total la suit, avec avertissement
            over_drink = True
            fl = drinks_ml
        sections.append({"n": s["n"], "from": s["from"], "to": s["to"], "hours": h, "temp": temp,
                         "carbs_g": grams, "carbs_g_h": dose, "fluid_ml": fl, "fluid_ml_h": fl / h if h else fluid,
                         "drink_ml": drinks_ml, "water_ml": max(0.0, fl - drinks_ml),
                         "sweat_l_h": sweat, "sweat_l": sweat * h, "na_loss_mg_h": na_loss, "na_target_mg": na_target, "na_planned_mg": na_prod,
                         "electrolyte_tabs": tabs, "products": lines})
        tot["carbs"] += grams
        tot["fluid"] += fl
        tot["sodium_need"] += na_target
        tot["sodium_prod"] += na_prod
        tot["hours"] += h
        tot["sweat_l"] += sweat * h

    warnings = []
    if band["hi"] and dose > band["hi"]:
        warnings.append(f"{dose:g} g/h dépasse la fourchette pour cette durée ({band['lo']}–{band['hi']} g/h) : à n'envisager que si tu l'as déjà tolérée à l'entraînement.")
    if band["hi"] and 0 < dose < band["lo"]:
        warnings.append(f"{dose:g} g/h est sous la fourchette pour cette durée ({band['lo']}–{band['hi']} g/h).")
    if habit is not None and dose > habit + 20:
        warnings.append(f"Cible supérieure de plus de 20 g/h à ton habitude ({habit:g} g/h) : entraîne ton tube digestif sur des sorties longues avant la course.")
    if profile.get("gi") == "often" and dose > 60:
        warnings.append("Troubles digestifs fréquents signalés : une cible au-dessus de 60 g/h est risquée sans entraînement digestif préalable.")
    if dose > 60 and prods and fruct < 0.2:
        warnings.append("Au-dessus de ~60 g/h, un seul type de glucide plafonne l'absorption : ajoute des produits contenant du fructose "
                        f"(ratio conseillé {rat['ratio']}).")
    if dose and prods and not shares:
        warnings.append("Aucun produit avec une part de glucides n'est renseigné.")
    if not prods and dose:
        warnings.append("Renseigne tes produits (et leur part des glucides) pour obtenir les quantités.")
    if over_drink:
        warnings.append("La boisson prévue dépasse la cible de liquide (sudation × part remplacée) : le liquide total a été relevé. "
                        "Réduis la part de boisson au profit des gels, ou utilise une boisson plus concentrée (sans dépasser ~8–10 g/100 mL).")
    bars = sum(shares.get(p["name"], 0) for p in prods if p["type"] == "bar")
    if bars > 0.3:
        warnings.append("Les barres représentent plus de 30 % des glucides : elles ralentissent la vidange gastrique, à garder en appoint.")
    if any(p["type"] == "maltodextrin" for p in prods) and tot["sodium_prod"] <= 0 and hours > 3:
        warnings.append("Maltodextrine seule : aucun sodium apporté, à compléter.")
    drink_conc = None
    drinks = [p for p in prods if p["type"] == "drink" and p["volume_ml"]]
    if drinks:
        drink_conc = statistics.mean(p["carbs_g"] / p["volume_ml"] * 100 for p in drinks)
        if drink_conc > 10:
            warnings.append(f"Boisson à {drink_conc:.0f} g/100 mL : concentration élevée, risque digestif ; dilue ou répartis avec des gels.")
    mass = profile.get("weight_kg")
    bm_loss = None
    if mass:
        bm_loss = (tot["sweat_l"] - tot["fluid"] / 1000) / mass * 100
        if bm_loss > 3:
            warnings.append(f"Perte de masse estimée {bm_loss:.1f} % : au-dessus de 2–3 %, la performance peut baisser ; "
                            "boire davantage si tu as soif, sans dépasser ta sudation.")

    return {"hours": hours, "band": band, "carb_g_h": dose, "ratio": rat, "fructose_share": fruct,
            "sweat": {"base_20c": base, "from_tests": from_tests, "n_tests": len(profile["tests"]), "na_mmol_l": na_conc,
                      "na_default": not profile.get("sweat_na_mmol_l"), "mean_temp": mean_t, "total_l": tot["sweat_l"]},
            "fluid_pct": fluid_pct, "na_pct": na_pct, "sections": sections,
            "totals": {"carbs_g": tot["carbs"], "fluid_ml": tot["fluid"], "sodium_target_mg": tot["sodium_need"], "sodium_planned_mg": tot["sodium_prod"],
                       "products": [{"name": p["name"], "type": p["type"], "servings": per_product.get(p["name"], 0.0)}
                                    for p in profile["products"] if per_product.get(p["name"], 0) > 0],
                       "bm_loss_pct": bm_loss},
            "drink_conc_pct": drink_conc, "warnings": warnings,
            "caffeine_mg": {"lo": round(3 * mass), "hi": round(6 * mass)} if mass else None}
