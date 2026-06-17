#!/usr/bin/env python3
"""Interface interactive pour SoloGit — navigation avec les flèches du clavier."""
import contextlib
import io
import itertools
import os
import sys
import threading
import time
import tty
import termios
from pathlib import Path
from typing import List, Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))
from sologit import *  # noqa: F401,F403  – toutes les classes/fonctions de sologit disponibles ici

# ── Couleurs ──────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BG_SEL = "\033[48;5;236m"  # fond gris foncé pour l'élément sélectionné

W = 54


def clear():
    os.system("clear")


def title(text: str):
    bar = "─" * max(0, W - 6 - len(text))
    print(f"\n  {BOLD}{CYAN}── {text} {bar}{RESET}\n")


def pause():
    print(f"\n  {BG_SEL}{CYAN}{BOLD} ▶  {RESET}{BG_SEL}Continuer{RESET}")
    getch()


def confirm_arrows(message: str) -> bool:
    """Demande Oui/Non avec les flèches. Retourne True si Oui."""
    print(f"  {BOLD}{message}{RESET}\n")
    items = [
        {"label": f"{GREEN}Oui{RESET}", "selectable": True},
        {"label": f"{RED}Non{RESET}",   "selectable": True},
    ]
    choice = arrow_select(items)
    print()
    return choice == 0


def with_spinner(message: str, fn, *args, **kwargs):
    """Lance fn(*args, **kwargs) dans un thread et affiche un spinner pendant ce temps."""
    done          = threading.Event()
    result_holder = [None]
    error_holder  = [None]
    captured      = io.StringIO()

    def target():
        try:
            with contextlib.redirect_stdout(captured):
                result_holder[0] = fn(*args, **kwargs)
        except Exception as e:
            error_holder[0] = e
        finally:
            done.set()

    t = threading.Thread(target=target, daemon=True)
    t.start()

    for frame in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
        if done.is_set():
            break
        sys.stdout.write(f"\r  {CYAN}{frame}{RESET}  {message}")
        sys.stdout.flush()
        time.sleep(0.08)

    t.join()
    sys.stdout.write(f"\r  {GREEN}✓{RESET}  {message}" + " " * 20 + "\n")
    sys.stdout.flush()

    output = captured.getvalue().strip()
    if output:
        print()
        for line in output.split("\n"):
            print(f"  {line}")

    if error_holder[0]:
        raise error_holder[0]
    return result_holder[0]


# ── Lecture clavier raw ───────────────────────────────────────────────────────

def getch() -> bytes:
    """Lit une touche en mode raw (flèches, Entrée, lettres...) sans attendre Entrée."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.buffer.read(1)
        if ch == b"\x1b":
            ch2 = sys.stdin.buffer.read(1)
            if ch2 == b"[":
                ch3 = sys.stdin.buffer.read(1)
                return ch + ch2 + ch3
            return ch + ch2
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


KEY_UP    = b"\x1b[A"
KEY_DOWN  = b"\x1b[B"
KEY_ENTER = (b"\r", b"\n")
KEY_ESC   = b"\x1b"
KEY_CTRL_C = b"\x03"


# ── Sélection avec les flèches ────────────────────────────────────────────────

def arrow_select(items: List[Dict[str, Any]]) -> Optional[int]:
    """
    Affiche une liste navigable avec les flèches et retourne l'index sélectionné.

    Chaque item est un dict :
        {"label": str, "selectable": bool}
    Les items non sélectionnables (séparateurs) sont affichés mais ignorés.
    Retourne None si l'utilisateur annule (q / Échap).
    """
    if not items:
        return None

    # Index initial = premier item sélectionnable
    idx = next((i for i, it in enumerate(items) if it["selectable"]), None)
    if idx is None:
        return None

    n = len(items)

    def render():
        for i, it in enumerate(items):
            if not it["selectable"]:
                print(f"  {DIM}{it['label']}{RESET}")
            elif i == idx:
                print(f"  {BG_SEL}{CYAN}{BOLD} ▶  {RESET}{BG_SEL}{it['label']}{RESET}")
            else:
                print(f"      {it['label']}")

    render()

    while True:
        key = getch()

        if key == KEY_CTRL_C:
            raise KeyboardInterrupt

        if key == KEY_UP:
            new = idx - 1
            while new >= 0 and not items[new]["selectable"]:
                new -= 1
            if new >= 0:
                idx = new

        elif key == KEY_DOWN:
            new = idx + 1
            while new < n and not items[new]["selectable"]:
                new += 1
            if new < n:
                idx = new

        elif key in KEY_ENTER:
            # Efface les lignes du sélecteur avant de retourner
            print(f"\033[{n}A", end="")
            for _ in range(n):
                print("\033[2K\033[1B", end="")
            print(f"\033[{n}A", end="", flush=True)
            return idx

        elif key in (KEY_ESC, b"q", b"Q"):
            print(f"\033[{n}A", end="")
            for _ in range(n):
                print("\033[2K\033[1B", end="")
            print(f"\033[{n}A", end="", flush=True)
            return None

        # Ré-affiche depuis le début de la liste
        print(f"\033[{n}A", end="", flush=True)
        render()


# ── Helpers de sélection ──────────────────────────────────────────────────────

def _commit_label(app: "SoloGit", c: dict) -> str:
    name = app.commit_name(c)
    desc = c.get("description", "")
    date = c["date"][:10]
    n    = len(c["snapshot"])
    s = f"{YELLOW}[{c['id']}]{RESET} {BOLD}{name}{RESET}"
    tags = c.get("tags", [])
    if tags:
        s += "  " + "  ".join(f"{CYAN}[{t}]{RESET}" for t in tags)
    if desc:
        preview = (desc[:26] + "…") if len(desc) > 26 else desc
        s += f"  {DIM}{preview}{RESET}"
    s += f"  {DIM}({date}, {n} f.){RESET}"
    return s


def pick_commit(app: "SoloGit", history: List[dict]) -> Optional[dict]:
    if not history:
        print(f"  {DIM}Aucun commit dans l'historique.{RESET}\n")
        return None

    reversed_history = list(reversed(history))
    items = [{"label": _commit_label(app, c), "selectable": True} for c in reversed_history]
    items.append({"label": f"{DIM}{'─' * 40}{RESET}", "selectable": False})
    items.append({"label": f"{DIM}Annuler{RESET}", "selectable": True})

    print(f"  {DIM}↑↓ pour naviguer, Entrée pour sélectionner, q pour annuler{RESET}\n")
    choice = arrow_select(items)

    if choice is None or choice == len(items) - 1:
        return None
    return reversed_history[choice]


def pick_file(files: List[str], extra_first: Optional[str] = None) -> Optional[str]:
    if not files:
        print(f"  {DIM}Aucun fichier.{RESET}\n")
        return None

    all_items = ([extra_first] if extra_first else []) + files
    items = [{"label": f, "selectable": True} for f in all_items]
    items.append({"label": f"{DIM}{'─' * 40}{RESET}", "selectable": False})
    items.append({"label": f"{DIM}Annuler{RESET}", "selectable": True})

    print(f"  {DIM}↑↓ pour naviguer, Entrée pour sélectionner, q pour annuler{RESET}\n")
    choice = arrow_select(items)

    if choice is None or choice == len(items) - 1:
        return None
    return all_items[choice]


# ── Bandeau principal ─────────────────────────────────────────────────────────

def show_header(app: SoloGit):
    history              = app.get_history()
    added, modified, deleted = app.get_pending_changes()
    n_changes            = len(added) + len(modified) + len(deleted)

    print(f"\n  {'═' * (W - 4)}")
    print(f"  {BOLD}{CYAN}  S O L O G I T{RESET}")
    print(f"  {'═' * (W - 4)}")
    print(f"  {DIM}📁  {app.repo_root}{RESET}")
    if history:
        last = history[-1]
        name = app.commit_name(last)
        tags = last.get("tags", [])
        tag_str = "  " + "  ".join(f"{CYAN}[{t}]{RESET}" for t in tags) if tags else ""
        print(f"  Dernier commit : {YELLOW}{name}{RESET}  {DIM}({last['date'][:10]}){RESET}{tag_str}")
    else:
        print(f"  {DIM}Aucun commit pour le moment.{RESET}")
    if n_changes:
        print(f"  Modifications  : {YELLOW}{n_changes} fichier(s) en attente{RESET}")
    else:
        print(f"  Modifications  : {GREEN}aucune{RESET}")
    print(f"  {'─' * (W - 4)}\n")
    print(f"  {DIM}↑↓ pour naviguer, Entrée pour valider, q pour quitter{RESET}\n")


# ── Actions ───────────────────────────────────────────────────────────────────

def action_status(app: SoloGit):
    title("STATUT")
    app.status()


def action_commit(app: SoloGit):
    title("COMMIT")
    name = input("  Nom du commit (Entrée = date auto) : ").strip() or None
    description = input("  Description   (Entrée = aucune)   : ").strip()
    if name and " " in name and not description:
        description, name = name, None
    app.commit(name, description)


def action_log(app: SoloGit):
    title("HISTORIQUE")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    n_str = input("  Afficher les N derniers (Entrée = tous) : ").strip()
    n = int(n_str) if n_str.isdigit() else None
    print()
    app.log(n=n)


def action_diff(app: SoloGit):
    title("DIFF")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    _, modified, _ = app.get_pending_changes()
    if not modified:
        print(f"  {GREEN}Aucune modification par rapport au dernier commit.{RESET}")
        return
    print("  Choisir le fichier à comparer :\n")
    choice = pick_file(modified, extra_first="[Tous les fichiers]")
    if choice is None:
        return
    print()
    if choice == "[Tous les fichiers]":
        app.diff()
    else:
        app.diff(filepath=str(app.repo_root / choice))


def action_restore(app: SoloGit):
    title("RESTAURER UN FICHIER")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    print("  Choisir le commit source :\n")
    commit = pick_commit(app, history)
    if commit is None:
        return
    print(f"\n  Choisir le fichier à restaurer :\n")
    filepath = pick_file(sorted(commit["snapshot"].keys()))
    if filepath is None:
        return
    name = app.commit_name(commit)
    print(f"  Restaurer {YELLOW}{filepath}{RESET} depuis [{commit['id']}] {name} ?\n")
    if not confirm_arrows("Confirmer la restauration ?"):
        print(f"  {DIM}Annulé.{RESET}")
        return
    app.restore(commit["id"], str(app.repo_root / filepath), force=True)


def action_checkout(app: SoloGit):
    title("CHECKOUT — RETOUR À UN COMMIT COMPLET")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    print("  Choisir le commit :\n")
    commit = pick_commit(app, history)
    if commit is None:
        return

    changed_files, extra_files = app.get_checkout_preview(commit["id"])

    if not changed_files and not extra_files:
        print(f"\n  {GREEN}L'espace de travail correspond déjà à ce commit.{RESET}")
        return

    print()
    if changed_files:
        print(f"  {YELLOW}~ {len(changed_files)} fichier(s) écrasé(s){RESET}")
    if extra_files:
        print(f"  {RED}- {len(extra_files)} fichier(s) supprimé(s){RESET}")
    print()

    if not confirm_arrows(f"Checkout vers [{commit['id']}] ?"):
        print(f"  {DIM}Annulé.{RESET}")
        return

    with_spinner(f"Checkout vers [{commit['id']}]…", app.checkout, commit["id"], force=True)


def action_amend(app: SoloGit):
    title("AMEND — MODIFIER LE DERNIER COMMIT")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    last = history[-1]
    print(f"  Commit actuel : {YELLOW}{app.commit_name(last)}{RESET}  {DIM}{last.get('description', '')}{RESET}\n")
    new_name = input("  Nouveau nom          (Entrée = inchangé) : ").strip() or None
    new_desc = input("  Nouvelle description (Entrée = inchangée) : ").strip() or None
    if new_name is None and new_desc is None:
        print(f"  {DIM}Rien à modifier.{RESET}")
        return
    app.amend(new_name=new_name, new_description=new_desc)


def action_undo(app: SoloGit):
    title("UNDO — ANNULER LE DERNIER COMMIT")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    last = history[-1]
    print(f"  Commit à annuler : {YELLOW}{app.commit_name(last)}{RESET}  {DIM}({last['date'][:10]}){RESET}\n")
    if not confirm_arrows("Confirmer l'annulation ?"):
        print(f"  {DIM}Annulé.{RESET}")
        return
    with_spinner("Annulation en cours…", app.undo, force=True)


def action_rename(app: SoloGit):
    title("RENAME — RENOMMER UN COMMIT")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    print("  Choisir le commit à renommer :\n")
    commit = pick_commit(app, history)
    if commit is None:
        return
    new_name = input("\n  Nouveau nom : ").strip()
    if not new_name:
        return
    app.rename(commit["id"], new_name)


def action_show(app: SoloGit):
    title("SHOW — DÉTAILS D'UN COMMIT")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    print("  Choisir le commit :\n")
    commit = pick_commit(app, history)
    if commit is None:
        return
    print()
    app.show(commit["id"])


def action_export(app: SoloGit):
    title("EXPORT — COPIER UN COMMIT VERS UN DOSSIER")
    history = app.get_history()
    if not history:
        print(f"  {DIM}Aucun commit.{RESET}")
        return
    print("  Choisir le commit à exporter :\n")
    commit = pick_commit(app, history)
    if commit is None:
        return
    dest = input("\n  Dossier de destination : ").strip()
    if not dest:
        return
    app.export(commit["id"], dest)


def action_extensions(app: SoloGit):
    title("EXTENSIONS — FILTRES DE FICHIERS")

    if app.ignore_file.exists():
        print(f"  {DIM}.sologitignore actuel :{RESET}\n")
        for line in app.ignore_file.read_text().splitlines():
            if not line or line.startswith("#"):
                print(f"  {DIM}{line}{RESET}")
            elif line.startswith("!"):
                print(f"  {GREEN}{line}{RESET}")
            else:
                print(f"  {RED}{line}{RESET}")
        print()

    items = [
        {"label": f"Extensions à {GREEN}suivre{RESET}   — liste blanche (ex: .py .tex .bib)", "selectable": True},
        {"label": f"Extensions à {RED}ignorer{RESET}  — liste noire  (ex: .log .tmp .exe)", "selectable": True},
        {"label": f"Réinitialiser  — supprimer tous les filtres",                             "selectable": True},
    ]
    choice = arrow_select(items)
    if choice is None:
        return
    print()

    if choice == 0:
        raw = input("  Extensions à suivre (espace entre chaque, ex: .py .tex) : ").strip()
        app.set_extensions(extensions=parse_extensions(raw) if raw else None)
    elif choice == 1:
        raw = input("  Extensions à ignorer (espace entre chaque, ex: .log .tmp) : ").strip()
        app.set_extensions(no_extensions=parse_extensions(raw) if raw else None)
    elif choice == 2:
        app.set_extensions()


def action_tag(app: SoloGit):
    title("TAG — MARQUER UN COMMIT")
    items = [
        {"label": "Ajouter un tag à un commit", "selectable": True},
        {"label": "Supprimer un tag",            "selectable": True},
        {"label": "Lister tous les tags",        "selectable": True},
    ]
    print("  Que veux-tu faire ?\n")
    choice = arrow_select(items)
    if choice is None:
        return
    print()

    if choice == 2:  # Lister
        app.tag(list_tags=True)

    elif choice == 0:  # Ajouter
        history = app.get_history()
        if not history:
            print(f"  {DIM}Aucun commit.{RESET}")
            return
        print("  Choisir le commit à tagger :\n")
        commit = pick_commit(app, history)
        if commit is None:
            return
        tag_name = input("\n  Nom du tag (ex: v1.0, release) : ").strip()
        if not tag_name:
            return
        app.tag(identifier=commit["id"], tag_name=tag_name)

    elif choice == 1:  # Supprimer
        history  = app.get_history()
        all_tags = sorted({t for c in history for t in c.get("tags", [])})
        if not all_tags:
            print(f"  {DIM}Aucun tag défini.{RESET}")
            return
        print("  Choisir le tag à supprimer :\n")
        tag_items = [{"label": t, "selectable": True} for t in all_tags]
        tag_items.append({"label": f"{DIM}{'─' * 30}{RESET}", "selectable": False})
        tag_items.append({"label": f"{DIM}Annuler{RESET}",    "selectable": True})
        tag_choice = arrow_select(tag_items)
        if tag_choice is None or tag_choice == len(tag_items) - 1:
            return
        print()
        app.tag(tag_name=all_tags[tag_choice], delete=True)


def action_fsck(app: SoloGit):
    title("FSCK — VÉRIFICATION D'INTÉGRITÉ")
    app.fsck()


def action_stats(app: SoloGit):
    title("STATS — ESPACE DISQUE")
    app.stats()


# ── Menu principal ────────────────────────────────────────────────────────────

MENU = [
    ("Statut",   "voir les fichiers modifiés",        action_status),
    ("Commit",     "sauvegarder l'état actuel",          action_commit),
    ("Extensions", "modifier les fichiers suivis",      action_extensions),
    ("Log",        "historique des commits",            action_log),
    ("Diff",     "comparer les modifications",         action_diff),
    ("Restore",  "restaurer un seul fichier",          action_restore),
    ("Checkout", "revenir à un commit complet",        action_checkout),
    None,
    ("Tag",      "marquer un commit (v1.0, release…)", action_tag),
    ("Amend",    "modifier le dernier commit",         action_amend),
    ("Undo",     "annuler le dernier commit",          action_undo),
    ("Rename",   "renommer un commit",                 action_rename),
    ("Show",     "détails et fichiers d'un commit",    action_show),
    ("Export",   "copier un commit vers un dossier",   action_export),
    ("Stats",    "espace disque utilisé",              action_stats),
    None,
    ("Fsck",     "vérifier l'intégrité du dépôt",     action_fsck),
    None,
    ("Quitter",  "",                                   None),
]


def build_menu_items() -> List[Dict[str, Any]]:
    items = []
    for entry in MENU:
        if entry is None:
            items.append({"label": f"{DIM}{'·' * (W - 6)}{RESET}", "selectable": False})
        else:
            cmd, desc, fn = entry
            label = f"{BOLD}{cmd:<10}{RESET} {DIM}{desc}{RESET}" if desc else f"{BOLD}{cmd}{RESET}"
            items.append({"label": label, "selectable": True, "fn": fn})
    return items


def run_main_menu(app: SoloGit) -> bool:
    """Affiche le menu principal, exécute l'action choisie. Retourne False pour quitter."""
    clear()
    show_header(app)

    items = build_menu_items()
    choice = arrow_select(items)

    if choice is None:
        return False

    selected = items[choice]
    fn = selected.get("fn")

    if fn is None:  # "Quitter"
        return False

    clear()
    try:
        fn(app)
    except SoloGitError as e:
        print(f"\n  {RED}Erreur : {e}{RESET}")
    except KeyboardInterrupt:
        pass

    pause()
    return True


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main():
    repo_root = find_repo_root(Path.cwd())

    if repo_root is None:
        clear()
        print(f"\n  {YELLOW}Aucun dépôt SoloGit trouvé ici ou dans les dossiers parents.{RESET}")
        choice = input("  Initialiser un dépôt dans ce dossier ? [o/N] : ").strip().lower()
        if choice in ("o", "oui", "y", "yes"):
            app = SoloGit(Path.cwd())
            app.init()
            repo_root = Path.cwd()
        else:
            print(f"\n  {DIM}Lance sologit-cli depuis un dossier avec un dépôt sologit.{RESET}\n")
            sys.exit(0)

    app = SoloGit(repo_root)

    try:
        while run_main_menu(app):
            pass
    except KeyboardInterrupt:
        pass

    clear()
    print(f"\n  {DIM}À bientôt !{RESET}\n")


if __name__ == "__main__":
    main()
