"""Génère les rapports HTML (fiche joueur + index effectif).

Sortie autonome (CSS en ligne, aucun réseau) dans reports/.
Convertible en PDF en ouvrant le HTML puis "Imprimer > PDF", ou via
un moteur type weasyprint si installé.

Usage :
    python report.py               # génère l'index + toutes les fiches
    python report.py JOU002        # génère une fiche précise
"""
from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, BaseLoader

from config import load_config, REPORTS_DIR
from db import get_connection
from analytics import list_players, player_stats, squad_overview, REF_DATE

CFG = load_config()
B = CFG["branding"]
CLIENT = CFG["client"]["nom"]

BASE_CSS = """
:root{
  --prim: __PRIM__; --sec: __SEC__; --acc: __ACC__;
  --ink:#1a1f2b; --muted:#6b7280; --line:#e5e7eb; --bg:#f7f8fa; --card:#ffffff;
}
*{box-sizing:border-box;}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink);background:var(--bg);line-height:1.5;}
a{color:var(--prim);}
.wrap{max-width:960px;margin:0 auto;padding:24px;}
.top{display:flex;align-items:center;justify-content:space-between;
  border-bottom:3px solid var(--sec);padding-bottom:12px;margin-bottom:20px;}
.top .client{font-size:13px;letter-spacing:.5px;text-transform:uppercase;
  color:var(--prim);font-weight:700;}
.top .meta{font-size:12px;color:var(--muted);text-align:right;}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;
  font-weight:600;background:var(--prim);color:#fff;}
.badge.sec{background:var(--sec);color:#20140a;}
.badge.ghost{background:#eef0f3;color:var(--ink);}
h1{font-size:26px;margin:4px 0 2px;}
.sub{color:var(--muted);font-size:14px;margin-bottom:18px;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0;}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;}
.tile .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;}
.tile .v{font-size:26px;font-weight:700;margin-top:4px;}
.tile .u{font-size:13px;color:var(--muted);font-weight:500;}
.section{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;margin:16px 0;}
.section h2{font-size:15px;margin:0 0 12px;text-transform:uppercase;letter-spacing:.5px;
  color:var(--prim);}
table{width:100%;border-collapse:collapse;font-size:13px;}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;}
th{color:var(--muted);font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.3px;}
tr:last-child td{border-bottom:none;}
.alert{padding:10px 14px;border-radius:10px;margin:8px 0;font-size:14px;font-weight:500;
  display:flex;gap:8px;align-items:center;}
.alert.danger{background:#fdecee;color:#8a1c2b;border:1px solid #f3c2c9;}
.alert.warn{background:#fff6e6;color:#8a5a00;border:1px solid #f3dEa8;}
.alert.ok{background:#eaf6ee;color:#1c6b38;border:1px solid #bfe4cc;}
.pill{font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;}
.pill.Apte{background:#eaf6ee;color:#1c6b38;}
.pill.Blessé,.pill.Blesse{background:#fdecee;color:#8a1c2b;}
.pill.Reprise{background:#fff6e6;color:#8a5a00;}
.pill.Incertain{background:#eef0f3;color:#444;}
.bar{height:8px;background:#eef0f3;border-radius:6px;overflow:hidden;}
.bar>span{display:block;height:100%;background:var(--prim);}
.code{font-family:ui-monospace,Menlo,monospace;font-size:12px;background:#eef0f3;
  padding:1px 6px;border-radius:5px;}
.foot{color:var(--muted);font-size:11px;text-align:center;margin:24px 0 8px;}
.rowlink{color:var(--prim);font-weight:600;text-decoration:none;}
""".replace("__PRIM__", B["couleur_primaire"]).replace("__SEC__", B["couleur_secondaire"]).replace("__ACC__", B["couleur_accent"])

PLAYER_TMPL = """<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{{ s.joueur.prenom }} {{ s.joueur.nom }} — Fiche joueur</title>
<style>{{ css }}</style></head><body><div class=wrap>
<div class=top>
  <div class=client>{{ client }}</div>
  <div class=meta>Fiche joueur · Module Joueurs<br>Éditée le {{ ref }}</div>
</div>

<div><span class="badge">{{ s.joueur.selection }}</span>
  <span class="badge sec">{{ s.joueur.poste }}</span>
  <span class="badge ghost">{{ s.joueur.statut }}</span></div>
<h1>{{ s.joueur.prenom }} {{ s.joueur.nom }}</h1>
<div class=sub>
  {{ s.age or "?" }} ans · Pied {{ s.joueur.pied or "—" }} · {{ s.joueur.taille_cm or "—" }} cm ·
  {{ s.joueur.club }} ({{ s.joueur.pays_club }})
</div>

{% if s.alertes %}
  {% for a in s.alertes %}
  <div class="alert {{ a.niveau }}">⚠ {{ a.texte }}</div>
  {% endfor %}
{% else %}
  <div class="alert ok">✔ Aucune alerte — joueur disponible et en rythme.</div>
{% endif %}

<div class=grid>
  <div class=tile><div class=k>Note moy. récente</div>
    <div class=v>{{ s.note_moy_recente or "—" }}<span class=u> /10</span></div></div>
  <div class=tile><div class=k>Note moy. globale</div>
    <div class=v>{{ s.note_moy or "—" }}<span class=u> /10</span></div></div>
  <div class=tile><div class=k>Observations</div>
    <div class=v>{{ s.nb_obs }}</div></div>
  <div class=tile><div class=k>Temps de jeu club</div>
    <div class=v>{{ s.pct_temps }}<span class=u>%</span></div></div>
  <div class=tile><div class=k>Titularisations</div>
    <div class=v>{{ s.pct_titu }}<span class=u>%</span></div></div>
  <div class=tile><div class=k>Dernier match joué</div>
    <div class=v style="font-size:18px">{{ s.dernier_match }}</div>
    <div class=u>{% if s.jours_sans_match is not none %}il y a {{ s.jours_sans_match }} j{% endif %}</div></div>
</div>

<div class=section>
  <h2>Statut médical / disponibilité</h2>
  {% if s.statut_med %}
    <p><span class="pill {{ s.statut_med.statut|replace('é','e') }}">{{ s.statut_med.statut }}</span>
      {{ s.statut_med.type_blessure or "" }}
      {% if s.statut_med.retour_prevu %}· retour prévu {{ s.statut_med.retour_prevu }}{% endif %}</p>
    <p style="color:var(--muted);font-size:13px">{{ s.statut_med.commentaire or "" }}</p>
  {% else %}<p style="color:var(--muted)">Aucune donnée médicale saisie.</p>{% endif %}
</div>

<div class=section>
  <h2>Production en club</h2>
  <table>
    <tr><th>Matchs suivis</th><th>Minutes cumulées</th><th>Buts</th><th>Passes D.</th></tr>
    <tr><td>{{ s.nb_matchs }}</td><td>{{ s.total_min }}'</td><td>{{ s.buts }}</td><td>{{ s.passes }}</td></tr>
  </table>
</div>

<div class=section>
  <h2>Observations vidéo ({{ s.observations|length }})</h2>
  <table>
    <tr><th>Date</th><th>Contexte</th><th>Adversaire</th><th>Note</th><th>Action</th>
      <th>Commentaire</th><th>Vidéo</th></tr>
    {% for o in s.observations %}
    <tr>
      <td>{{ o.date }}</td>
      <td>{{ o.contexte }}</td>
      <td>{{ o.adversaire }}</td>
      <td><b>{{ o.note_globale }}</b></td>
      <td><span class=code>{{ o.code_action }}</span></td>
      <td>{{ o.commentaire }}</td>
      <td>{% if o.video_link %}<a class=rowlink href="{{ o.video_link }}" target=_blank>▶ {{ o.ts_label }}</a>{% endif %}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class=section>
  <h2>Profil</h2>
  <p>{{ s.joueur.notes_generales }}</p>
</div>

<div class=foot>{{ client }} · Généré automatiquement — données confidentielles.</div>
</div></body></html>"""

INDEX_TMPL = """<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Effectif — {{ client }}</title><style>{{ css }}</style></head><body><div class=wrap>
<div class=top><div class=client>{{ client }}</div>
  <div class=meta>Module Joueurs · Vue effectif<br>{{ ref }}</div></div>
<h1>Effectif suivi</h1>
<div class=sub>{{ rows|length }} joueurs · cliquer un nom pour ouvrir sa fiche</div>
<div class=section>
<table>
  <tr><th>Joueur</th><th>Poste</th><th>Sélection</th><th>Statut</th><th>Club</th>
    <th>Note réc.</th><th>Tps jeu</th><th>Médical</th><th>Alertes</th></tr>
  {% for r in rows %}
  <tr>
    <td><a class=rowlink href="joueur_{{ r.player_id }}.html">{{ r.nom }}</a></td>
    <td>{{ r.poste }}</td><td>{{ r.selection }}</td><td>{{ r.statut }}</td><td>{{ r.club }}</td>
    <td>{{ r.note_moy_recente or "—" }}</td>
    <td><div class=bar><span style="width:{{ r.pct_temps }}%"></span></div>
        <span style="font-size:11px;color:var(--muted)">{{ r.pct_temps }}%</span></td>
    <td><span class="pill {{ r.statut_med|replace('é','e') }}">{{ r.statut_med }}</span></td>
    <td>{% if r.nb_alertes %}<span class="badge" style="background:var(--acc)">{{ r.nb_alertes }}</span>{% else %}—{% endif %}</td>
  </tr>
  {% endfor %}
</table></div>
<div class=foot>{{ client }} · Généré automatiquement — données confidentielles.</div>
</div></body></html>"""


def _env():
    return Environment(loader=BaseLoader(), autoescape=True)


def render_player(player_id, conn=None):
    s = player_stats(player_id, conn)
    if not s:
        return None
    html = _env().from_string(PLAYER_TMPL).render(
        s=s, css=BASE_CSS, client=CLIENT, ref=REF_DATE.isoformat())
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"joueur_{player_id}.html"
    out.write_text(html, encoding="utf-8")
    return out


def render_index(conn=None):
    rows = squad_overview(conn)
    html = _env().from_string(INDEX_TMPL).render(
        rows=rows, css=BASE_CSS, client=CLIENT, ref=REF_DATE.isoformat())
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def main():
    conn = get_connection()
    if len(sys.argv) > 1:
        out = render_player(sys.argv[1], conn)
        print("Fiche :", out)
    else:
        idx = render_index(conn)
        print("Index :", idx)
        for j in list_players(conn):
            print("Fiche :", render_player(j["player_id"], conn))


if __name__ == "__main__":
    main()
