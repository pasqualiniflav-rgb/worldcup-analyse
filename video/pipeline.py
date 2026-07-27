"""Exploitation du tracking.csv : frame annotée, heatmap, auto-clip.

Ces fonctions ne dépendent PAS d'ultralytics : elles travaillent sur le
CSV + la vidéo, et sont donc entièrement testables (voir selftest.py).
"""
from __future__ import annotations

import subprocess
from collections import defaultdict, Counter
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import load_video_config, read_tracking, out_dir, ffmpeg_exe

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
        cmd = [ffmpeg_exe(), "-y", "-ss", f"{s:.2f}", "-i", str(video_path),
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
            [ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-c", "copy", "-loglevel", "error", str(reel)], check=True)
        print(f"Montage complet -> {reel}")
    return clips


# --------------------------------------------------------------------------
#  4) Vignette d'identité : gros plan du joueur ciblé
# --------------------------------------------------------------------------
def _track_rows(rows, track_id):
    return [r for r in rows if r["track_id"] == track_id and r["cls"] == 0]


def _track_label(trk, track_id):
    """Étiquette lisible : 'N°7 A' si le numéro est connu, sinon '#<id>'."""
    nums = [r.get("numero") for r in trk if r.get("numero")]
    teams = [r.get("team") for r in trk if r.get("team")]
    team = Counter(teams).most_common(1)[0][0] if teams else None
    if nums:
        num = Counter(nums).most_common(1)[0][0]
        return f"N.{num}" + (f" {team}" if team else "")
    return f"#{track_id}"


def player_thumbnail(video_path: Path, tracking_csv: Path, track_id: int,
                     out_png: Path | None = None):
    rows = read_tracking(tracking_csv)
    trk = _track_rows(rows, track_id)
    if not trk:
        print(f"Aucune donnée pour le joueur #{track_id}.")
        return None
    # frame où la boîte est la plus grande (joueur le plus proche/net)
    best = max(trk, key=lambda r: r["w"] * r["h"])
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, best["frame"])
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    H, W = frame.shape[:2]
    x, y, w, h = best["x"], best["y"], best["w"], best["h"]
    mx, my = w * 0.6, h * 0.4
    x1 = int(max(0, x - w / 2 - mx)); x2 = int(min(W, x + w / 2 + mx))
    y1 = int(max(0, y - h / 2 - my)); y2 = int(min(H, y + h / 2 + my))
    crop = frame[y1:y2, x1:x2].copy()
    # boîte du joueur dans le crop
    cv2.rectangle(crop, (int(x - w / 2 - x1), int(y - h / 2 - y1)),
                  (int(x + w / 2 - x1), int(y + h / 2 - y1)), (0, 255, 255), 2)
    cv2.putText(crop, _track_label(trk, track_id), (5, 22), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 255, 255), 2)
    out_png = out_png or (out_dir() / f"joueur_{track_id}_identite.png")
    cv2.imwrite(str(out_png), crop)
    print(f"Vignette d'identité -> {out_png}")
    return out_png


# --------------------------------------------------------------------------
#  5) Montage ANNOTÉ : le joueur ciblé est entouré tout au long du film
# --------------------------------------------------------------------------
def _frame_segments(frames_present, fps, cfg):
    if not frames_present:
        return []
    gap_f = cfg["autoclip"]["gap_max"] * fps
    pad_a = cfg["autoclip"]["padding_avant"] * fps
    pad_b = cfg["autoclip"]["padding_apres"] * fps
    fr = sorted(frames_present)
    segs, start, prev = [], fr[0], fr[0]
    for f in fr[1:]:
        if f - prev > gap_f:
            segs.append((start, prev)); start = f
        prev = f
    segs.append((start, prev))
    padded = [(max(0, s - pad_a), e + pad_b) for s, e in segs]
    merged = []
    for s, e in padded:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def annotated_montage(video_path: Path, tracking_csv: Path, track_id: int,
                      cfg: dict | None = None, out_path: Path | None = None):
    cfg = cfg or load_video_config()
    rows = read_tracking(tracking_csv)
    trk = _track_rows(rows, track_id)
    if not trk:
        print(f"Aucune donnée pour le joueur #{track_id}.")
        return None
    pos = {r["frame"]: r for r in trk}
    label = _track_label(trk, track_id)

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    Hh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    segs = _frame_segments(list(pos.keys()), fps, cfg)
    include = lambda f: any(s <= f <= e for s, e in segs)

    out_path = out_path or (out_dir() / f"montage_joueur_{track_id}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(out_path), fourcc, fps, (W, Hh))

    written = 0
    f = 0
    while True:
        ok, frame = cap.read()
        if not ok or f > total:
            break
        if include(f):
            r = pos.get(f)
            if r:
                x, y, w, h = r["x"], r["y"], r["w"], r["h"]
                p1 = (int(x - w / 2), int(y - h / 2)); p2 = (int(x + w / 2), int(y + h / 2))
                cv2.rectangle(frame, p1, p2, (0, 255, 255), 3)
                cv2.putText(frame, label, (p1[0], max(20, p1[1] - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                # marqueur au-dessus de la tête
                cv2.circle(frame, (int(x), int(y - h / 2 - 12)), 6, (0, 255, 255), -1)
            vw.write(frame)
            written += 1
        f += 1
    cap.release(); vw.release()
    dur = written / fps if fps else 0
    print(f"Montage annoté -> {out_path}  ({written} images, ~{dur:.0f}s)")
    return out_path


if __name__ == "__main__":
    import sys
    print("Module utilitaire — voir run_video.py")