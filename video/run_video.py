"""Orchestrateur du module vidéo (POC).

Étapes :
  prep   -> découpe un segment de la vidéo complète (ffmpeg)
  track  -> détection + suivi + équipes + frame annotée (nécessite ultralytics)
  clip   -> montage auto + heatmap d'un joueur (à partir de son #ID)
  all    -> prep + track, puis clip si un #ID est fourni

Exemples :
  python run_video.py prep  match_complet.mp4
  python run_video.py track                       # sur le segment préparé
  python run_video.py clip 7                       # joueur #7 repéré sur la frame annotée
  python run_video.py all   match_complet.mp4 7
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import load_video_config, out_dir

SEGMENT = "segment.mp4"


def prep(video_path: Path, cfg) -> Path:
    t = cfg["traitement"]
    seg = out_dir() / SEGMENT
    cmd = ["ffmpeg", "-y"]
    if t.get("segment_debut"):
        cmd += ["-ss", str(t["segment_debut"])]
    cmd += ["-i", str(video_path)]
    if t.get("segment_duree"):
        cmd += ["-t", str(t["segment_duree"])]
    # redimensionnement pour accélérer
    largeur = t.get("redim_largeur")
    if largeur:
        cmd += ["-vf", f"scale={int(largeur)}:-2"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-an",
            "-loglevel", "error", str(seg)]
    print("Préparation du segment...")
    subprocess.run(cmd, check=True)
    print(f"Segment prêt -> {seg}")
    return seg


def track(cfg) -> Path:
    from detect_track import run as detect_run
    from teams import assign_teams
    from pipeline import annotated_preview
    seg = out_dir() / SEGMENT
    if not seg.exists():
        sys.exit("Segment introuvable : lancez d'abord 'prep'.")
    csv_path = detect_run(seg, cfg)
    if cfg["equipes"]["activer"]:
        assign_teams(seg, csv_path, cfg)
    annotated_preview(seg, csv_path)
    print("\n-> Ouvrez out/preview_ids.png et repérez le #ID de votre joueur,")
    print("   puis lancez : python run_video.py clip <ID>")
    return csv_path


def clip(track_id: int, cfg):
    from pipeline import autoclip, heatmap
    seg = out_dir() / SEGMENT
    csv_path = out_dir() / "tracking.csv"
    if not csv_path.exists():
        sys.exit("tracking.csv introuvable : lancez d'abord 'track'.")
    autoclip(seg, csv_path, track_id, cfg)
    heatmap(csv_path, track_id=track_id, video_path=seg)


def main():
    cfg = load_video_config()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep"); p.add_argument("video")
    sub.add_parser("track")
    c = sub.add_parser("clip"); c.add_argument("track_id", type=int)
    a = sub.add_parser("all"); a.add_argument("video"); a.add_argument("track_id", nargs="?", type=int)
    args = ap.parse_args()

    if args.cmd == "prep":
        prep(Path(args.video), cfg)
    elif args.cmd == "track":
        track(cfg)
    elif args.cmd == "clip":
        clip(args.track_id, cfg)
    elif args.cmd == "all":
        prep(Path(args.video), cfg)
        track(cfg)
        if args.track_id is not None:
            clip(args.track_id, cfg)


if __name__ == "__main__":
    main()
