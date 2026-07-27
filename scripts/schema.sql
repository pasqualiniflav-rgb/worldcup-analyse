-- ============================================================
--  SCHÉMA DE LA BASE (SQLite) — un seul fichier, zéro serveur.
--  Le module Joueurs est central. Les tables médical / temps de
--  jeu / adversaire sont posées dès maintenant pour être étendues.
-- ============================================================

-- Réinitialisation propre (la source de vérité reste l'Excel) -----------
DROP TABLE IF EXISTS observations;
DROP TABLE IF EXISTS dispo_medicale;
DROP TABLE IF EXISTS temps_jeu;
DROP TABLE IF EXISTS adversaires;
DROP TABLE IF EXISTS joueurs;

-- Fiche d'identité des joueurs ------------------------------------------
CREATE TABLE IF NOT EXISTS joueurs (
    player_id       TEXT PRIMARY KEY,      -- identifiant stable (ex. JOU001)
    nom             TEXT NOT NULL,
    prenom          TEXT NOT NULL,
    date_naissance  TEXT,                  -- AAAA-MM-JJ
    poste           TEXT,                  -- GB, DC, MC...
    pied            TEXT,                  -- Droit / Gauche / Ambidextre
    taille_cm       INTEGER,
    selection       TEXT,                  -- A, Espoirs U21, U19, U17
    statut          TEXT,                  -- Cadre / Rotation / À suivre / Vivier / Écarté
    club            TEXT,
    pays_club       TEXT,
    notes_generales TEXT
);

-- Observations vidéo / match (le cœur du scouting) ----------------------
-- Chaque ligne = un joueur observé sur un match, avec note et lien vidéo
-- horodaté (timestamp en secondes) qui rouvre la vidéo au bon moment.
CREATE TABLE IF NOT EXISTS observations (
    obs_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL,
    date            TEXT,                  -- AAAA-MM-JJ
    contexte        TEXT,                  -- 'Sélection' ou 'Club'
    competition     TEXT,
    adversaire      TEXT,
    minutes         INTEGER,               -- minutes observées / jouées
    note_globale    REAL,                  -- note sur l'échelle configurée
    video_url       TEXT,                  -- lien YouTube / fichier
    video_ts        INTEGER,              -- horodatage en secondes
    code_action     TEXT,                  -- ex. 'But', 'Passe D', 'Duel gagné'
    commentaire     TEXT,
    observateur     TEXT,
    FOREIGN KEY (player_id) REFERENCES joueurs(player_id)
);

-- Module MÉDICAL / DISPONIBILITÉ ----------------------------------------
CREATE TABLE IF NOT EXISTS dispo_medicale (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL,
    date            TEXT,
    statut          TEXT,                  -- Apte / Blessé / Reprise / Incertain
    type_blessure   TEXT,
    retour_prevu    TEXT,                  -- AAAA-MM-JJ estimé
    commentaire     TEXT,
    FOREIGN KEY (player_id) REFERENCES joueurs(player_id)
);

-- TEMPS DE JEU RÉEL en club (crucial avant une convocation) --------------
CREATE TABLE IF NOT EXISTS temps_jeu (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL,
    date            TEXT,
    club            TEXT,
    competition     TEXT,
    minutes         INTEGER,
    titulaire       INTEGER,               -- 1 = titulaire, 0 = remplaçant/entré
    buts            INTEGER DEFAULT 0,
    passes_d        INTEGER DEFAULT 0,
    FOREIGN KEY (player_id) REFERENCES joueurs(player_id)
);

-- Module ADVERSAIRE (préparation du prochain match international) --------
CREATE TABLE IF NOT EXISTS adversaires (
    adversaire_id   TEXT PRIMARY KEY,
    pays            TEXT,
    systeme         TEXT,                  -- ex. 4-3-3, 3-5-2
    forces          TEXT,
    faiblesses      TEXT,
    joueurs_cles    TEXT,
    video_url       TEXT,
    commentaire     TEXT
);
