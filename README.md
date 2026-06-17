# SoloGit

[🇫🇷 Version française](README.fr.md)

A lightweight local versioning tool written in Python, inspired by Git but simplified for solo use. No network, no server — everything is stored in a `.sologit/` folder at the root of your project.

---

## Installation

No external dependencies. Python 3.8+ is all you need.

```bash
# Make the scripts executable
chmod +x sologit.py sologit-cli.py
```

Then choose one of the two methods below to make them accessible from anywhere:

**Option 1 — Symlinks in `/usr/local/bin/` (recommended)**

```bash
# Replace /path/to/ with the folder where the files are stored
sudo ln -sf /path/to/sologit.py     /usr/local/bin/sologit
sudo ln -sf /path/to/sologit-cli.py /usr/local/bin/sologit-cli
```

**Option 2 — Aliases in your shell config**

```bash
# On macOS (zsh, default since macOS Catalina) → edit ~/.zshrc
# On Linux or older macOS (bash) → edit ~/.bashrc

alias sologit="python3 /path/to/sologit.py"
alias sologit-cli="python3 /path/to/sologit-cli.py"
```

Then reload your shell: `source ~/.zshrc` (or `source ~/.bashrc`).

You can then run `sologit` or `sologit-cli` from any directory.

---

## Interactive interface (recommended)

```bash
sologit-cli
```

Launches a text-based interface with keyboard navigation:
- **↑ ↓** to navigate menus
- **Enter** to confirm
- **q** to cancel / go back

Commit lists and file lists are also arrow-navigable.

---

## Quick start (command line)

```bash
sologit init                        # initialize the repo in the current folder
sologit commit save_1               # save the current state
sologit log                         # show history
sologit checkout save_1             # go back to the state of save_1
```

---

## Commands

### `init` — Initialize a repository

```bash
sologit init
sologit init --extension ".tex .bib .py"       # track only these extensions
sologit init --no_extension ".log .tmp"         # ignore these extensions
sologit init --extension ".tex .bib" --no_extension ".bak"
```

Creates the `.sologit/` folder and a `.sologitignore` file in the current directory.

---

### `commit` — Save the current state

```bash
sologit commit                                  # name = current date/time
sologit commit save_1                           # short name
sologit commit save_1 "commit description"     # name + description
sologit commit "description with spaces"        # description only, name = date
```

After each commit, modified files are shown with a colored diff (line numbers, red/green background for removals/additions).

If a commit with the same name already exists, a confirmation is asked.

---

### `status` — See current changes

```bash
sologit status
```

Shows added (`+`), modified (`~`) and deleted (`-`) files since the last commit.

---

### `log` — Show history

```bash
sologit log           # all commits
sologit log -n 5      # last 5 only
```

Tags are displayed as `[v1.0]` badges next to the commit.

---

### `diff` — View changes

```bash
sologit diff                        # diff all modified files
sologit diff main.tex               # diff a specific file
sologit diff main.tex save_1        # compare against a specific commit
```

Claude Code-style display: old/new line numbers, colored background for each added or removed line.

---

### `extensions` — Modify file filters

```bash
sologit extensions                                  # show current .sologitignore
sologit extensions --extension ".py .tex .bib"     # redefine the whitelist
sologit extensions --no_extension ".log .tmp .exe" # redefine the blacklist
```

Regenerates `.sologitignore` without touching the history. Useful for changing tracked file types after init.

---

### `tag` — Mark a commit

```bash
sologit tag save_1 v1.0       # add a tag
sologit tag                    # list all tags
sologit tag --delete v1.0      # remove a tag
```

Tags appear in `sologit log` as badges.

---

### `show` — Commit details

```bash
sologit show save_1
```

Shows the list of files in the commit with their size and hash.

---

### `restore` — Restore a file

```bash
sologit restore save_1 main.tex           # restore a single file
sologit restore save_1 main.tex --force   # without confirmation
```

A safety backup of the current version is automatically created in `.sologit/backups/`.

---

### `checkout` — Go back to a full commit

```bash
sologit checkout save_1           # restore all files from the commit
sologit checkout save_1 --force   # without confirmation
```

Files absent from that commit are deleted from disk. A backup is created before any modification.

---

### `amend` — Edit the last commit

```bash
sologit amend --name new_name
sologit amend --description "new description"
sologit amend --name v2 --description "fixed version"
```

---

### `undo` — Cancel the last commit

```bash
sologit undo
sologit undo --force    # without confirmation
```

Removes the last commit from history and restores the working directory to the previous state.

---

### `rename` — Rename a commit

```bash
sologit rename save_1 v1_stable
```

---

### `export` — Export a commit to a folder

```bash
sologit export save_1 ./release
sologit export save_1 ~/Desktop/final_version
```

Copies all files from the commit to the destination folder, preserving the directory structure.

---

### `stats` — Repository statistics

```bash
sologit stats
```

Shows the number of commits, disk space used, and recoverable orphan objects.

---

### `fsck` — Check repository integrity

```bash
sologit fsck
```

Verifies that every object referenced in history exists and that its hash matches its content. Reports missing, corrupted, or orphan objects.

---

## The `.sologitignore` file

Automatically created on `init`, editable with `sologit extensions`. Works like `.gitignore` with negation `!` support.

```
# Ignore extensions
*.log
*.tmp
build/

# Whitelist (track only certain types)
*
!*/
!*.tex
!*.bib
!*.png
```

The folders `.sologit`, `.git`, `__pycache__`, `venv` and `env` are always ignored automatically.

---

## Identifying a commit

All commands (`checkout`, `restore`, `diff`, `show`, `rename`, `export`, `tag`…) accept:
- the commit **name**: `save_1`
- the **ID prefix** (7 characters): `3f46276`

In case of duplicate names, the most recent commit is used.

---

## Internal structure

```
.sologit/
├── history.json        # full commit history (JSON)
├── objects/            # file contents (content-addressed, sharded ab/cdef…)
│   └── ab/
│       └── cdef1234…
└── backups/            # automatic backups created before any overwrite
    └── 20260617_143022/
```

Each object is identified by its SHA-1 hash. An unchanged file is stored only once, regardless of how many commits reference it.
