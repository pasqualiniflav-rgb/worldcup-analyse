"""Détection + suivi des joueurs et du ballon  ->  tracking.csv

S'appuie sur Ultralytics YOLO (détection COCO) + ByteTrack (suivi).
La classe COCO 0 = personne, 32 = ballon de sport.

Import d'ultralytics FAIT À L'INTÉRIEUR de la fonction pour que le reste
du module reste utilisable/testable sans le modèle installé.

    pip install ultralytics        # installe aussi torch
    python detect_track.py chemin/vers/segment.mp4
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

from common import load_video_config, out_dir, write_tracking

CLS_NAMES = {0: "player", 32: "ball"}


def run(video_path: Path, cfg: dict | None = None) -> Path:
    cfg = cfg or load_video_config()
    m = cfg["modele"]
    t = cfg["traitement"]

    from ultralytics import YOLO  # import tardif

    model = YOLO(m["poids"])

    stride = int(t.get("frame_stride") or 1)
    imgsz = int(t.get("redim_largeur") or 1280)

    # Lecture des métadonnées vidéo (fps + nb total d'images) pour la progression
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    cap.release()
    total_steps = (total_frames // stride) if total_frames else 0
    print(f"Détection en cours ({total_frames} images, 1 sur {stride})... "
          f"cela peut prendre plusieurs minutes.")

    rows = []
    # stream=True -> générateur image par image, faible mémoire
    results = model.track(
        source=str(video_path),
        classes=m["classes"],
        conf=m["conf_min"],
        tracker=m["tracker"],
        vid_stride=stride,
        imgsz=imgsz,
        stream=True,
        persist=True,
        verbose=False,
    )

    for frame_idx, r in enumerate(results):
        # Progression toutes les 25 images traitées
        if frame_idx % 25 == 0:
            if total_steps:
                pct = min(100, round(100 * frame_idx / total_steps))
                print(f"  ... {frame_idx}/{total_steps} images traitées ({pct}%)",
                      flush=True)
            else:
                print(f"  ... {frame_idx} images traitées", flush=True)
        boxes = r.boxes
        if boxes is None or boxes.id is None:
            continue
        xywh = boxes.xywh.cpu().numpy()
        ids = boxes.id.int().cpu().numpy()
        clss = boxes.cls.int().cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        real_frame = frame_idx * stride
        for (x, y, w, h), tid, cls, conf in zip(xywh, ids, clss, confs):
            rows.append({
                "frame": real_frame,
                "time_s": round(real_frame / (fps or 25.0), 3),
                "track_id": int(tid),
                "cls": int(cls),
                "cls_name": CLS_NAMES.get(int(cls), str(cls)),
                "x": round(float(x), 1),
                "y": round(float(y), 1),
                "w": round(float(w), 1),
                "h": round(float(h), 1),
                "conf": round(float(conf), 3),
                "team": "",
            })

    out = out_dir() / "tracking.csv"
    write_tracking(rows, out)
    print(f"tracking.csv : {len(rows)} détections suivies -> {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python detect_track.py <video.mp4>")
    run(Path(sys.argv[1]))