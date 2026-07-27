"""Couche d'accès à la base SQLite.

Un unique fichier .sqlite fait office de "source de vérité" du client.
Il se sauvegarde / s'archive comme un simple document.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from config import DB_PATH, DB_DIR, ROOT


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = db_path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """(Ré)initialise le schéma à partir de schema.sql."""
    schema = (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")
    conn = get_connection(db_path)
    with conn:
        conn.executescript(schema)
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Base initialisée :", DB_PATH)
