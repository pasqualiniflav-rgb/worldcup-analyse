"""Mini-dashboard local (Streamlit).

Tourne 100% en local, sans internet :
    pip install streamlit
    streamlit run app/dashboard.py

Permet de : filtrer l'effectif, voir les alertes, ouvrir la fiche
d'un joueur, et relancer l'ingestion depuis l'Excel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Rendre les modules de scripts/ importables
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from config import load_config, INPUT_DIR  # noqa: E402
from db import get_connection  # noqa: E402
from analytics import list_players, player_stats, squad_overview  # noqa: E402
from ingest import ingest  # noqa: E402

CFG = load_config()
st.set_page_config(page_title="Module Joueurs", layout="wide")

st.sidebar.title(CFG["client"]["nom"])
st.sidebar.caption("Module Joueurs — démo locale")

if st.sidebar.button("🔄 Ré-importer depuis l'Excel"):
    counts = ingest(INPUT_DIR / "saisie_selection.xlsx")
    st.sidebar.success("Base mise à jour : " + ", ".join(f"{k}={v}" for k, v in counts.items()))

conn = get_connection()
players = list_players(conn)

if not players:
    st.warning("Base vide. Lancez l'ingestion (bouton dans la barre latérale).")
    st.stop()

# ---- Filtres ----
sels = sorted({p["selection"] for p in players if p["selection"]})
postes = sorted({p["poste"] for p in players if p["poste"]})
f_sel = st.sidebar.multiselect("Sélection", sels, default=sels)
f_poste = st.sidebar.multiselect("Poste", postes, default=postes)

tab1, tab2 = st.tabs(["📋 Effectif", "👤 Fiche joueur"])

with tab1:
    st.subheader("Vue d'ensemble de l'effectif")
    rows = squad_overview(conn)
    df = pd.DataFrame(rows)
    df = df[df["selection"].isin(f_sel) & df["poste"].isin(f_poste)]
    st.dataframe(
        df.rename(columns={
            "nom": "Joueur", "poste": "Poste", "selection": "Sélection",
            "statut": "Statut", "club": "Club", "note_moy_recente": "Note réc.",
            "pct_temps": "Tps jeu %", "nb_alertes": "Alertes", "statut_med": "Médical",
        }).drop(columns=["player_id"]),
        use_container_width=True, hide_index=True,
    )
    n_alertes = sum(r["nb_alertes"] for r in rows)
    st.metric("Joueurs avec alerte", sum(1 for r in rows if r["nb_alertes"]))

with tab2:
    options = {f'{p["prenom"]} {p["nom"]} ({p["poste"]})': p["player_id"]
               for p in players
               if p["selection"] in f_sel and p["poste"] in f_poste}
    if not options:
        st.info("Aucun joueur ne correspond aux filtres.")
        st.stop()
    choice = st.selectbox("Choisir un joueur", list(options.keys()))
    s = player_stats(options[choice], conn)
    j = s["joueur"]

    st.subheader(f'{j["prenom"]} {j["nom"]}')
    st.caption(f'{s["age"]} ans · {j["poste"]} · {j["selection"]} · {j["club"]} ({j["pays_club"]})')

    for a in s["alertes"]:
        (st.error if a["niveau"] == "danger" else st.warning)("⚠ " + a["texte"])
    if not s["alertes"]:
        st.success("✔ Aucune alerte — joueur disponible et en rythme.")

    c = st.columns(5)
    c[0].metric("Note récente", s["note_moy_recente"] or "—")
    c[1].metric("Note globale", s["note_moy"] or "—")
    c[2].metric("Observations", s["nb_obs"])
    c[3].metric("Temps de jeu", f'{s["pct_temps"]}%')
    c[4].metric("Titularisations", f'{s["pct_titu"]}%')

    st.markdown("#### Observations vidéo")
    obs = pd.DataFrame(s["observations"])
    if not obs.empty:
        obs = obs[["date", "contexte", "adversaire", "note_globale",
                   "code_action", "commentaire", "video_link"]]
        st.dataframe(
            obs, use_container_width=True, hide_index=True,
            column_config={"video_link": st.column_config.LinkColumn("Vidéo", display_text="▶ ouvrir")},
        )
