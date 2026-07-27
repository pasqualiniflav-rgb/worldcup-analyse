"""Chargement de la configuration client et des chemins du projet.

Point unique pour lire config/client.yaml. Tous les autres scripts
importent d'ici pour rester indépendants du client déployé.
"""
from __future__ import annotations

from pathlib import Path
import yaml

# Racine du projet = dossier parent de /scripts
ROOT = Path(__file__).resolve().parent.parent

# Arborescence standard
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
INPUT_DIR = DATA_DIR / "input"
DB_DIR = DATA_DIR / "db"
REPORTS_DIR = ROOT / "reports"
ASSETS_DIR = ROOT / "assets"

DB_PATH = DB_DIR / "selection.sqlite"


def load_config(path: Path | None = None) -> dict:
    """Charge le fichier de configuration client (YAML)."""
    path = path or (CONFIG_DIR / "client.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    cfg = load_config()
    print("Client :", cfg["client"]["nom"])
    print("Base   :", DB_PATH)
