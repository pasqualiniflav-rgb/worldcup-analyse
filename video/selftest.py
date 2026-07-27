"""Self-test de la PLOMBERIE du module vidéo, sans YOLO.

Génère une petite vidéo synthétique + un tracking.csv de vérité terrain,
puis exécute frame annotée -> heatmap -> auto-clip et vérifie les sorties.
Valide : lecture/écriture vidéo, découpe ffmpeg, concat, heatmap, CSV,
et surtout la logique de segmentation des séquences.

    python selftest.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np

from common import load_video_config, out_dir, write_tracking, TRACK_FIELDS
from pipeline import annotated_preview, heatmap, autoclip

W, H, FPS, N_FRAMES = 960, 540, 25, 240
TARGET_ID = 3  # joueur ciblé pour l'auto-clip

TEAM_COLOR = {"A": (60, 76, 231), "B": (231, 160, 60)}  # BGR


def _players():
    """10 joueurs (5 A, 5 B) + trajectoires simples."""
    ps = []
    for i in range(10):
        team = "A" if i < 5 else "B"
        base_x = 150 + (i % 5) * 150
        base_y = 160 if team == "A" else 360
        ps.append(dict(track_id=i + 1, team=team, bx=base_x, by=base_y,
                       ax=40 + i * 4, ay=30, ph=i * 0.6))
    return ps


def _pos(p, f):
    x = p["bx"] + p["ax"] * math.sin(f * 0.05 + p["ph"])
    y = p["by"] + p["ay"] * math.cos(f * 0.04 + p["ph"])
    return x, y


def _target_present(f):
    # Présent frames 0..70 et 200..239 -> doit produire 2 clips distincts
    return f <= 70 or f >= 200


def generate():
    od = out_dir()
    seg = od / "segment.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(seg), fourcc, FPS, (W, H))
    players = _players()
    rows = []
    for f in range(N_FRAMES):
        frame = np.full((H, W, 3), (40, 110, 60), np.uint8)  # pelouse
        for p in players:
            if p["track_id"] == TARGET_ID and not _target_present(f):
                continue
            x, y = _pos(p, f)
            w, h = 26, 54
            cv2.rectangle(frame, (int(x - w/2), int(y - h/2)),
                          (int(x + w/2), int(y + h/2)), TEAM_COLOR[p["team"]], -1)
            rows.append(dict(frame=f, time_s=round(f / FPS, 3),
                             track_id=p["track_id"], cls=0, cls_name="player",
                             x=round(x, 1), y=round(y, 1), w=w, h=h,
                             conf=0.9, team=p["team"]))
        # ballon
        bx = W/2 + 200 * math.sin(f * 0.08); by = H/2 + 120 * math.cos(f * 0.08)
        cv2.circle(frame, (int(bx), int(by)), 7, (255, 255, 255), -1)
        rows.append(dict(frame=f, time_s=round(f / FPS, 3), track_id=99, cls=32,
                         cls_name="ball", x=round(bx, 1), y=round(by, 1),
                         w=14, h=14, conf=0.8, team=""))
        vw.write(frame)
    vw.release()
    csv_path = od / "tracking.csv"
    write_tracking([{k: r.get(k, "") for k in TRACK_FIELDS} for r in rows], csv_path)
    return seg, csv_path


def main():
    cfg = load_video_config()
    seg, csv_path = generate()
    print(f"Vidéo synthétique : {seg}")

    preview = annotated_preview(seg, csv_path)
    hm = heatmap(csv_path, track_id=TARGET_ID, video_path=seg)
    clips = autoclip(seg, csv_path, TARGET_ID, cfg)

    # Vérifications
    ok = True
    checks = {
        "vidéo générée": seg.exists() and seg.stat().st_size > 0,
        "frame annotée": preview and Path(preview).exists(),
        "heatmap": hm and Path(hm).exists(),
        "2 séquences attendues": len(clips) == 2,
        "montage créé": (out_dir() / f"montage_joueur_{TARGET_ID}.mp4").exists(),
    }
    print("\n=== RÉSULTATS DU SELF-TEST ===")
    for name, val in checks.items():
        print(f"  [{'OK' if val else 'ÉCHEC'}] {name}")
        ok = ok and val
    print("=" * 32)
    print("SUCCES OK" if ok else "DES TESTS ONT ECHOUE")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
