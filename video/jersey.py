"""Lecture des numéros de maillot -> identité stable des joueurs.

Idée : le numéro ne change jamais. Pour chaque joueur suivi, on lit le
numéro sur les images les plus nettes (joueur proche/grand), on agrège
par vote majoritaire, et on écrit ce numéro dans tracking.csv (colonne
`numero`) + un récapitulatif numeros.json.

Réserve honnête : sur un plan large, le numéro n'est lisible que sur une
fraction des joueurs (proches de la caméra). C'est normal ; quelques
lectures fiables suffisent à étiqueter tout le track.

    pip install easyocr
    python jersey.py            # utilise out/segment.mp4 + out/tracking.csv
"""
from __future__ import annotations

from collections import defaultdict, Counter
import json
from pathlib import Path

import cv2
import numpy as np

from common import load_video_config, out_dir, read_tracking, write_tracking, TRACK_FIELDS

# OCR chargé paresseusement (dépendance lourde) ; injectable pour les tests.
_READER = None


def _get_reader():
    global _READER
    if _READER is None:
        import easyocr  # import tardif
        _READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _READER


def _read_digits(crop, ocr=None):
    """Retourne (numero:str, conf:float) ou (None, 0). numero = 1 à 2 chiffres."""
    if crop is None or crop.size == 0:
        return None, 0.0
    # agrandit le crop pour aider l'OCR sur petits chiffres
    h, w = crop.shape[:2]
    if max(h, w) < 120:
        f = 3
        crop = cv2.resize(crop, (w * f, h * f), interpolation=cv2.INTER_CUBIC)
    reader = ocr or _get_reader()
    results = reader.readtext(crop, allowlist="0123456789", detail=1, paragraph=False)
    best, best_c = None, 0.0
    for _, text, conf in results:
        text = "".join(ch for ch in text if ch.isdigit())
        if 1 <= len(text) <= 2 and conf > best_c:
            best, best_c = text, float(conf)
    return best, best_c


def _back_crop(frame, x, y, w, h):
    """Bande haute du torse/dos, où se trouve le plus souvent le numéro."""
    H, W = frame.shape[:2]
    x1 = int(max(0, x - w * 0.30)); x2 = int(min(W, x + w * 0.30))
    y1 = int(max(0, y - h * 0.38)); y2 = int(min(H, y - h * 0.02))
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def read_numbers(video_path: Path, tracking_csv: Path, cfg=None, ocr=None) -> Path:
    cfg = cfg or load_video_config()
    jr = cfg.get("numeros") or {}
    n_samp = int(jr.get("echantillons_par_track", 12))
    min_conf = float(jr.get("conf_min", 0.4))
    min_lectures = int(jr.get("lectures_min", 2))
    min_avg = float(jr.get("conf_moyenne_min", 0.45))

    rows = read_tracking(tracking_csv)
    players = [r for r in rows if r["cls"] == 0]

    # pour chaque track, on garde les N frames où la boîte est la plus grande
    by_track = defaultdict(list)
    for r in players:
        by_track[r["track_id"]].append(r)
    frames_needed = defaultdict(list)  # frame -> [(track_id, row)]
    for tid, rs in by_track.items():
        rs_sorted = sorted(rs, key=lambda r: r["w"] * r["h"], reverse=True)[:n_samp]
        for r in rs_sorted:
            frames_needed[r["frame"]].append((tid, r))

    # Source de lecture : vidéo d'origine HAUTE RÉSOLUTION si disponible,
    # sinon le segment réduit. En HD, les chiffres sont bien plus lisibles.
    meta_path = out_dir() / "segment_meta.json"
    meta = None
    if jr.get("haute_resolution", True) and meta_path.exists():
        try:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            if Path(m["source"]).exists():
                meta = m
        except Exception:
            meta = None

    if meta:
        cap = cv2.VideoCapture(meta["source"])
        scale = float(meta.get("scale", 1.0))
        start_s = float(meta.get("start_s", 0.0))
        seg_fps = float(meta.get("seg_fps", 25.0)) or 25.0
        print(f"Lecture des numéros en HAUTE RÉSOLUTION "
              f"({meta['orig_w']}x{meta['orig_h']}, échelle x{scale:.2f})...")
    else:
        cap = cv2.VideoCapture(str(video_path))
        scale, start_s, seg_fps = 1.0, 0.0, 25.0
        print("Lecture des numéros sur le segment (résolution réduite)...")

    votes = defaultdict(Counter)   # track_id -> Counter({numero: poids})
    reads = defaultdict(int)
    for i, frame_no in enumerate(sorted(frames_needed)):
        if meta:
            cap.set(cv2.CAP_PROP_POS_MSEC, (start_s + frame_no / seg_fps) * 1000.0)
        else:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = cap.read()
        if not ok:
            continue
        for tid, r in frames_needed[frame_no]:
            crop = _back_crop(frame, r["x"] * scale, r["y"] * scale,
                              r["w"] * scale, r["h"] * scale)
            num, conf = _read_digits(crop, ocr)
            if num is not None and conf >= min_conf:
                votes[tid][num] += conf
                reads[tid] += 1
        if i % 50 == 0:
            print(f"  ... {i}/{len(frames_needed)} images lues", flush=True)
    cap.release()

    # décision par track
    numero_of = {}
    summary = {}
    for tid, cnt in votes.items():
        if reads[tid] < min_lectures:
            continue
        num, poids = cnt.most_common(1)[0]
        avg = poids / reads[tid]
        # garde-fous : confiance moyenne suffisante + numéro plausible (1..99)
        if avg < min_avg:
            continue
        if not num.isdigit() or int(num) == 0:
            continue
        numero_of[tid] = num
        summary[str(tid)] = {"numero": num, "lectures": reads[tid],
                             "score": round(poids, 2),
                             "conf_moyenne": round(avg, 2)}

    # réécrit tracking.csv : on EFFACE d'abord les anciens numéros, puis on
    # applique uniquement ceux du passage courant (évite les résidus).
    for r in rows:
        if r["cls"] == 0:
            r["numero"] = numero_of.get(r["track_id"], "")
    write_tracking([{k: r.get(k, "") for k in TRACK_FIELDS} for r in rows], tracking_csv)

    out_json = out_dir() / "numeros.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nNuméros identifiés : {len(numero_of)} joueurs sur {len(by_track)} tracks")
    print(f"Récapitulatif -> {out_json}")
    return out_json


def apply_numbers_from_json(tracking_csv: Path, json_path: Path | None = None) -> Path:
    """Resynchronise la colonne `numero` de tracking.csv depuis numeros.json
    (référence propre), sans relancer l'OCR. Efface tout résidu."""
    json_path = json_path or (out_dir() / "numeros.json")
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    num_by_tid = {int(k): str(v["numero"]) for k, v in data.items()}
    rows = read_tracking(tracking_csv)
    for r in rows:
        if r["cls"] == 0:
            r["numero"] = num_by_tid.get(r["track_id"], "")
    write_tracking([{k: r.get(k, "") for k in TRACK_FIELDS} for r in rows], tracking_csv)
    print(f"tracking.csv resynchronisé depuis {json_path.name} : "
          f"{len(num_by_tid)} numéros appliqués.")
    return tracking_csv


if __name__ == "__main__":
    od = out_dir()
    read_numbers(od / "segment.mp4", od / "tracking.csv")