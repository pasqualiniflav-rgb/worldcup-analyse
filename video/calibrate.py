"""Calibration terrain (homographie) par clics — pour la vue du dessus.

Ouvre une image du match et te demande de cliquer, DANS L'ORDRE, 4 repères
connus du terrain (les 4 coins d'une surface de réparation). On en déduit
la transformation image -> terrain, sauvegardée dans out/homography.json.

    python calibrate.py                 # image à 0 s, surface GAUCHE (défaut)
    python calibrate.py 35              # image à 35 s, surface gauche
    python calibrate.py 35 droite       # image à 35 s, surface DROITE

Choisis un instant où la surface de réparation choisie est BIEN visible,
et précise 'gauche' ou 'droite' selon la surface que tu vas cliquer.
Astuce caméra fixe : une seule calibration suffit pour toute la vidéo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

from common import out_dir
from pitch import (landmarks_for_side, compute_homography, save_homography,
                   image_to_pitch)


def _grab_frame(seconds: float):
    seg = out_dir() / "segment.mp4"
    if not seg.exists():
        sys.exit("out/segment.mp4 introuvable : lance d'abord 'run_video.py prep'.")
    cap = cv2.VideoCapture(str(seg))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(seconds * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit("Impossible de lire l'image à cet instant.")
    return frame


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    side = sys.argv[2] if len(sys.argv) > 2 else "gauche"
    landmarks = landmarks_for_side(side)
    order = list(landmarks.keys())
    pitch_pts = [landmarks[k] for k in order]
    print(f"Calibration sur la surface : {side.upper()}")
    frame = _grab_frame(seconds)
    clicks = []

    def banner(img):
        i = len(clicks)
        txt = f"Clique : {order[i]}" if i < len(order) else "Terminé - touche 's' pour sauver"
        disp = img.copy()
        cv2.rectangle(disp, (0, 0), (disp.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(disp, f"[{i}/4] {txt}", (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        for k, (px, py) in enumerate(clicks):
            cv2.circle(disp, (px, py), 6, (0, 255, 255), -1)
            cv2.putText(disp, str(k + 1), (px + 8, py),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        return disp

    win = "Calibration terrain - clique les 4 coins de la surface"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 4:
            clicks.append((x, y))
            cv2.imshow(win, banner(frame))

    cv2.setMouseCallback(win, on_mouse)
    cv2.imshow(win, banner(frame))
    print("Clique les 4 repères dans l'ordre affiché.")
    for k in order:
        print("  -", k)
    print("Puis appuie sur 's' pour sauver, 'r' pour recommencer, 'q' pour annuler.")

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key == ord("r"):
            clicks.clear(); cv2.imshow(win, banner(frame))
        elif key == ord("q"):
            cv2.destroyAllWindows(); return
        elif key == ord("s") and len(clicks) == 4:
            break
    cv2.destroyAllWindows()

    H = compute_homography(clicks, pitch_pts)
    out = out_dir() / "homography.json"
    save_homography(H, clicks, pitch_pts, out)
    # petite vérif : réprojection des points cliqués
    check = image_to_pitch(H, clicks)
    print("\nCalibration sauvegardée ->", out)
    print("Vérif (doit être proche des repères terrain) :")
    for name, got in zip(order, check):
        print(f"  {name:38s} -> ({got[0]:.1f}, {got[1]:.1f}) m")
    print("\nTu peux maintenant relancer : python run_video.py clip <ID>")


if __name__ == "__main__":
    main()