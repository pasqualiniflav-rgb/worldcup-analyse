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
import json
import subprocess
import sys
from pathlib import Path

import cv2

from common import load_video_config, out_dir, ffmpeg_exe

SEGMENT = "segment.mp4"
META = "segment_meta.json"


def _seconds(hms) -> float:
    """'hh:mm:ss' ou nombre -> secondes."""
    if not hms:
        return 0.0
    s = str(hms)
    if ":" in s:
        parts = [float(p) for p in s.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(s)


def _vid_dims(path):
    cap = cv2.VideoCapture(str(path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.release()
    return w, h, fps


def prep(video_path: Path, cfg) -> Path:
    t = cfg["traitement"]
    seg = out_dir() / SEGMENT
    cmd = [ffmpeg_exe(), "-y"]
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

    # Métadonnées pour la relecture haute résolution des numéros
    try:
        ow, oh, ofps = _vid_dims(video_path)
        sw, sh, sfps = _vid_dims(seg)
        meta = {"source": str(Path(video_path).resolve()),
                "start_s": _seconds(t.get("segment_debut")),
                "orig_w": ow, "orig_h": oh, "orig_fps": ofps,
                "seg_w": sw, "seg_h": sh, "seg_fps": sfps,
                "scale": (ow / sw) if sw else 1.0}
        (out_dir() / META).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception as e:
        print("  (info) métadonnées HD non écrites :", e)
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
    from pipeline import annotated_montage, player_thumbnail, heatmap
    seg = out_dir() / SEGMENT
    csv_path = out_dir() / "tracking.csv"
    if not csv_path.exists():
        sys.exit("tracking.csv introuvable : lancez d'abord 'track'.")
    # 1) qui est ce joueur : vignette d'identité
    player_thumbnail(seg, csv_path, track_id)
    # 2) son film, avec un repère qui le suit
    annotated_montage(seg, csv_path, track_id, cfg)
    # 3) heatmap : vue du dessus si le terrain est calibré, sinon vue caméra
    homo = out_dir() / "homography.json"
    if homo.exists():
        from pitch import heatmap_topdown
        heatmap_topdown(csv_path, homo, track_id=track_id)
    else:
        heatmap(csv_path, track_id=track_id, video_path=seg)
        print("(Astuce : lance 'python calibrate.py' pour obtenir la heatmap vue du dessus.)")


def main():
    cfg = load_video_config()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep"); p.add_argument("video")
    sub.add_parser("track")
    c = sub.add_parser("clip"); c.add_argument("track_id", type=int)
    sub.add_parser("numbers")
    sub.add_parser("roster")
    sub.add_parser("fixnumbers")
    cn = sub.add_parser("clipnum")
    cn.add_argument("numero"); cn.add_argument("equipe", nargs="?", default=None)
    cal = sub.add_parser("calibrate")
    cal.add_argument("seconds", nargs="?", type=float, default=0.0)
    cal.add_argument("side", nargs="?", default="gauche")   # gauche | droite
    a = sub.add_parser("all"); a.add_argument("video"); a.add_argument("track_id", nargs="?", type=int)
    args = ap.parse_args()

    if args.cmd == "prep":
        prep(Path(args.video), cfg)
    elif args.cmd == "track":
        track(cfg)
    elif args.cmd == "clip":
        clip(args.track_id, cfg)
    elif args.cmd == "numbers":
        from jersey import read_numbers
        read_numbers(out_dir() / SEGMENT, out_dir() / "tracking.csv", cfg)
    elif args.cmd == "roster":
        import consolidate
        consolidate.roster(out_dir() / "tracking.csv")
    elif args.cmd == "fixnumbers":
        from jersey import apply_numbers_from_json
        apply_numbers_from_json(out_dir() / "tracking.csv")
    elif args.cmd == "clipnum":
        import consolidate
        consolidate.merged_player(args.numero, args.equipe, cfg)
    elif args.cmd == "calibrate":
        import calibrate
        sys.argv = ["calibrate.py", str(args.seconds), str(args.side)]
        calibrate.main()
    elif args.cmd == "all":
        prep(Path(args.video), cfg)
        track(cfg)
        if args.track_id is not None:
            clip(args.track_id, cfg)


if __name__ == "__main__":
    main()