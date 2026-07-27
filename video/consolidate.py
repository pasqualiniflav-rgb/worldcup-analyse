"""Consolidation : regroupe les fragments de suivi par (équipe, numéro).

Le tracker fragmente l'identité (un joueur = plusieurs track_id). Quand le
numéro de maillot est connu, on peut recoller : tous les tracks qui portent
le même numéro dans la même équipe = UN joueur. On obtient alors :
  - un effectif vidéo (roster) : un joueur par numéro identifié,
  - un montage / une heatmap FUSIONNÉS (tous ses fragments réunis).

    python consolidate.py roster            # affiche + sauve l'effectif vidéo
    python consolidate.py clip 5 B          # film + heatmap du n°5 équipe B
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from common import (load_video_config, out_dir, read_tracking, write_tracking,
                    TRACK_FIELDS)
import pipeline


def _seg_fps() -> float:
    meta = out_dir() / "segment_meta.json"
    if meta.exists():
        try:
            return float(json.loads(meta.read_text(encoding="utf-8")).get("seg_fps", 25.0))
        except Exception:
            pass
    return 25.0


def roster(tracking_csv: Path):
    """Effectif vidéo : un joueur par (équipe, numéro) identifié."""
    rows = read_tracking(tracking_csv)
    players = [r for r in rows if r["cls"] == 0]
    fps = _seg_fps()

    grouped = defaultdict(lambda: {"tracks": set(), "detections": 0})
    identified_tracks = set()
    for r in players:
        num = r.get("numero")
        if not num:
            continue
        key = (r.get("team") or "?", str(num))
        grouped[key]["tracks"].add(r["track_id"])
        grouped[key]["detections"] += 1
        identified_tracks.add(r["track_id"])

    roster_list = []
    for (team, num), g in sorted(grouped.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
        roster_list.append({
            "equipe": team,
            "numero": num,
            "fragments": len(g["tracks"]),
            "detections": g["detections"],
            "secondes_presence": round(g["detections"] / fps, 1),
            "track_ids": sorted(g["tracks"]),
        })

    total_tracks = len({r["track_id"] for r in players})
    print(f"\nEFFECTIF VIDÉO — {len(roster_list)} joueurs identifiés par leur numéro")
    print(f"(sur {total_tracks} fragments de suivi ; {len(identified_tracks)} rattachés)\n")
    print(f"  {'Équipe':7} {'N°':>3}  {'Frag.':>5}  {'Présence':>9}")
    for p in roster_list:
        print(f"  {p['equipe']:7} {p['numero']:>3}  {p['fragments']:>5}  "
              f"{p['secondes_presence']:>7}s")

    out_json = out_dir() / "joueurs_video.json"
    out_json.write_text(json.dumps(roster_list, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEffectif -> {out_json}")
    return roster_list


def _tracks_for(rows, numero, team):
    return {r["track_id"] for r in rows
            if r["cls"] == 0 and str(r.get("numero")) == str(numero)
            and (team is None or r.get("team") == team)}


def merged_player(numero, team, cfg=None):
    """Fusionne tous les fragments d'un joueur (numéro+équipe) et produit
    son montage, sa heatmap et sa vignette."""
    cfg = cfg or load_video_config()
    seg = out_dir() / "segment.mp4"
    csv_path = out_dir() / "tracking.csv"
    rows = read_tracking(csv_path)

    ids = _tracks_for(rows, numero, team)
    if not ids:
        print(f"Aucun fragment pour le n°{numero} équipe {team}.")
        return None

    # Astuce : on ré-étiquette tous ces fragments avec UN seul id virtuel,
    # puis on réutilise les fonctions existantes.
    vid = 900000 + int(numero)
    merged_rows = []
    for r in rows:
        r2 = dict(r)
        if r["track_id"] in ids:
            r2["track_id"] = vid
        merged_rows.append(r2)
    tmp = out_dir() / "_merged_tracking.csv"
    write_tracking([{k: r.get(k, "") for k in TRACK_FIELDS} for r in merged_rows], tmp)

    tag = f"num{numero}_{team or 'X'}"
    print(f"Joueur n°{numero} ({team}) : {len(ids)} fragments réunis "
          f"[{', '.join(map(str, sorted(ids)))}]")

    pipeline.player_thumbnail(seg, tmp, vid, out_png=out_dir() / f"joueur_{tag}_identite.png")
    pipeline.annotated_montage(seg, tmp, vid, cfg, out_path=out_dir() / f"montage_{tag}.mp4")

    homo = out_dir() / "homography.json"
    if homo.exists():
        from pitch import heatmap_topdown
        heatmap_topdown(tmp, homo, track_id=vid, out_png=out_dir() / f"heatmap_top_{tag}.png")
    else:
        pipeline.heatmap(tmp, track_id=vid, video_path=seg,
                         out_png=out_dir() / f"heatmap_{tag}.png")
    print(f"Sorties fusionnées -> montage_{tag}.mp4 / heatmap / vignette")
    return tag


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python consolidate.py roster | clip <numero> [equipe]")
    if sys.argv[1] == "roster":
        roster(out_dir() / "tracking.csv")
    elif sys.argv[1] == "clip":
        numero = sys.argv[2]
        team = sys.argv[3] if len(sys.argv) > 3 else None
        merged_player(numero, team)
    else:
        sys.exit("Commande inconnue. Utilise 'roster' ou 'clip <numero> [equipe]'.")


if __name__ == "__main__":
    main()