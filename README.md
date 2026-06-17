# SoloGit

Un mini-système de versionnage local écrit en Python, inspiré de Git mais simplifié pour un usage solo. Pas de réseau, pas de serveur — tout est stocké dans un dossier `.sologit/` à la racine du projet.

---

## Installation

Aucune dépendance externe. Python 3.8+ suffit.

```bash
# Rendre le script exécutable (optionnel)
chmod +x sologit.py

# Créer un alias global pour l'utiliser partout (à ajouter dans ~/.zshrc ou ~/.bashrc)
alias sologit="python3 ~/Desktop/sologit.py"
```

---

## Démarrage rapide

```bash
sologit init                        # initialise le dépôt dans le dossier courant
sologit commit save_1               # sauvegarde l'état actuel
sologit log                         # affiche l'historique
sologit checkout save_1             # revient à l'état de save_1
```

---

## Commandes

### `init` — Initialiser un dépôt

```bash
sologit init
sologit init --extension ".tex .bib .py"       # suivre uniquement ces extensions
sologit init --no_extension ".log .tmp"         # ignorer ces extensions
sologit init --extension ".tex .bib" --no_extension ".bak"  # les deux combinés
```

Crée le dossier `.sologit/` et un fichier `.sologitignore` dans le répertoire courant.

---

### `commit` — Sauvegarder l'état actuel

```bash
sologit commit                                  # nom = date automatique
sologit commit save_1                           # nom court
sologit commit save_1 "descriptif du commit"   # nom + description
sologit commit "descriptif avec espaces"        # description seule, nom = date auto
```

Si un commit avec le même nom existe déjà, une confirmation est demandée.

---

### `status` — Voir les modifications en cours

```bash
sologit status
```

Affiche les fichiers ajoutés (`+`), modifiés (`~`) et supprimés (`-`) par rapport au dernier commit, sans rien enregistrer.

---

### `log` — Afficher l'historique

```bash
sologit log           # tous les commits
sologit log -n 5      # les 5 derniers uniquement
```

---

### `diff` — Voir les modifications

```bash
sologit diff                        # diff de tous les fichiers modifiés
sologit diff main.tex               # diff d'un fichier précis
sologit diff main.tex save_1        # comparaison avec un commit spécifique
```

---

### `show` — Détails d'un commit

```bash
sologit show save_1
```

Affiche la liste des fichiers du commit avec leur taille et leur hash. Ne touche pas à l'espace de travail.

---

### `restore` — Restaurer un fichier

```bash
sologit restore save_1 main.tex           # restaure un seul fichier
sologit restore save_1 main.tex --force   # sans confirmation
```

Une sauvegarde de sécurité de la version actuelle est créée automatiquement dans `.sologit/backups/`.

---

### `checkout` — Revenir à un commit complet

```bash
sologit checkout save_1           # restaure tous les fichiers du commit
sologit checkout save_1 --force   # sans confirmation
```

Les fichiers absents de ce commit sont supprimés du disque. Une sauvegarde est créée avant toute modification.

---

### `amend` — Modifier le dernier commit

```bash
sologit amend --name nouveau_nom
sologit amend --description "nouvelle description"
sologit amend --name v2 --description "version corrigée"
```

Ne crée pas de nouveau commit, modifie uniquement le nom et/ou la description du dernier.

---

### `undo` — Annuler le dernier commit

```bash
sologit undo
sologit undo --force    # sans confirmation
```

Supprime le dernier commit de l'historique et restaure l'espace de travail à l'état du commit précédent. Une sauvegarde est créée avant.

---

### `rename` — Renommer un commit

```bash
sologit rename save_1 v1_stable
```

---

### `export` — Exporter un commit vers un dossier

```bash
sologit export save_1 ./livraison
sologit export save_1 ~/Desktop/version_finale
```

Copie tous les fichiers du commit dans le dossier de destination, en préservant l'arborescence.

---

### `stats` — Statistiques du dépôt

```bash
sologit stats
```

Affiche le nombre de commits, l'espace disque utilisé, et les objets orphelins récupérables.

---

## Le fichier `.sologitignore`

Créé automatiquement à l'`init`. Fonctionne comme `.gitignore` avec support de la négation `!`.

```
# Ignorer des extensions
*.log
*.tmp
build/

# Liste blanche (ne garder que certains types)
*
!*/
!*.tex
!*.bib
!*.png
```

Les dossiers `.sologit`, `.git`, `__pycache__`, `venv` et `env` sont toujours ignorés automatiquement.

---

## Identifier un commit

Toutes les commandes (`checkout`, `restore`, `diff`, `show`, `rename`, `export`) acceptent :
- le **nom** du commit : `save_1`
- le **préfixe de l'ID** (7 caractères) : `3f46276`

En cas de doublon de nom, le commit le plus récent est utilisé.

---

## Structure interne

```
.sologit/
├── history.json        # historique de tous les commits
├── objects/            # contenu des fichiers (content-addressed, sous-dossiers ab/cdef…)
│   └── ab/
│       └── cdef1234…
└── backups/            # sauvegardes automatiques créées avant chaque écrasement
    └── 20260617_143022/
```
