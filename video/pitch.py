"""Terrain vu du dessus (top-down) + homographie.

- draw_pitch() : dessine un terrain standard (105 x 68 m) vu d'en haut.
- load/apply homographie : convertit des points image -> coordonnées terrain.
- heatmap_topdown() : heatmap d'un joueur/équipe projetée sur le terrain.

Rappel : une homographie FIXE suppose une caméra FIXE. Sur une caméra qui
bouge (retransmission TV), le résultat est approximatif.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import read_tracking, out_dir, load_video_config

# Dimensions terrain (mètres)
PITCH_L, PITCH_W = 105.0, 68.0

# Points de repère nommés (coordonnées terrain en mètres).
# Utilisés par l'outil de calibration : le staff clique ces points sur l'image.
# Surface GAUCHE : ligne de but à x=0, ligne de surface à x=16.5.
LANDMARKS_LEFT_BOX = {
    "coin surface haut (ligne de but)": (0.0, 13.84),
    "coin surface haut (ligne surface)": (16.5, 13.84),
    "coin surface bas (ligne surface)": (16.5, 54.16),
    "coin surface bas (ligne de but)": (0.0, 54.16),
}
# Surface DROITE : ligne de but à x=105, ligne de surface à x=88.5.
LANDMARKS_RIGHT_BOX = {
    "coin surface haut (ligne de but)": (PITCH_L, 13.84),
    "coin surface haut (ligne surface)": (PITCH_L - 16.5, 13.84),
    "coin surface bas (ligne surface)": (PITCH_L - 16.5, 54.16),
    "coin surface bas (ligne de but)": (PITCH_L, 54.16),
}


def landmarks_for_side(side: str) -> dict:
    """'gauche'/'left' ou 'droite'/'right' -> repères de la bonne surface."""
    s = (side or "gauche").strip().lower()
    if s in ("droite", "right", "d", "r"):
        return LANDMARKS_RIGHT_BOX
    return LANDMARKS_LEFT_BOX


def draw_pitch(scale: int = 12) -> np.ndarray:
    """Retourne une image BGR du terrain vu du dessus. scale = pixels/mètre."""
    W, H = int(PITCH_L * scale), int(PITCH_W * scale)
    img = np.full((H, W, 3), (58, 115, 68), np.uint8)  # vert
    white = (245, 245, 245)
    t = max(2, scale // 4)

    def m(x, y):
        return (int(round(x * scale)), int(round(y * scale)))

    cv2.rectangle(img, m(0, 0), m(PITCH_L, PITCH_W), white, t)           # contour
    cv2.line(img, m(PITCH_L / 2, 0), m(PITCH_L / 2, PITCH_W), white, t)  # médiane
    cv2.circle(img, m(PITCH_L / 2, PITCH_W / 2), int(9.15 * scale), white, t)
    cv2.circle(img, m(PITCH_L / 2, PITCH_W / 2), max(3, t), white, -1)
    # Surfaces : gauche (x=0) s'étend VERS L'INTÉRIEUR (+), droite (x=105) vers (-)
    for gx in (0, PITCH_L):
        s = 1 if gx == 0 else -1
        cv2.rectangle(img, m(gx, 13.84), m(gx + s * 16.5, 54.16), white, t)   # réparation
        cv2.rectangle(img, m(gx, 24.84), m(gx + s * 5.5, 43.16), white, t)    # but
        cv2.circle(img, m(gx + s * 11, PITCH_W / 2), max(3, t), white, -1)    # point de penalty
    return img


def load_homography(path: Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return np.array(data["H"], dtype=float)


def save_homography(H, image_pts, pitch_pts, path: Path):
    Path(path).write_text(json.dumps({
        "H": H.tolist(),
        "image_pts": [list(map(float, p)) for p in image_pts],
        "pitch_pts": [list(map(float, p)) for p in pitch_pts],
    }, indent=2), encoding="utf-8")


def compute_homography(image_pts, pitch_pts):
    src = np.array(image_pts, dtype=np.float32)
    dst = np.array(pitch_pts, dtype=np.float32)
    H, _ = cv2.findHomography(src, dst, method=0)
    return H


def image_to_pitch(H, pts_xy):
    """pts_xy : liste de (x, y) en pixels -> array (N,2) en mètres terrain."""
    pts = np.array(pts_xy, dtype=np.float32).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(pts, H).reshape(-1, 2)
    return out


def heatmap_topdown(tracking_csv: Path, homography_json: Path,
                    track_id: int | None = None, team: str | None = None,
                    out_png: Path | None = None, scale: int = 10):
    rows = read_tracking(tracking_csv)
    if track_id is not None:
        sel = [r for r in rows if r["track_id"] == track_id and r["cls"] == 0]
        titre, suffix = f"Heatmap terrain — joueur #{track_id}", f"top_joueur_{track_id}"
    elif team is not None:
        sel = [r for r in rows if r.get("team") == team and r["cls"] == 0]
        titre, suffix = f"Heatmap terrain — équipe {team}", f"top_equipe_{team}"
    else:
        raise ValueError("Préciser track_id ou team.")
    if not sel:
        print("Aucune position pour cette cible.")
        return None

    H = load_homography(homography_json)
    # point au sol = milieu bas de la boîte (les pieds)
    feet = [(r["x"], r["y"] + r["h"] / 2) for r in sel]
    pitch_pts = image_to_pitch(H, feet)
    # Correction d'orientation éventuelle (sans recalibration)
    hg = load_video_config().get("homographie") or {}
    if hg.get("flip_x"):
        pitch_pts[:, 0] = PITCH_L - pitch_pts[:, 0]
    if hg.get("flip_y"):
        pitch_pts[:, 1] = PITCH_W - pitch_pts[:, 1]
    # garde ce qui tombe dans le terrain (petite marge)
    m = 3
    mask = ((pitch_pts[:, 0] > -m) & (pitch_pts[:, 0] < PITCH_L + m) &
            (pitch_pts[:, 1] > -m) & (pitch_pts[:, 1] < PITCH_W + m))
    pitch_pts = pitch_pts[mask]
    if len(pitch_pts) == 0:
        print("Aucun point projeté ne tombe sur le terrain (calibration à revoir ?).")
        return None

    pitch = draw_pitch(scale)
    Hpx, Wpx = pitch.shape[:2]
    xs = np.clip(pitch_pts[:, 0] * scale, 0, Wpx - 1)
    ys = np.clip(pitch_pts[:, 1] * scale, 0, Hpx - 1)
    hist, _, _ = np.histogram2d(xs, ys, bins=[Wpx // 20, Hpx // 20],
                                range=[[0, Wpx], [0, Hpx]])

    fig, ax = plt.subplots(figsize=(11, 11 * Hpx / Wpx))
    ax.imshow(cv2.cvtColor(pitch, cv2.COLOR_BGR2RGB), extent=[0, Wpx, Hpx, 0])
    ax.imshow(hist.T, origin="upper", extent=[0, Wpx, Hpx, 0],
              cmap="hot", alpha=0.55, interpolation="gaussian", aspect="auto")
    ax.set_title(titre, fontsize=13)
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    out_png = out_png or (out_dir() / f"heatmap_{suffix}.png")
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"Heatmap vue du dessus -> {out_png}")
    return out_png