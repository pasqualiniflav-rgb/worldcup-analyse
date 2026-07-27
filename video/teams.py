"""Classification des équipes par couleur de maillot.

Pour chaque joueur suivi, on échantillonne quelques crops du torse,
on en extrait la couleur dominante, puis on sépare en 2 groupes (KMeans).
Le résultat ('A' / 'B') est réécrit dans la colonne `team` du CSV.

Approche volontairement simple (POC) : gardiens/arbitres peuvent être
mal classés — c'est corrigeable manuellement ensuite.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from sklearn.cluster import KMeans

from common import load_video_config, read_tracking, write_tracking, TRACK_FIELDS


def _torso_color(frame, x, y, w, h):
    """Signature couleur du maillot (torse), robuste.

    On isole la bande torse, on RETIRE les pixels verts (pelouse) et trop
    sombres (ombres), puis on encode la couleur de façon à bien séparer
    blanc (peu saturé) et rouge (très saturé) : [saturation, valeur,
    cos(teinte), sin(teinte)].
    """
    H, W = frame.shape[:2]
    x1 = int(max(0, x - w * 0.25)); x2 = int(min(W, x + w * 0.25))
    y1 = int(max(0, y - h * 0.32)); y2 = int(min(H, y - h * 0.05))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)
    h_, s_, v_ = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    # Masque : on écarte le vert pelouse (teinte ~35-90) et les ombres (V bas)
    green = (h_ >= 35) & (h_ <= 90) & (s_ > 40)
    dark = v_ < 40
    keep = ~(green | dark)
    if keep.sum() < 10:
        keep = np.ones_like(green, dtype=bool)  # secours : tout garder
    h_, s_, v_ = h_[keep], s_[keep], v_[keep]
    ang = h_ * (2 * np.pi / 180.0)  # teinte OpenCV 0-179 -> radians
    return np.array([s_.mean(), v_.mean(),
                     np.cos(ang).mean() * s_.mean(),
                     np.sin(ang).mean() * s_.mean()])


def assign_teams(video_path: Path, tracking_csv: Path, cfg: dict | None = None) -> Path:
    cfg = cfg or load_video_config()
    n_samp = int(cfg["equipes"]["echantillons_par_track"])

    rows = read_tracking(tracking_csv)
    players = [r for r in rows if r["cls"] == 0]

    # Frames à visiter, groupées pour ne lire la vidéo qu'une fois
    by_track = defaultdict(list)
    for r in players:
        by_track[r["track_id"]].append(r)
    frames_needed = defaultdict(list)  # frame -> [(track_id, row)]
    for tid, rs in by_track.items():
        step = max(1, len(rs) // n_samp)
        for r in rs[::step][:n_samp]:
            frames_needed[r["frame"]].append((tid, r))

    cap = cv2.VideoCapture(str(video_path))
    colors = defaultdict(list)  # track_id -> [hsv...]
    for frame_no in sorted(frames_needed):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = cap.read()
        if not ok:
            continue
        for tid, r in frames_needed[frame_no]:
            c = _torso_color(frame, r["x"], r["y"], r["w"], r["h"])
            if c is not None:
                colors[tid].append(c)
    cap.release()

    track_ids = [t for t in colors if colors[t]]
    if len(track_ids) < 2:
        print("Pas assez de joueurs pour classer les équipes.")
        return tracking_csv

    feats = np.array([np.mean(colors[t], axis=0) for t in track_ids])
    # Standardisation (les dimensions n'ont pas la même échelle)
    mu, sigma = feats.mean(axis=0), feats.std(axis=0) + 1e-6
    feats_std = (feats - mu) / sigma
    labels = KMeans(n_clusters=2, n_init=10, random_state=0).fit_predict(feats_std)
    team_of = {t: ("A" if lab == 0 else "B") for t, lab in zip(track_ids, labels)}

    for r in rows:
        if r["cls"] == 0 and r["track_id"] in team_of:
            r["team"] = team_of[r["track_id"]]

    write_tracking([{k: r.get(k, "") for k in TRACK_FIELDS} for r in rows], tracking_csv)
    a = sum(1 for v in team_of.values() if v == "A")
    b = len(team_of) - a
    print(f"Équipes estimées : A={a} joueurs, B={b} joueurs")
    return tracking_csv


if __name__ == "__main__":
    import sys
    assign_teams(Path(sys.argv[1]), Path(sys.argv[2]))