"""Calcul des indicateurs et des alertes à partir de la base.

Toute la "logique métier" est ici, séparée de l'affichage.
"""
from __future__ import annotations

from datetime import date, datetime

from config import load_config
from db import get_connection

CFG = load_config()
AL = CFG["alertes"]

REF_DATE = date(2026, 7, 27)  # "aujourd'hui" de la démo


def _d(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _fmt_ts(seconds):
    if seconds is None:
        return ""
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def _video_link(url, ts):
    """Construit un lien qui rouvre la vidéo à l'horodatage (YouTube &t=)."""
    if not url:
        return None
    if ts and "youtube.com" in str(url):
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}t={int(ts)}s"
    return url


def list_players(conn=None):
    conn = conn or get_connection()
    rows = conn.execute(
        "SELECT * FROM joueurs ORDER BY selection, poste, nom"
    ).fetchall()
    return [dict(r) for r in rows]


def player_stats(player_id, conn=None):
    conn = conn or get_connection()
    j = conn.execute("SELECT * FROM joueurs WHERE player_id=?", (player_id,)).fetchone()
    if not j:
        return None
    joueur = dict(j)

    obs = [dict(r) for r in conn.execute(
        "SELECT * FROM observations WHERE player_id=? ORDER BY date DESC", (player_id,)
    ).fetchall()]
    tj = [dict(r) for r in conn.execute(
        "SELECT * FROM temps_jeu WHERE player_id=? ORDER BY date DESC", (player_id,)
    ).fetchall()]
    med = [dict(r) for r in conn.execute(
        "SELECT * FROM dispo_medicale WHERE player_id=? ORDER BY date DESC", (player_id,)
    ).fetchall()]

    # --- Notes d'observation ---
    notes = [o["note_globale"] for o in obs if o["note_globale"] is not None]
    note_moy = round(sum(notes) / len(notes), 2) if notes else None
    notes_recentes = notes[:5]
    note_moy_recente = round(sum(notes_recentes) / len(notes_recentes), 2) if notes_recentes else None

    # Liens vidéo horodatés
    for o in obs:
        o["video_link"] = _video_link(o.get("video_url"), o.get("video_ts"))
        o["ts_label"] = _fmt_ts(o.get("video_ts"))

    # --- Temps de jeu en club ---
    total_min = sum((t["minutes"] or 0) for t in tj)
    nb_matchs = len(tj)
    nb_titu = sum(1 for t in tj if t.get("titulaire") == 1)
    pct_titu = round(100 * nb_titu / nb_matchs) if nb_matchs else 0
    max_possible = nb_matchs * 90
    pct_temps = round(100 * total_min / max_possible) if max_possible else 0
    buts = sum((t.get("buts") or 0) for t in tj)
    passes = sum((t.get("passes_d") or 0) for t in tj)

    # Dernier match réellement joué (minutes > 0)
    dates_jouees = [_d(t["date"]) for t in tj if (t.get("minutes") or 0) > 0]
    dates_jouees = [d for d in dates_jouees if d]
    dernier_match = max(dates_jouees) if dates_jouees else None
    jours_sans_match = (REF_DATE - dernier_match).days if dernier_match else None

    # --- Statut médical courant ---
    statut_med = med[0] if med else None

    # --- Alertes ---
    alertes = []
    if statut_med and statut_med.get("statut") in ("Blessé", "Incertain"):
        lbl = statut_med.get("type_blessure") or "raison non précisée"
        alertes.append({
            "niveau": "danger" if statut_med["statut"] == "Blessé" else "warn",
            "texte": f"Statut médical : {statut_med['statut']} ({lbl}) — "
                     f"retour prévu {statut_med.get('retour_prevu') or 'à confirmer'}",
        })
    if jours_sans_match is not None and jours_sans_match > AL["jours_sans_match_max"]:
        alertes.append({
            "niveau": "warn",
            "texte": f"{jours_sans_match} jours sans match joué "
                     f"(seuil {AL['jours_sans_match_max']} j)",
        })
    if note_moy_recente is not None and note_moy_recente < AL["note_forme_basse"]:
        alertes.append({
            "niveau": "warn",
            "texte": f"Forme en baisse : moyenne récente {note_moy_recente} "
                     f"(< {AL['note_forme_basse']})",
        })
    if nb_matchs and pct_temps < AL["temps_jeu_faible_pct"]:
        alertes.append({
            "niveau": "warn",
            "texte": f"Faible temps de jeu en club : {pct_temps}% "
                     f"(< {AL['temps_jeu_faible_pct']}%)",
        })

    return {
        "joueur": joueur,
        "age": (REF_DATE - _d(joueur.get("date_naissance"))).days // 365
               if _d(joueur.get("date_naissance")) else None,
        "note_moy": note_moy,
        "note_moy_recente": note_moy_recente,
        "nb_obs": len(obs),
        "observations": obs,
        "total_min": total_min,
        "nb_matchs": nb_matchs,
        "pct_titu": pct_titu,
        "pct_temps": pct_temps,
        "buts": buts,
        "passes": passes,
        "dernier_match": dernier_match.isoformat() if dernier_match else "—",
        "jours_sans_match": jours_sans_match,
        "statut_med": statut_med,
        "medical": med,
        "alertes": alertes,
    }


def squad_overview(conn=None):
    """Vue d'ensemble de l'effectif avec indicateurs clés + alertes."""
    conn = conn or get_connection()
    out = []
    for j in list_players(conn):
        s = player_stats(j["player_id"], conn)
        out.append({
            "player_id": j["player_id"],
            "nom": f"{j['prenom']} {j['nom']}",
            "poste": j["poste"],
            "selection": j["selection"],
            "statut": j["statut"],
            "club": j["club"],
            "note_moy_recente": s["note_moy_recente"],
            "pct_temps": s["pct_temps"],
            "nb_alertes": len(s["alertes"]),
            "statut_med": s["statut_med"]["statut"] if s["statut_med"] else "—",
        })
    return out


if __name__ == "__main__":
    s = player_stats("JOU002")
    print(s["joueur"]["nom"], "- alertes:", [a["texte"] for a in s["alertes"]])
