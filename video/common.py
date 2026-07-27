"""Utilitaires partagés du module vidéo : config, chemins, schéma CSV."""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

import yaml

VIDEO_DIR = Path(__file__).resolve().parent


def ffmpeg_exe() -> str:
    """Localise l'exécutable ffmpeg de façon robuste (Windows/macOS/Linux).

    Ordre : 1) chemin forcé dans la config  2) ffmpeg présent sur le PATH
    3) binaire embarqué par le paquet imageio-ffmpeg (pip install imageio-ffmpeg).
    Ainsi, aucune manipulation du PATH n'est nécessaire côté client.
    """
    try:
        cfg = load_video_config()
        override = (cfg.get("systeme") or {}).get("ffmpeg")
        if override:
            return str(override)
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"  # dernier recours : laisse remonter une erreur claire


def load_video_config(path: Path | None = None) -> dict:
    path = path or (VIDEO_DIR / "config_video.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def out_dir() -> Path:
    cfg = load_video_config()
    d = VIDEO_DIR / cfg["sorties"]["dossier"]
    d.mkdir(parents=True, exist_ok=True)
    return d


# Schéma de la table de suivi (une ligne = une détection suivie sur une image)
TRACK_FIELDS = ["frame", "time_s", "track_id", "cls", "cls_name",
                "x", "y", "w", "h", "conf", "team", "numero"]


def write_tracking(rows, path: Path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=TRACK_FIELDS)
        wr.writeheader()
        for r in rows:
            wr.writerow({k: r.get(k, "") for k in TRACK_FIELDS})


def read_tracking(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("frame", "track_id", "cls"):
            r[k] = int(float(r[k])) if r[k] not in ("", None) else None
        for k in ("time_s", "x", "y", "w", "h", "conf"):
            r[k] = float(r[k]) if r[k] not in ("", None) else None
    return rows