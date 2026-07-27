"""Ingestion : classeur Excel de saisie  ->  base SQLite.

Lit chaque onglet du classeur (data/input/saisie_selection.xlsx),
nettoie les lignes vides et charge la base. Idempotent : réinitialise
le schéma à chaque exécution (la source de vérité reste l'Excel).

Usage :
    python ingest.py                       # utilise le fichier démo
    python ingest.py chemin/vers/fichier.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from config import INPUT_DIR
from db import init_db, get_connection

# Onglet Excel  ->  (table SQLite, colonne clé pour filtrer les lignes vides)
SHEET_TO_TABLE = {
    "Joueurs": ("joueurs", "player_id"),
    "Observations": ("observations", "player_id"),
    "Medical": ("dispo_medicale", "player_id"),
    "TempsJeu": ("temps_jeu", "player_id"),
    "Adversaires": ("adversaires", "adversaire_id"),
}

# Colonnes attendues par table (ordre libre dans l'Excel)
TABLE_COLUMNS = {
    "joueurs": ["player_id", "nom", "prenom", "date_naissance", "poste", "pied",
                "taille_cm", "selection", "statut", "club", "pays_club", "notes_generales"],
    "observations": ["player_id", "date", "contexte", "competition", "adversaire",
                     "minutes", "note_globale", "video_url", "video_ts", "code_action",
                     "commentaire", "observateur"],
    "dispo_medicale": ["player_id", "date", "statut", "type_blessure", "retour_prevu",
                       "commentaire"],
    "temps_jeu": ["player_id", "date", "club", "competition", "minutes", "titulaire",
                  "buts", "passes_d"],
    "adversaires": ["adversaire_id", "pays", "systeme", "forces", "faiblesses",
                    "joueurs_cles", "video_url", "commentaire"],
}


def read_sheet(xlsx_path: Path, sheet: str) -> pd.DataFrame:
    """Lit un onglet : en-têtes en ligne 3, ligne 4 = aide (ignorée),
    données à partir de la ligne 5."""
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=2, skiprows=[3],
                       engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def clean(df: pd.DataFrame, table: str, key_col: str) -> pd.DataFrame:
    # Garde uniquement les colonnes connues et présentes
    cols = [c for c in TABLE_COLUMNS[table] if c in df.columns]
    df = df[cols].copy()
    # Vire les lignes sans clé
    df = df[df[key_col].notna() & (df[key_col].astype(str).str.strip() != "")]
    # NaN -> None pour SQLite
    df = df.where(pd.notna(df), None)
    return df


def ingest(xlsx_path: Path) -> dict:
    init_db()  # (ré)initialise le schéma
    conn = get_connection()
    counts = {}
    with conn:
        for sheet, (table, key_col) in SHEET_TO_TABLE.items():
            try:
                df = read_sheet(xlsx_path, sheet)
            except ValueError:
                print(f"  ! onglet '{sheet}' introuvable, ignoré")
                continue
            df = clean(df, table, key_col)
            rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
            if rows:
                placeholders = ",".join("?" * len(df.columns))
                collist = ",".join(df.columns)
                conn.executemany(
                    f"INSERT INTO {table} ({collist}) VALUES ({placeholders})", rows
                )
            counts[table] = len(rows)
    conn.close()
    return counts


def main():
    xlsx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (INPUT_DIR / "saisie_selection.xlsx")
    if not xlsx_path.exists():
        sys.exit(f"Fichier introuvable : {xlsx_path}")
    print("Ingestion de :", xlsx_path)
    counts = ingest(xlsx_path)
    for table, n in counts.items():
        print(f"  {table:16s} : {n} lignes")
    print("Terminé.")


if __name__ == "__main__":
    main()
