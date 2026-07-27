"""Exploitation du tracking.csv : frame annotée, heatmap, auto-clip.

Ces fonctions ne dépendent PAS d'ultralytics : elles travaillent sur le
CSV + la vidéo, et sont donc entièrement testables (voir selftest.py).
"""
from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import load_video_config, read_tracking, out_dir

TEAM_BGR = {"A": (60, 76, 231), "B": (231, 160, 60), "": (200, 200, 200)}


# --------------------------------------------------------------------------
#  1) Frame annotée : pour identifier VISUELLEMENT l'ID du joueur ciblé
# --------------------------------------------------------------------------
def annotated_preview(video_path: Path, tracking_csv: Path, out_png: Path | None = None):
    rows = read_tracking(tracking_csv)
    by_frame = defaultdict(list)
    for r in rows:
        by_frame[r["frame"]].append(r)
    if not by_frame:
        raise SystemExit("tracking.csv vide.")
    # Frame avec le plus de joueurs -> la plus lisible
    best = max(by_frame, key=lambda f: sum(1 for r in by_frame[f] if r["cls"] == 0))

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, best)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"Impossible de lire la frame {best}.")

    for r in by_frame[best]:
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        p1 = (int(x - w / 2), int(y - h / 2))
        p2 = (int(x + w / 2), int(y + h / 2))
        if r["cls"] == 32:  # ballon
            cv2.circle(frame, (int(x), int(y)), 8, (0, 255, 255), 2)
            continue
        color = TEAM_BGR.get(r.get("team", ""), (200, 200, 200))
        cv2.rectangle(frame, p1, p2, color, 2)
        cv2.putText(frame, f"#{r['track_id']}", (p1[0], p1[1] - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    out_png = out_png or (out_dir() / "preview_ids.png")
    cv2.imwrite(str(out_png), frame)
    print(f"Frame annotée (choisir un #ID) -> {out_png}")
    return out_png


# --------------------------------------------------------------------------
#  2) Heatmap d'un joueur (ou d'une équipe) en espace image
# --------------------------------------------------------------------------
def heatmap(tracking_csv: Path, track_id: int | None = None, team: str | None = None,
            video_path: Path | None = None, out_png: Path | None = None):
    rows = read_tracking(tracking_csv)
    if track_id is not None:
        pts = [(r["x"], r["y"]) for r in rows if r["track_id"] == track_id and r["cls"] == 0]
        titre = f"Heatmap joueur #{track_id}"
        suffix = f"joueur_{track_id}"
    elif team is not None:
        pts = [(r["x"], r["y"]) for r in rows if r.get("team") == team and r["cls"] == 0]
        titre = f"Heatmap équipe {team}"
        suffix = f"equipe_{team}"
    else:
        raise ValueError("Préciser track_id ou team.")
    if not pts:
        print("Aucune position pour cette cible.")
        return None

    # Dimensions image (depuis la vidéo si dispo, sinon depuis les points)
    if video_path:
        cap = cv2.VideoCapture(str(video_path))
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
        cap.release()
    else:
        W = int(max(p[0] for p in pts)) + 50
        H = int(max(p[1] for p in pts)) + 50

    xs = np.array([p[0] for p in pts]); ys = np.array([p[1] for p in pts])
    bins_x = max(12, W // 40); bins_y = max(8, H // 40)
    hist, xe, ye = np.histogram2d(xs, ys, bins=[bins_x, bins_y],
                                  range=[[0, W], [0, H]])

    fig, ax = plt.subplots(figsize=(9, 9 * H / W))
    ax.set_facecolor("#1c6b38")
    ax.imshow(hist.T, origin="upper", extent=[0, W, H, 0],
              cmap="hot", alpha=0.85, interpolation="gaussian", aspect="auto")
    ax.set_title(titre, fontsize=13)
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    out_png = out_png or (out_dir() / f"heatmap_{suffix}.png")
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"Heatmap -> {out_png}")
    return out_png


# --------------------------------------------------------------------------
#  3) Auto-clip : montage automatique des séquences d'un joueur
# --------------------------------------------------------------------------
def _segments_for_track(rows, track_id, cfg):
    times = sorted(r["time_s"] for r in rows if r["track_id"] == track_id)
    if not times:
        return []
    gap_max = cfg["autoclip"]["gap_max"]
    segs = []
    start = prev = times[0]
    for t in times[1:]:
        if t - prev > gap_max:
            segs.append((start, prev))
            start = t
        prev = t
    segs.append((start, prev))

    pad_a = cfg["autoclip"]["padding_avant"]
    pad_b = cfg["autoclip"]["padding_apres"]
    dmin = cfg["autoclip"]["duree_min"]
    out = []
    for s, e in segs:
        if (e - s) < dmin:
            # séquence très courte : on la garde quand même avec le padding
            pass
        out.append((max(0.0, s - pad_a), e + pad_b))
    # fusion des segments qui se chevauchent après padding
    merged = []
    for s, e in out:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def autoclip(video_path: Path, tracking_csv: Path, track_id: int,
             cfg: dict | None = None, make_reel: bool = True):
    cfg = cfg or load_video_config()
    rows = read_tracking(tracking_csv)
    segs = _segments_for_track(rows, track_id, cfg)
    if not segs:
        print(f"Aucune séquence pour le joueur #{track_id}.")
        return []

    clip_dir = out_dir() / f"clips_joueur_{track_id}"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (s, e) in enumerate(segs, 1):
        dur = round(e - s, 2)
        out_clip = clip_dir / f"seq_{i:03d}_{s:.1f}s.mp4"
        cmd = ["ffmpeg", "-y", "-ss", f"{s:.2f}", "-i", str(video_path),
               "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "23", "-an", "-loglevel", "error", str(out_clip)]
        subprocess.run(cmd, check=True)
        clips.append(out_clip)
    print(f"{len(clips)} séquences découpées -> {clip_dir}")

    if make_reel and clips:
        listfile = clip_dir / "concat.txt"
        listfile.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
        reel = out_dir() / f"montage_joueur_{track_id}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-c", "copy", "-loglevel", "error", str(reel)], check=True)
        print(f"Montage complet -> {reel}")
    return clips


if __name__ == "__main__":
    import sys
    print("Module utilitaire — voir run_video.py")
