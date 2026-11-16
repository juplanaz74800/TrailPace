"""Test du module nutrition sur le plan courant, sans toucher à data/nutrition.json."""
import json
import sys

sys.path.insert(0, ".")
from trailpace import nutrition as N
from trailpace import planservice, service

plan = planservice.plan_json({})
prof = N.load_profile()
prof.update(weight_kg=70, habit_g_h=40, gi="sometimes")
prof["tests"] = [N.clean_test({"date": "2026-11-10", "duration_min": 60, "temp_c": 8, "mass_before_kg": 70.0, "mass_after_kg": 69.6,
                               "fluid_ml": 300, "urine_ml": 0, "avg_power_w": 240})]
print("sudation du test :", round(N.test_rate(prof["tests"][0]), 2), "L/h à", prof["tests"][0]["temp_c"], "°C")
print("repères :", {h: (N.carb_band(h)["lo"], N.carb_band(h)["hi"]) for h in (0.5, 1.5, 2.5, 4, 9)})
print("ratio :", {d: N.ratio_for(d)["ratio"] for d in (40, 75, 100, 130)})

n = N.build(plan, prof)
print(f"durée {n['hours']:.1f} h | cible {n['carb_g_h']} g/h (défaut {N.default_carb_target(n['hours'], 40)}) | ratio {n['ratio']['ratio']} | fructose {n['fructose_share']:.2f}")
print("sudation de base 20 °C :", round(n["sweat"]["base_20c"], 2), "| depuis tests :", n["sweat"]["from_tests"], "| T moyenne", round(n["sweat"]["mean_temp"], 1))
for s in n["sections"]:
    print(f"  S{s['n']} {s['hours']:.1f} h : {s['carbs_g']:.0f} g | liquide {s['fluid_ml']:.0f} mL (boisson {s['drink_ml']:.0f}) | sueur {s['sweat_l_h']:.2f} L/h | Na cible {s['na_target_mg']:.0f} mg (prévu {s['na_planned_mg']:.0f}) | élec {s['electrolyte_tabs']}")
t = n["totals"]
print("totaux :", round(t["carbs_g"]), "g ;", round(t["fluid_ml"]), "mL ;", [(p["name"][:18], round(p["servings"], 1)) for p in t["products"]], "| perte masse", t["bm_loss_pct"] and round(t["bm_loss_pct"], 1), "%")
for w in n["warnings"]:
    print("  !", w)
b = N.bilan(prof, service.profile_json().get("sessions", []), n["hours"])
print("bilan :", json.dumps(b["training"], ensure_ascii=False)[:420])
for it in b["items"]:
    print("  ", it["what"], it["band"]["lo"], "-", it["band"]["hi"], it.get("status"))
print("notes :", b["notes"])
# cas limites
print("dose 130 :", [w[:60] for w in N.build(plan, prof, carb=130)["warnings"]])
try:
    N.clean_test({"duration_min": 60, "temp_c": 10, "mass_before_kg": 70, "mass_after_kg": 75, "fluid_ml": 0})
except ValueError as e:
    print("test invalide refusé :", e)
