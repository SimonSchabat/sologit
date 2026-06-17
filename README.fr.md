# SoloGit

[🇬🇧 English version](README.md)

Un mini-système de versionnage local écrit en Python, inspiré de Git mais simplifié pour un usage solo. Pas de réseau, pas de serveur — tout est stocké dans un dossier `.sologit/` à la racine du projet.

---

## Installation

Aucune dépendance externe. Python 3.8+ suffit.

```bash
# Rendre les scripts exécutables
chmod +x sologit.py sologit-cli.py
```

Ensuite, choisis l'une des deux méthodes pour y accéder depuis n'importe quel dossier :

**Option 1 — Symlinks dans `/usr/local/bin/` (recommandé)**

```bash
# Remplace /chemin/vers/ par le dossier où se trouvent les fichiers
sudo ln -sf /chemin/vers/sologit.py     /usr/local/bin/sologit
sudo ln -sf /chemin/vers/sologit-cli.py /usr/local/bin/sologit-cli
```

**Option 2 — Alias dans la config du shell**

```bash
# Sur macOS (zsh, shell par défaut depuis macOS Catalina) → édite ~/.zshrc
# Sur Linux ou ancien macOS (bash) → édite ~/.bashrc

alias sologit="python3 /chemin/vers/sologit.py"
alias sologit-cli="python3 /chemin/vers/sologit-cli.py"
```

Puis recharge le shell : `source ~/.zshrc` (ou `source ~/.bashrc`).

Tu peux ensuite taper `sologit` ou `sologit-cli` depuis n'importe quel dossier.

---

## Interface interactive (recommandée)

```bash
sologit-cli
```

Lance une interface en mode texte avec navigation au clavier :
- **↑ ↓** pour naviguer dans les menus
- **Entrée** pour valider
- **q** pour annuler / revenir

Les listes de commits et de fichiers sont également navigables à la flèche.

---

## Démarrage rapide (ligne de commande)

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
sologit init --extension ".tex .bib" --no_extension ".bak"
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

Après chaque commit, les fichiers modifiés sont affichés avec un diff coloré (numéros de ligne, fond rouge/vert pour les suppressions/ajouts).

Si un commit avec le même nom existe déjà, une confirmation est demandée.

---

### `status` — Voir les modifications en cours

```bash
sologit status
```

Affiche les fichiers ajoutés (`+`), modifiés (`~`) et supprimés (`-`) par rapport au dernier commit.

---

### `log` — Afficher l'historique

```bash
sologit log           # tous les commits
sologit log -n 5      # les 5 derniers uniquement
```

Les tags éventuels sont affichés en badges `[v1.0]` à côté du commit.

---

### `diff` — Voir les modifications

```bash
sologit diff                        # diff de tous les fichiers modifiés
sologit diff main.tex               # diff d'un fichier précis
sologit diff main.tex save_1        # comparaison avec un commit spécifique
```

Affichage style Claude Code : numéros de ligne ancien/nouveau, fond coloré pour chaque ligne ajoutée ou supprimée.

---

### `extensions` — Modifier les filtres de fichiers

```bash
sologit extensions                                  # affiche le .sologitignore actuel
sologit extensions --extension ".py .tex .bib"     # redéfinir la liste blanche
sologit extensions --no_extension ".log .tmp .exe" # redéfinir la liste noire
```

Régénère le `.sologitignore` sans toucher à l'historique. Pratique pour changer les types de fichiers suivis après l'init.

---

### `tag` — Marquer un commit

```bash
sologit tag save_1 v1.0       # ajouter un tag
sologit tag                    # lister tous les tags
sologit tag --delete v1.0      # supprimer un tag
```

Les tags apparaissent dans `sologit log` sous forme de badges.

---

### `show` — Détails d'un commit

```bash
sologit show save_1
```

Affiche la liste des fichiers du commit avec leur taille et leur hash.

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

---

### `undo` — Annuler le dernier commit

```bash
sologit undo
sologit undo --force    # sans confirmation
```

Supprime le dernier commit de l'historique et restaure l'espace de travail à l'état précédent.

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

### `fsck` — Vérifier l'intégrité du dépôt

```bash
sologit fsck
```

Vérifie que chaque objet référencé dans l'historique existe et que son hash correspond au contenu. Signale les objets manquants, corrompus ou orphelins.

---

## Le fichier `.sologitignore`

Créé automatiquement à l'`init`, modifiable avec `sologit extensions`. Fonctionne comme `.gitignore` avec support de la négation `!`.

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

Toutes les commandes (`checkout`, `restore`, `diff`, `show`, `rename`, `export`, `tag`…) acceptent :
- le **nom** du commit : `save_1`
- le **préfixe de l'ID** (7 caractères) : `3f46276`

En cas de doublon de nom, le commit le plus récent est utilisé.

---

## Structure interne

```
.sologit/
├── history.json        # historique de tous les commits (JSON)
├── objects/            # contenu des fichiers (content-addressed, sous-dossiers ab/cdef…)
│   └── ab/
│       └── cdef1234…
└── backups/            # sauvegardes automatiques créées avant chaque écrasement
    └── 20260617_143022/
```

Chaque objet est identifié par son hash SHA-1. Un même fichier non modifié n'est stocké qu'une seule fois, quel que soit le nombre de commits qui le référencent.
