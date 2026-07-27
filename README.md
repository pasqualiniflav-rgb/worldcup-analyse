# Analyse Sélection — Module Joueurs (MVP)

Solution **locale et légère** d'analyse pour une sélection nationale de football.
Chaîne complète : **Excel de saisie → base SQLite → rapports joueur + dashboard**.
Aucun serveur, aucune donnée dans le cloud — tout reste sur le poste du staff.

> Ce dépôt est un **template produit** : pour déployer chez un autre client, on ne
> modifie que `config/client.yaml`. Le moteur ne change pas.

---

## 1. Philosophie

Une sélection nationale ne voit ses joueurs que quelques jours par rassemblement,
pendant qu'ils jouent toute l'année dans des clubs différents. Le cœur du besoin
n'est donc pas l'entraînement quotidien mais **l'observation à distance et le suivi
dans le temps** de joueurs éparpillés, à partir surtout de **vidéo** et de **notes
saisies à la main**. Cet outil est donc avant tout une *base de connaissance joueurs
+ un moteur de scouting vidéo*.

## 2. Architecture (4 couches)

```
   [ Excel de saisie ]        data/input/saisie_selection.xlsx     ← interface du staff
            │  ingest.py
            ▼
   [ Base SQLite ]            data/db/selection.sqlite             ← source de vérité (1 fichier)
            │  analytics.py   (indicateurs + alertes)
            ▼
   [ Restitution ]           reports/*.html   +   app/dashboard.py ← fiches joueur & dashboard
```

## 3. Installation

```bash
pip install -r requirements.txt
```

## 4. Utilisation

Générer la base + tous les rapports en une commande :

```bash
python run.py
```

Puis ouvrir `reports/index.html` dans un navigateur → cliquer un joueur pour sa fiche.

Étapes séparées si besoin :

```bash
python scripts/ingest.py            # Excel -> base
python scripts/report.py            # tous les rapports
python scripts/report.py JOU002     # une fiche précise
```

Dashboard interactif (optionnel) :

```bash
streamlit run app/dashboard.py
```

## 5. Saisie des données (le staff)

Le staff ne travaille **que** dans un classeur Excel. Deux fichiers :

- `data/templates/modele_saisie.xlsx` — **gabarit vierge** à dupliquer.
- `data/input/saisie_selection.xlsx` — exemple **pré-rempli** (10 joueurs fictifs).

Onglets : **Joueurs**, **Observations** (vidéo horodatée), **Medical**,
**TempsJeu**, **Adversaires**. Ligne 3 = en-têtes, ligne 4 = aide, saisie à partir
de la ligne 5. Les listes déroulantes (poste, sélection, statut…) viennent de la config.

**Codage vidéo** : dans l'onglet *Observations*, renseigner `video_url` (lien YouTube)
et `video_ts` (horodatage **en secondes**). Le rapport génère un lien ▶ qui rouvre la
vidéo exactement au bon moment — l'équivalent gratuit d'un Sportscode/Hudl basique.

## 6. Ce que calcule l'outil

Par joueur : note moyenne (globale et récente), nombre d'observations, temps de jeu
réel en club (%), taux de titularisation, buts/passes, dernier match joué, statut
médical courant. Et surtout des **alertes automatiques** utiles avant une convocation :
blessure/incertitude médicale, trop longtemps sans jouer, forme en baisse, temps de
jeu club insuffisant. Seuils réglables dans `config/client.yaml`.

## 7. Structure du projet

```
analyse-selection/
├── config/client.yaml         # LE seul fichier à changer par client
├── data/
│   ├── templates/             # gabarit Excel vierge
│   ├── input/                 # classeur de saisie (rempli par le staff)
│   └── db/                    # base SQLite (générée)
├── scripts/
│   ├── config.py              # chemins + config
│   ├── schema.sql / db.py     # schéma + accès base
│   ├── make_templates.py      # (re)génère les Excel + données démo
│   ├── ingest.py              # Excel  -> base
│   ├── analytics.py           # indicateurs + alertes (logique métier)
│   └── report.py              # base   -> rapports HTML
├── app/dashboard.py           # mini-dashboard Streamlit (optionnel)
├── reports/                   # sorties HTML (générées)
└── run.py                     # pipeline complet
```

## 8. Feuille de route (prochains modules)

Le schéma de base pose déjà **Médical/disponibilité** et **Adversaire**. Extensions
naturelles, dans l'ordre suggéré :

1. **Module Jeunes** — suivi longitudinal du vivier U17/U19/U21 (progression saison/saison).
2. **Module Adversaire** — fiche de préparation match international (déjà amorcé).
3. **Module Clubs** — cartographie des clubs et du temps de jeu par contexte.
4. **Export PDF** natif (weasyprint) et **comparateur** de joueurs.
5. **Entraînements** — module léger activé uniquement pendant les rassemblements.

## 9. Argument de déploiement client

Données 100 % locales (rien ne sort du poste) → argument de **confidentialité** fort
pour une fédération. Un client = un dossier + un `client.yaml`. Sauvegarde = copier le
fichier `.sqlite`. Zéro dépendance à un fournisseur externe.
