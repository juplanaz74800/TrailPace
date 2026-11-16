"""Teste le catalogue CSV via l'API (serveur sur :8000) puis rétablit le fichier fourni."""
import io

import requests

B = "http://localhost:8000/api/nutrition/catalog"
c = requests.get(B).json()
print("fichier :", c["file"], "|", len(c["products"]), "produits |", len(c["brands"]), "marques")

r = requests.post(B, files={"file": ("x.csv", b"a,b\n1,2\n")})
print("CSV sans colonnes requises ->", r.status_code, r.json().get("detail"))
r = requests.post(B, files={"file": ("x.csv", ("marque,type_produit,nom_produit,glucides_g,sodium_mg\nTest,Fusée,Truc,10,5\n").encode())})
print("types non reconnus ->", r.status_code, r.json().get("detail"))
csv_ok = ("marque;type_produit;nom_produit;glucides_g;sodium_mg;ratio_glu_fru;dilution_ml;portion_g_ml;unite;statut\n"
          "Ma marque;Gel;Mon gel;27,5;120;2:1;;40;g;vérifié\n"
          "Ma marque;Barre;Ma barre;30;80;;;50;g;\n"
          "Ma marque;Boisson;Ma boisson;40;300;1:0,8;500;40;g;\n").encode()
r = requests.post(B, files={"file": ("mon.csv", csv_ok)})
print("CSV valide (séparateur ;, virgules décimales) ->", r.status_code, r.json())
c = requests.get(B).json()
print("   après import :", c["file"], [(p["name"], p["category"], p["carbs_g"], p["fructose_pct"], p["confidence"]) for p in c["products"]])
requests.delete(B)
c = requests.get(B).json()
print("après rétablissement :", c["file"], len(c["products"]), "produits")
