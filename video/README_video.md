# Module Vidéo — Analyse automatique (POC)

Transforme une vidéo de match en **données** : détection + suivi des joueurs
et du ballon, classification des équipes, **heatmaps**, et surtout **montage
automatique par joueur** (auto-clipping). Tout tourne **en local**.

> ⚠️ Statut : preuve de concept. La « plomberie » (découpe, heatmap, montage,
> segmentation) est **testée et validée** (`selftest.py`). La qualité de la
> **détection** dépend de ta vidéo et se juge sur ton premier vrai passage.

---

## Ce que ça fait (et ne fait pas)

**Fait, fiable :** suit joueurs + ballon, sépare les 2 équipes par couleur de
maillot, produit une heatmap par joueur, et découpe automatiquement toutes les
séquences où un joueur ciblé est présent → un montage prêt à visionner.

**Ne fait PAS (pour l'instant) :** reconnaître automatiquement passes/tacles/buts.
C'est la partie « recherche » ; l'approche retenue est *l'IA propose, l'humain
valide*. Le suivi et l'auto-clipping sont déjà l'essentiel du gain de temps.

## Prérequis

```bash
pip install -r video/requirements_video.txt   # installe ultralytics + torch
# + ffmpeg installé sur le système (voir le fichier requirements_video.txt)
```

Matériel : ça marche sur **CPU** pour tester un court segment, mais un **GPU**
est fortement recommandé pour traiter un match entier dans un temps raisonnable.

## Récupérer la vidéo en local

Le pipeline travaille sur un **fichier vidéo local** (ex. `match.mp4`) que tu
places où tu veux. Récupère ta vidéo par le moyen de ton choix ; vérifie que tu
as le droit de l'utiliser (droits / CGU de la plateforme source).

## Utilisation (dans le dossier `video/`)

Règle d'abord le segment à traiter dans `config_video.yaml`
(`segment_debut`, `segment_duree`, `frame_stride`). **Commence petit** : 1 à 2
minutes, pas les 90.

```bash
# 1) Découper + préparer le segment (rapide)
python run_video.py prep /chemin/vers/match.mp4

# 2) Détection + suivi + équipes + frame annotée  (le gros du calcul)
python run_video.py track
#    -> ouvre out/preview_ids.png et repère le #ID de TON joueur

# 3) Montage auto + heatmap de ce joueur (ex. #7)
python run_video.py clip 7
```

Ou tout d'un coup : `python run_video.py all /chemin/match.mp4 7`

## Sorties (dossier `video/out/`)

- `preview_ids.png` — une image du match avec chaque joueur numéroté (pour choisir l'ID).
- `tracking.csv` — toutes les positions suivies (frame, id, classe, x, y, équipe…). **C'est la donnée** : elle peut alimenter la même base SQLite que le reste du projet.
- `heatmap_joueur_<id>.png` — zone d'activité du joueur.
- `clips_joueur_<id>/` — chaque séquence découpée.
- `montage_joueur_<id>.mp4` — le montage complet du joueur.

## Réglages utiles (`config_video.yaml`)

- `frame_stride` : 3 = traite 1 image sur 3 (3× plus rapide, suffisant pour heatmap/clip).
- `modele.poids` : `yolo11n.pt` (rapide) → `yolo11s/m.pt` (plus précis, plus lourd).
- `autoclip.padding_*` / `gap_max` : marge autour des séquences et fusion des séquences proches.

## Valider sans vidéo réelle

```bash
python selftest.py
```

Génère une vidéo synthétique + un tracking de vérité terrain et vérifie toute la
chaîne (découpe, heatmap, montage, segmentation). Utile pour confirmer que
l'installation (ffmpeg, opencv) est bonne avant de lancer sur un vrai match.

## Comment ça se branche au reste du projet

`tracking.csv` est la passerelle : un script d'agrégation peut en tirer des
indicateurs (temps de présence, zones, distances si l'homographie est ajoutée)
et les écrire dans `data/db/selection.sqlite` — les fiches joueur et le dashboard
existants les afficheront alors sans modification. Prochaine étape naturelle :
l'**homographie** (calibrer 4 points du terrain) pour convertir les pixels en
mètres et calculer distances/vitesses réelles.
