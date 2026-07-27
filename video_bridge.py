"""Pont VIDÉO -> BASE JOUEURS.

Transforme l'effectif vidéo (numéros identifiés) en entrées de la base
`selection.sqlite` du projet principal, via une table de correspondance
numéro -> vrai joueur remplie par le staff (à partir des compositions).

Deux commandes :
  python video_bridge.py template
      -> crée correspondance.csv, pré-rempli des numéros détectés.
         Le staff y saisit prénom/nom (et poste/sélection) de chaque joueur.

  python video_bridge.py import  "Compétition"  "Adversaire"  AAAA-MM-JJ
      -> crée/complète les joueurs et ajoute une OBSERVATION vidéo
         (présence, montage) dans la base. Régénère ensuite les fiches
         avec :  python scripts/report.py   (PAS run.py, qui réinitialise).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from config import DB_PATH  # noqa: E402  (scripts/config.py)
from db import get_connection  # noqa: E402

VIDEO_OUT = ROOT / "video" / "out"
ROSTER_JSON = VIDEO_OUT / "joueurs_video.json"
CORR = ROOT / "correspondance.csv"

FIELDS = ["equipe", "numero", "secondes_presence",
          "player_id", "prenom", "nom", "poste", "selection", "statut"]


def cmd_template():
    if not ROSTER_JSON.exists():
        sys.exit(f"{ROSTER_JSON} introuvable : lance d'abord 'run_video.py roster'.")
    roster = json.loads(ROSTER_JSON.read_text(encoding="utf-8"))
    with open(CORR, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for p in roster:
            w.writerow({"equipe": p["equipe"], "numero": p["numero"],
                        "secondes_presence": p["secondes_presence"],
                        "player_id": "", "prenom": "", "nom": "",
                        "poste": "", "selection": "A", "statut": "À suivre"})
    print(f"Table de correspondance -> {CORR}")
    print("Remplis 'prenom' et 'nom' pour chaque joueur à importer "
          "(les lignes vides sont ignorées), puis :")
    print('  python video_bridge.py import "Amical" "Afghanistan" 2026-07-27')


def cmd_import(competition="Match vidéo", adversaire="", date="2026-07-27"):
    if not CORR.exists():
        sys.exit("correspondance.csv manquant : lance 'template' d'abord.")
    rows = list(csv.DictReader(open(CORR, encoding="utf-8-sig")))
    conn = get_connection()  # base existante (ne pas réinitialiser !)
    n_players, n_obs = 0, 0
    with conn:
        for r in rows:
            if not (r.get("nom") or "").strip():
                continue  # ligne non renseignée -> ignorée
            pid = (r.get("player_id") or "").strip() or f"VID_{r['equipe']}{r['numero']}"
            conn.execute(
                """INSERT INTO joueurs (player_id, nom, prenom, poste, selection, statut)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(player_id) DO UPDATE SET
                     nom=excluded.nom, prenom=excluded.prenom,
                     poste=COALESCE(NULLIF(excluded.poste,''), joueurs.poste)""",
                (pid, r["nom"].strip(), (r.get("prenom") or "").strip(),
                 r.get("poste") or "", r.get("selection") or "A",
                 r.get("statut") or "À suivre"))
            n_players += 1

            sec = float(r.get("secondes_presence") or 0)
            montage = f"montage_num{r['numero']}_{r['equipe']}.mp4"
            commentaire = (f"Analyse vidéo automatique — n°{r['numero']} ({r['equipe']}), "
                           f"{sec:.0f}s de présence à l'écran. Montage : {montage}")
            conn.execute(
                """INSERT INTO observations
                   (player_id, date, contexte, competition, adversaire, minutes,
                    note_globale, video_url, commentaire, observateur)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pid, date, "Vidéo", competition, adversaire, round(sec / 60, 1),
                 None, montage, commentaire, "Pipeline vidéo"))
            n_obs += 1
    conn.close()
    print(f"Import terminé : {n_players} joueurs créés/complétés, {n_obs} observations vidéo ajoutées.")
    print(f"Base : {DB_PATH}")
    print("Régénère les fiches avec :  python scripts/report.py")


def cmd_squad(csv_path, selection="A", prefix="SEL"):
    """Importe un effectif (compo) dans la base joueurs, sans observation.
    CSV attendu : numero, nom, prenom, poste, statut, notes."""
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    conn = get_connection()
    n = 0
    with conn:
        for r in rows:
            if not (r.get("nom") or "").strip():
                continue
            num = (r.get("numero") or "").strip()
            pid = f"{prefix}_{num}" if num else f"{prefix}_{r['nom'].strip()[:6]}"
            conn.execute(
                """INSERT INTO joueurs (player_id, nom, prenom, poste, selection, statut, notes_generales)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(player_id) DO UPDATE SET
                     nom=excluded.nom, prenom=excluded.prenom, poste=excluded.poste,
                     statut=excluded.statut, notes_generales=excluded.notes_generales""",
                (pid, r["nom"].strip(), (r.get("prenom") or "").strip(),
                 r.get("poste") or "", selection, r.get("statut") or "À suivre",
                 (r.get("notes") or "") + (f"  [maillot n°{num}]" if num else "")))
            n += 1
    conn.close()
    print(f"Effectif importé : {n} joueurs (sélection {selection}).")
    print("Régénère les fiches avec :  python scripts/report.py")


def main():
    cmds = ("template", "import", "squad")
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("Usage: python video_bridge.py template | import "
                 '["Compétition" "Adversaire" AAAA-MM-JJ] | '
                 "squad <fichier.csv> <selection> <prefixe>")
    if sys.argv[1] == "template":
        cmd_template()
    elif sys.argv[1] == "squad":
        cmd_squad(*(sys.argv[2:5]))
    else:
        args = sys.argv[2:]
        cmd_import(*(args[:3]))


if __name__ == "__main__":
    main()