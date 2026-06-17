#!/usr/bin/env python3
import re
import sys
import shutil
import hashlib
import json
import fnmatch
import difflib
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Couleurs ANSI
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

_BG_RED   = "\033[48;5;52m"   # fond rouge foncé (diff)
_BG_GREEN = "\033[48;5;22m"   # fond vert foncé (diff)

REPO_DIR_NAME  = ".sologit"
IGNORE_FILE_NAME = ".sologitignore"

DEFAULT_IGNORE_CONTENT = """# Fichiers et dossiers à ignorer par SoloGit
# Une ligne par motif (style .gitignore simplifié).
# Les lignes vides ou commençant par # sont ignorées.
#
# Exemples :
#   *.log
#   build/
#   secrets.txt
#
# Le préfixe "!" réautorise ce qu'un motif précédent excluait
# (utile pour une liste blanche : ignorer tout, sauf certains types) :
#   *
#   !*/
#   !*.tex
#   !*.bib
"""


class SoloGitError(Exception):
    """Erreur métier attendue (affichée proprement, sans traceback)."""


class SoloGit:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.base_dir  = self.repo_root / REPO_DIR_NAME
        self.objects_dir  = self.base_dir / "objects"
        self.history_file = self.base_dir / "history.json"
        self.ignore_file  = self.repo_root / IGNORE_FILE_NAME

        self.ignore_dir_names = {REPO_DIR_NAME, "__pycache__", ".git", "venv", "env"}

        self._ignore_patterns: Optional[List[str]] = None
        self._backup_session_dir: Optional[Path]   = None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init(self, extensions: Optional[List[str]] = None,
             no_extensions: Optional[List[str]] = None):
        if self.base_dir.exists():
            print(f"Le dépôt {self.base_dir} est déjà initialisé.")
            return

        self.objects_dir.mkdir(parents=True)
        self.history_file.write_text(json.dumps([]))
        self.ignore_file.write_text(self._build_sologitignore(extensions, no_extensions))

        print("Dépôt local SoloGit initialisé avec succès.")
        print(f"  - historique  : {self.history_file}")
        print(f"  - exclusions  : {self.ignore_file}")
        if extensions:
            print(f"  - suivi       : {', '.join(extensions)} uniquement")
        if no_extensions:
            print(f"  - ignorés     : {', '.join(no_extensions)}")

    @staticmethod
    def _build_sologitignore(extensions, no_extensions) -> str:
        if not extensions and not no_extensions:
            return DEFAULT_IGNORE_CONTENT
        lines = ["# Fichier généré automatiquement par sologit init", ""]
        if extensions:
            lines += ["# Liste blanche : tout est ignoré sauf les extensions ci-dessous", "*", "!*/"]
            for ext in extensions:
                lines.append(f"!*{ext}")
        if no_extensions:
            if extensions:
                lines.append("")
            lines.append("# Extensions explicitement ignorées")
            for ext in no_extensions:
                lines.append(f"*{ext}")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utilitaires internes
    # ------------------------------------------------------------------

    def _hash_file(self, filepath: Path) -> str:
        hasher = hashlib.sha1()
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _load_ignore_patterns(self) -> List[str]:
        if self._ignore_patterns is None:
            patterns = []
            if self.ignore_file.exists():
                for line in self.ignore_file.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    patterns.append(line)
            self._ignore_patterns = patterns
        return self._ignore_patterns

    def _segment_ignored(self, seg_path: str, seg_name: str, is_dir: bool) -> bool:
        ignored = False
        for raw_pattern in self._load_ignore_patterns():
            pattern = raw_pattern
            negate = pattern.startswith("!")
            if negate:
                pattern = pattern[1:]
            dir_only = pattern.endswith("/")
            core = pattern.rstrip("/")
            if not core:
                continue
            if dir_only and not is_dir:
                continue
            if fnmatch.fnmatch(seg_path, core) or fnmatch.fnmatch(seg_name, core):
                ignored = not negate
        return ignored

    def _is_ignored(self, rel_path: Path) -> bool:
        parts = rel_path.parts
        if any(part in self.ignore_dir_names for part in parts):
            return True
        acc: List[str] = []
        for part in parts[:-1]:
            acc.append(part)
            if self._segment_ignored("/".join(acc), part, is_dir=True):
                return True
        return self._segment_ignored(rel_path.as_posix(), rel_path.name, is_dir=False)

    def _object_path(self, file_hash: str) -> Path:
        return self.objects_dir / file_hash[:2] / file_hash[2:]

    def _resolve_object_path(self, file_hash: str) -> Optional[Path]:
        sharded = self._object_path(file_hash)
        if sharded.exists():
            return sharded
        legacy = self.objects_dir / file_hash
        if legacy.exists():
            return legacy
        return None

    def _hash_from_object_path(self, obj_path: Path) -> str:
        """Reconstruit le hash SHA-1 depuis le chemin d'un objet stocké."""
        if obj_path.parent == self.objects_dir:
            return obj_path.name                    # format plat (legacy)
        return obj_path.parent.name + obj_path.name  # format en sous-dossiers

    def _scan_working_directory(self, save_objects: bool = False) -> Tuple[Dict[str, str], int]:
        current_state: Dict[str, str] = {}
        files_saved = 0
        for filepath in self.repo_root.rglob("*"):
            if filepath.is_dir():
                continue
            rel_path = filepath.relative_to(self.repo_root)
            if self._is_ignored(rel_path):
                continue
            try:
                file_hash = self._hash_file(filepath)
            except Exception as e:
                print(f"Avertissement : impossible de lire {rel_path} ({e})")
                continue
            rel_str = rel_path.as_posix()
            current_state[rel_str] = file_hash
            if save_objects and self._resolve_object_path(file_hash) is None:
                obj = self._object_path(file_hash)
                obj.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(filepath, obj)
                files_saved += 1
        return current_state, files_saved

    @staticmethod
    def _diff_snapshots(old: Dict[str, str], new: Dict[str, str]) -> Tuple[List[str], List[str], List[str]]:
        added    = sorted(set(new) - set(old))
        deleted  = sorted(set(old) - set(new))
        modified = sorted(k for k in (set(new) & set(old)) if new[k] != old[k])
        return added, modified, deleted

    @staticmethod
    def _print_change_summary(added, modified, deleted):
        if not (added or modified or deleted):
            print("  (aucun changement de fichier)")
            return
        for f in added:    print(f"  {GREEN}+ {f}{RESET}")
        for f in modified: print(f"  {YELLOW}~ {f}{RESET}")
        for f in deleted:  print(f"  {RED}- {f}{RESET}")

    @staticmethod
    def _format_size(n_bytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n_bytes < 1024:
                return f"{n_bytes} {unit}" if unit == "B" else f"{n_bytes:.1f} {unit}"
            n_bytes /= 1024
        return f"{n_bytes:.1f} TB"

    def _load_history(self) -> List[dict]:
        return json.loads(self.history_file.read_text())

    def _commit_name(self, commit: dict) -> str:
        return commit.get("name", commit.get("message", ""))

    def _find_commit(self, history: List[dict], identifier: str) -> Optional[dict]:
        by_id = next((c for c in history if c["id"].startswith(identifier)), None)
        if by_id:
            return by_id
        matches = [c for c in history if self._commit_name(c) == identifier]
        return matches[-1] if matches else None

    def _resolve_target(self, filepath: str) -> Tuple[Path, str]:
        abs_path = Path(filepath).resolve()
        try:
            rel_path = abs_path.relative_to(self.repo_root)
        except ValueError:
            raise SoloGitError(f"'{filepath}' est en dehors du dépôt ({self.repo_root}).")
        return abs_path, rel_path.as_posix()

    def _ensure_backup_session(self) -> Path:
        if self._backup_session_dir is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._backup_session_dir = self.base_dir / "backups" / ts
            self._backup_session_dir.mkdir(parents=True, exist_ok=True)
        return self._backup_session_dir

    def _backup_file(self, abs_path: Path, rel_str: str):
        session = self._ensure_backup_session()
        dest = session / rel_str
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_path, dest)

    @staticmethod
    def _confirm(message: str) -> bool:
        answer = input(f"{message} [o/N] ").strip().lower()
        return answer in ("o", "oui", "y", "yes")

    def _render_diff(self, old_path: Path, new_path: Optional[Path], rel_str: str) -> bool:
        """Affiche le diff coloré entre deux fichiers (style Claude Code). Retourne True si diff non vide."""
        try:
            old_lines = old_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            new_lines = new_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) \
                        if new_path and new_path.exists() else []
        except Exception:
            print(f"  '{rel_str}' : diff impossible (fichier binaire).")
            return False

        raw_diff = list(difflib.unified_diff(old_lines, new_lines, n=3))
        if not raw_diff:
            return False

        deleted_note = f"  {RED}(supprimé){RESET}" if not (new_path and new_path.exists()) else ""
        print(f"\n  {BOLD}{CYAN}{rel_str}{RESET}{deleted_note}")
        print(f"  {'─' * 56}")

        old_line = new_line = 0
        for raw in raw_diff:
            line = raw.rstrip("\n\r")
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("@@"):
                m = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", line)
                if m:
                    old_line = int(m.group(1)) - 1
                    new_line = int(m.group(2)) - 1
                    rest     = m.group(3).strip()
                    hunk     = f"@@ -{m.group(1)} +{m.group(2)} @@"
                    suffix   = f"  {DIM}{rest}{RESET}" if rest else ""
                    print(f"  {DIM}{CYAN}{'':9s}  {hunk}{RESET}{suffix}")
            elif line.startswith("-"):
                old_line += 1
                content  = line[1:]
                gutter   = f"{DIM}{old_line:4d}     {RESET}"
                print(f"  {gutter} {_BG_RED}{RED}- {content}\033[K{RESET}")
            elif line.startswith("+"):
                new_line += 1
                content  = line[1:]
                gutter   = f"{DIM}     {new_line:4d}{RESET}"
                print(f"  {gutter} {_BG_GREEN}{GREEN}+ {content}\033[K{RESET}")
            else:
                old_line += 1
                new_line += 1
                content  = line[1:] if line.startswith(" ") else line
                gutter   = f"{DIM}{old_line:4d} {new_line:4d}{RESET}"
                print(f"  {gutter}  {DIM}│{RESET} {content}")
        return True

    def _show_file_diff(self, abs_path: Path, rel_str: str, target_commit: dict) -> bool:
        """Affiche le diff d'un fichier de l'espace de travail vs un commit."""
        last_hash = target_commit["snapshot"].get(rel_str)
        if not last_hash:
            print(f"  '{rel_str}' n'existait pas dans [{target_commit['id']}].")
            return False
        if abs_path.exists() and self._hash_file(abs_path) == last_hash:
            return False
        old_path = self._resolve_object_path(last_hash)
        if old_path is None:
            print(f"  Objet manquant pour '{rel_str}' (dépôt corrompu ?).")
            return False
        return self._render_diff(old_path, abs_path, rel_str)

    # ------------------------------------------------------------------
    # Commandes
    # ------------------------------------------------------------------

    def commit(self, name: Optional[str] = None, description: str = ""):
        auto_name = name is None
        if auto_name:
            name = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        current_state, files_saved = self._scan_working_directory(save_objects=True)
        history = self._load_history()
        previous_commit   = history[-1] if history else None
        previous_snapshot = previous_commit["snapshot"] if previous_commit else {}

        added, modified, deleted = self._diff_snapshots(previous_snapshot, current_state)

        if history and not (added or modified or deleted):
            print("Aucune modification détectée par rapport au dernier commit.")
            return

        if not auto_name:
            existing = [c for c in history if self._commit_name(c) == name]
            if existing:
                print(f"{YELLOW}Attention : un commit nommé '{name}' existe déjà ({existing[-1]['date']}).{RESET}")
                if not self._confirm("Continuer quand même ?"):
                    print("Annulé.")
                    return

        commit_id = hashlib.sha1(
            f"{json.dumps(current_state, sort_keys=True)}{name}{description}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:7]

        history.append({"id": commit_id, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         "name": name, "description": description, "snapshot": current_state})
        self.history_file.write_text(json.dumps(history, indent=4))

        print(f"\n[{commit_id}] Commit effectué : '{name}'")
        if description:
            print(f"  {CYAN}{description}{RESET}")
        print(f"  {DIM}{files_saved} nouveaux objets  ·  "
              f"+{len(added)}  ~{len(modified)}  -{len(deleted)}{RESET}")

        self._print_change_summary(added, modified, deleted)

        if previous_commit and modified:
            for rel_str in modified:
                self._show_file_diff(self.repo_root / rel_str, rel_str, previous_commit)

    def status(self):
        history = self._load_history()
        previous_snapshot = history[-1]["snapshot"] if history else {}
        current_state, _ = self._scan_working_directory(save_objects=False)
        added, modified, deleted = self._diff_snapshots(previous_snapshot, current_state)
        if not history:
            print("Aucun commit pour le moment. Au prochain commit, ces fichiers seront ajoutés :")
        else:
            print(f"Comparaison avec le dernier commit [{history[-1]['id']}] :")
        self._print_change_summary(added, modified, deleted)

    def log(self, n: Optional[int] = None):
        history = self._load_history()
        if not history:
            print("L'historique est vide.")
            return
        commits = history[-n:] if n else history
        for commit in reversed(commits):
            name        = self._commit_name(commit)
            description = commit.get("description", "")
            tags        = commit.get("tags", [])
            tag_badges  = "  " + "  ".join(f"{CYAN}[{t}]{RESET}" for t in tags) if tags else ""
            print(f"{YELLOW}[{commit['id']}]{RESET} - {commit['date']} ({len(commit['snapshot'])} fichier(s) suivis){tag_badges}")
            print(f"  {name}")
            if description:
                print(f"  {CYAN}{description}{RESET}")
            print()

    def diff(self, filepath: Optional[str] = None, commit_id: Optional[str] = None):
        history = self._load_history()
        if not history:
            raise SoloGitError("Aucun historique de commit existant.")

        target_commit = (self._find_commit(history, commit_id) if commit_id else history[-1])
        if commit_id and not target_commit:
            raise SoloGitError(f"Le commit '{commit_id}' est introuvable.")

        if filepath is not None:
            # --- diff d'un seul fichier ---
            abs_path, rel_str = self._resolve_target(filepath)
            if not abs_path.exists():
                raise SoloGitError(f"'{filepath}' introuvable dans le dossier actuel.")
            if not self._show_file_diff(abs_path, rel_str, target_commit):
                print(f"Le fichier est identique au commit [{target_commit['id']}].")
        else:
            # --- diff de tous les fichiers modifiés ---
            current_state, _ = self._scan_working_directory(save_objects=False)
            _, modified, _ = self._diff_snapshots(target_commit["snapshot"], current_state)
            if not modified:
                print(f"Aucune modification par rapport au commit [{target_commit['id']}].")
                return
            for rel_str in modified:
                self._show_file_diff(self.repo_root / rel_str, rel_str, target_commit)

    def amend(self, new_name: Optional[str] = None, new_description: Optional[str] = None):
        if new_name is None and new_description is None:
            raise SoloGitError("Précise au moins --name ou --description.")
        history = self._load_history()
        if not history:
            raise SoloGitError("Aucun commit à modifier.")

        last = history[-1]
        old_name = self._commit_name(last)

        if new_name is not None:
            existing = [c for c in history[:-1] if self._commit_name(c) == new_name]
            if existing:
                print(f"{YELLOW}Attention : un commit nommé '{new_name}' existe déjà ({existing[-1]['date']}).{RESET}")
                if not self._confirm("Continuer quand même ?"):
                    print("Annulé.")
                    return
            last["name"] = new_name

        if new_description is not None:
            last["description"] = new_description

        history[-1] = last
        self.history_file.write_text(json.dumps(history, indent=4))

        print(f"Commit [{last['id']}] modifié.")
        if new_name is not None:
            print(f"  nom         : '{old_name}' → '{new_name}'")
        if new_description is not None:
            print(f"  description : '{new_description}'")

    def undo(self, force: bool = False):
        history = self._load_history()
        if not history:
            raise SoloGitError("Aucun commit à annuler.")

        last = history[-1]
        print(f"Annulation du commit [{last['id']}] '{self._commit_name(last)}' du {last['date']}.")
        if not force and not self._confirm("Continuer ?"):
            print("Annulé.")
            return

        # Sauvegarde de l'espace de travail actuel
        current_state, _ = self._scan_working_directory(save_objects=False)
        for rel_str in current_state:
            abs_path = self.repo_root / rel_str
            if abs_path.exists():
                self._backup_file(abs_path, rel_str)

        history.pop()
        self.history_file.write_text(json.dumps(history, indent=4))

        if history:
            prev = history[-1]
            prev_snapshot = prev["snapshot"]
            extra_files = sorted(set(current_state) - set(prev_snapshot))
            for rel_str, file_hash in prev_snapshot.items():
                obj = self._resolve_object_path(file_hash)
                if obj is None:
                    print(f"Avertissement : objet manquant pour '{rel_str}', ignoré.")
                    continue
                dest = self.repo_root / rel_str
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(obj, dest)
            for rel_str in extra_files:
                (self.repo_root / rel_str).unlink()
            print(f"Retour au commit [{prev['id']}] '{self._commit_name(prev)}' effectué.")
        else:
            print("Historique vidé. L'espace de travail n'a pas été modifié.")

        if self._backup_session_dir:
            print(f"📦 Sauvegarde dans : {self._backup_session_dir}")

    def rename(self, identifier: str, new_name: str):
        history = self._load_history()
        commit = self._find_commit(history, identifier)
        if not commit:
            raise SoloGitError(f"Le commit '{identifier}' est introuvable.")

        old_name = self._commit_name(commit)
        existing = [c for c in history if self._commit_name(c) == new_name and c["id"] != commit["id"]]
        if existing:
            print(f"{YELLOW}Attention : un commit nommé '{new_name}' existe déjà ({existing[-1]['date']}).{RESET}")
            if not self._confirm("Continuer quand même ?"):
                print("Annulé.")
                return

        commit["name"] = new_name
        self.history_file.write_text(json.dumps(history, indent=4))
        print(f"Commit [{commit['id']}] renommé : '{old_name}' → '{new_name}'.")

    def show(self, identifier: str):
        history = self._load_history()
        commit = self._find_commit(history, identifier)
        if not commit:
            raise SoloGitError(f"Le commit '{identifier}' est introuvable.")

        name = self._commit_name(commit)
        description = commit.get("description", "")
        snapshot = commit["snapshot"]

        print(f"{YELLOW}[{commit['id']}]{RESET} - {commit['date']}")
        print(f"  {BOLD}{name}{RESET}")
        if description:
            print(f"  {CYAN}{description}{RESET}")
        print(f"\n  {len(snapshot)} fichier(s) suivis\n")

        if not snapshot:
            return

        col_hash = 9
        col_size = 9
        header = f"  {'HASH':<{col_hash}}  {'TAILLE':>{col_size}}  CHEMIN"
        print(header)
        print("  " + "-" * (len(header) - 2))

        for rel_str, file_hash in sorted(snapshot.items()):
            obj = self._resolve_object_path(file_hash)
            size_str = self._format_size(obj.stat().st_size) if obj else "?"
            print(f"  {file_hash[:7]:<{col_hash}}  {size_str:>{col_size}}  {rel_str}")

    def stats(self):
        history = self._load_history()

        # Objets référencés par au moins un commit
        referenced: set = set()
        for commit in history:
            referenced.update(commit["snapshot"].values())

        # Parcours de tous les objets stockés
        all_objects: Dict[str, int] = {}
        for f in self.objects_dir.rglob("*"):
            if not f.is_file():
                continue
            h = self._hash_from_object_path(f)
            all_objects[h] = f.stat().st_size

        total_count  = len(all_objects)
        total_size   = sum(all_objects.values())
        ref_count    = sum(1 for h in all_objects if h in referenced)
        ref_size     = sum(v for h, v in all_objects.items() if h in referenced)
        orphan_count = total_count - ref_count
        orphan_size  = total_size  - ref_size

        # Taille du dossier .sologit complet (history.json + objets + backups)
        sologit_size = sum(f.stat().st_size for f in self.base_dir.rglob("*") if f.is_file())

        print(f"{BOLD}Statistiques du dépôt{RESET}  ({self.base_dir})\n")
        print(f"  Commits         : {len(history)}")
        print(f"  Objets stockés  : {total_count}  ({self._format_size(total_size)})")
        print(f"  Objets actifs   : {ref_count}   ({self._format_size(ref_size)})")
        if orphan_count:
            print(f"  {YELLOW}Objets orphelins : {orphan_count}   ({self._format_size(orphan_size)}) "
                  f"— espace récupérable{RESET}")
        else:
            print(f"  Objets orphelins : 0   (aucun espace récupérable)")
        print(f"\n  Taille totale .sologit : {self._format_size(sologit_size)}")

    def export(self, identifier: str, dest_dir: str):
        history = self._load_history()
        commit = self._find_commit(history, identifier)
        if not commit:
            raise SoloGitError(f"Le commit '{identifier}' est introuvable.")

        dest = Path(dest_dir)
        if dest.exists() and any(dest.iterdir()):
            print(f"{YELLOW}'{dest}' existe déjà et n'est pas vide.{RESET}")
            if not self._confirm("Continuer et écraser les fichiers existants ?"):
                print("Annulé.")
                return

        dest.mkdir(parents=True, exist_ok=True)
        exported = 0
        for rel_str, file_hash in commit["snapshot"].items():
            obj = self._resolve_object_path(file_hash)
            if obj is None:
                print(f"Avertissement : objet manquant pour '{rel_str}', ignoré.")
                continue
            target = dest / rel_str
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(obj, target)
            exported += 1

        name = self._commit_name(commit)
        print(f"Export du commit [{commit['id']}] '{name}' terminé : {exported} fichier(s) → '{dest}'.")

    # ------------------------------------------------------------------
    # API publique pour les interfaces externes (CLI, plugins…)
    # ------------------------------------------------------------------

    def get_history(self) -> List[dict]:
        """Retourne l'historique complet des commits."""
        return self._load_history()

    def get_pending_changes(self) -> Tuple[List[str], List[str], List[str]]:
        """Retourne (ajoutés, modifiés, supprimés) vs le dernier commit."""
        history  = self._load_history()
        previous = history[-1]["snapshot"] if history else {}
        current, _ = self._scan_working_directory(save_objects=False)
        return self._diff_snapshots(previous, current)

    def get_checkout_preview(self, commit_id: str) -> Tuple[List[str], List[str]]:
        """Retourne (fichiers_écrasés, fichiers_supprimés) pour un checkout."""
        history = self._load_history()
        target  = self._find_commit(history, commit_id)
        if not target:
            raise SoloGitError(f"Le commit '{commit_id}' est introuvable.")
        current, _ = self._scan_working_directory(save_objects=False)
        snap          = target["snapshot"]
        changed_files = sorted(f for f, h in snap.items() if current.get(f) != h)
        extra_files   = sorted(set(current) - set(snap))
        return changed_files, extra_files

    def commit_name(self, commit: dict) -> str:
        """Retourne le nom lisible d'un commit (compatibilité ancien champ 'message')."""
        return self._commit_name(commit)

    def set_extensions(self, extensions: Optional[List[str]] = None,
                       no_extensions: Optional[List[str]] = None):
        """Régénère .sologitignore avec les nouvelles règles d'extensions."""
        new_content = self._build_sologitignore(extensions, no_extensions)
        self.ignore_file.write_text(new_content)
        self._ignore_patterns = None  # invalide le cache
        print("Fichier .sologitignore mis à jour.")
        if extensions:
            print(f"  Suivi    : {', '.join(extensions)}")
        if no_extensions:
            print(f"  Ignorés  : {', '.join(no_extensions)}")
        if not extensions and not no_extensions:
            print("  (aucun filtre — tous les fichiers seront suivis)")

    def tag(self, identifier: Optional[str] = None, tag_name: Optional[str] = None,
            delete: bool = False, list_tags: bool = False):
        history = self._load_history()

        if list_tags or (not identifier and not delete):
            all_tags = [(c, t) for c in history for t in c.get("tags", [])]
            if not all_tags:
                print("Aucun tag défini.")
            else:
                for commit, t in all_tags:
                    name = self._commit_name(commit)
                    print(f"  {CYAN}{t:<15}{RESET} [{commit['id']}] {name}  {DIM}({commit['date'][:10]}){RESET}")
            return

        if delete and tag_name:
            removed = 0
            for commit in history:
                tags = commit.get("tags", [])
                if tag_name in tags:
                    tags.remove(tag_name)
                    commit["tags"] = tags
                    removed += 1
            if removed:
                self.history_file.write_text(json.dumps(history, indent=4))
                print(f"Tag '{CYAN}{tag_name}{RESET}' supprimé ({removed} commit(s) mis à jour).")
            else:
                print(f"Tag '{tag_name}' introuvable.")
            return

        if identifier and tag_name:
            commit = self._find_commit(history, identifier)
            if not commit:
                raise SoloGitError(f"Le commit '{identifier}' est introuvable.")
            tags = commit.setdefault("tags", [])
            if tag_name in tags:
                print(f"Le commit [{commit['id']}] a déjà le tag '{tag_name}'.")
                return
            tags.append(tag_name)
            self.history_file.write_text(json.dumps(history, indent=4))
            name = self._commit_name(commit)
            print(f"Tag '{CYAN}{tag_name}{RESET}' ajouté au commit [{commit['id']}] '{name}'.")
            return

        raise SoloGitError(
            "Usage : sologit tag <commit> <tag>  |  sologit tag --delete <tag>  |  sologit tag"
        )

    def fsck(self):
        history      = self._load_history()
        issues: List[str] = []
        referenced: set   = set()

        for commit in history:
            name = self._commit_name(commit)
            for rel_str, file_hash in commit["snapshot"].items():
                referenced.add(file_hash)
                obj_path = self._resolve_object_path(file_hash)
                if obj_path is None:
                    issues.append(f"[{commit['id']}] '{name}' : objet manquant pour '{rel_str}' ({file_hash[:8]})")
                else:
                    actual = self._hash_file(obj_path)
                    if actual != file_hash:
                        issues.append(
                            f"[{commit['id']}] '{name}' : corrompu '{rel_str}' "
                            f"(attendu {file_hash[:8]}, lu {actual[:8]})"
                        )

        orphan_count = sum(
            1 for f in self.objects_dir.rglob("*")
            if f.is_file() and self._hash_from_object_path(f) not in referenced
        )

        print(f"{BOLD}Vérification d'intégrité{RESET}  ({self.base_dir})\n")
        print(f"  Commits vérifiés  : {len(history)}")
        print(f"  Objets référencés : {len(referenced)}")

        if issues:
            print(f"\n  {RED}{BOLD}{len(issues)} problème(s) détecté(s) :{RESET}")
            for issue in issues:
                print(f"  {RED}✗ {issue}{RESET}")
        else:
            print(f"\n  {GREEN}✓ Aucun problème — le dépôt est intègre.{RESET}")

        if orphan_count:
            print(f"  {YELLOW}⚠  {orphan_count} objet(s) orphelin(s) (voir 'sologit stats'){RESET}")

    def restore(self, commit_id: str, filepath: str, force: bool = False):
        history = self._load_history()
        commit_to_restore = self._find_commit(history, commit_id)
        if not commit_to_restore:
            raise SoloGitError(f"Le commit '{commit_id}' est introuvable.")

        abs_path, rel_str = self._resolve_target(filepath)
        file_hash = commit_to_restore["snapshot"].get(rel_str)
        if not file_hash:
            raise SoloGitError(f"'{filepath}' n'était pas présent dans le commit [{commit_to_restore['id']}].")

        object_path = self._resolve_object_path(file_hash)
        if object_path is None:
            raise SoloGitError("Objet introuvable dans le stockage (dépôt corrompu ?).")

        if abs_path.exists():
            if not force and not self._confirm(f"⚠️  Ceci va écraser '{rel_str}'. Continuer ?"):
                print("Annulé.")
                return
            self._backup_file(abs_path, rel_str)

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(object_path, abs_path)
        print(f"Restauration réussie : '{filepath}' → commit [{commit_to_restore['id']}].")
        if self._backup_session_dir:
            print(f"📦 Sauvegarde dans : {self._backup_session_dir}")

    def checkout(self, commit_id: str, force: bool = False):
        history = self._load_history()
        target_commit = self._find_commit(history, commit_id)
        if not target_commit:
            raise SoloGitError(f"Le commit '{commit_id}' est introuvable.")

        target_snapshot = target_commit["snapshot"]
        current_state, _ = self._scan_working_directory(save_objects=False)
        extra_files   = sorted(set(current_state) - set(target_snapshot))
        changed_files = sorted(f for f, h in target_snapshot.items() if current_state.get(f) != h)

        if not changed_files and not extra_files:
            print(f"L'espace de travail correspond déjà au commit [{target_commit['id']}].")
            return

        if not force:
            print(f"Le checkout vers [{target_commit['id']}] va :")
            if changed_files:
                print(f"  - écraser {len(changed_files)} fichier(s) :")
                for f in changed_files[:15]: print(f"      {YELLOW}~ {f}{RESET}")
                if len(changed_files) > 15:  print(f"      ... et {len(changed_files)-15} de plus")
            if extra_files:
                print(f"  - supprimer {len(extra_files)} fichier(s) :")
                for f in extra_files[:15]: print(f"      {RED}- {f}{RESET}")
                if len(extra_files) > 15:  print(f"      ... et {len(extra_files)-15} de plus")
            if not self._confirm("Continuer ?"):
                print("Annulé.")
                return

        for f in set(changed_files) | set(extra_files):
            abs_path = self.repo_root / f
            if abs_path.exists():
                self._backup_file(abs_path, f)

        restored = 0
        for rel_str, file_hash in target_snapshot.items():
            obj = self._resolve_object_path(file_hash)
            if obj is None:
                print(f"Avertissement : objet manquant pour '{rel_str}', ignoré.")
                continue
            dest = self.repo_root / rel_str
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(obj, dest)
            restored += 1

        removed = 0
        for rel_str in extra_files:
            (self.repo_root / rel_str).unlink()
            removed += 1

        print(f"Checkout terminé vers [{target_commit['id']}] : {restored} restauré(s), {removed} supprimé(s).")
        if self._backup_session_dir:
            print(f"📦 Sauvegarde dans : {self._backup_session_dir}")


# ----------------------------------------------------------------------
# Découverte du dépôt
# ----------------------------------------------------------------------

def find_repo_root(start: Path) -> Optional[Path]:
    current = start.resolve()
    while True:
        if (current / REPO_DIR_NAME).is_dir():
            return current
        if current.parent == current:
            return None
        current = current.parent


def parse_extensions(raw: Optional[str]) -> Optional[List[str]]:
    """Convertit une chaîne d'extensions en liste (.py .tex → ['.py', '.tex'])."""
    if not raw:
        return None
    exts = [p if p.startswith(".") else f".{p}" for p in raw.strip().split()]
    return exts or None


def main():
    parser = argparse.ArgumentParser(description="SoloGit : Un mini-Git local écrit en Python.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Init
    p = subparsers.add_parser("init", help="Initialiser le dépôt (.sologit).")
    p.add_argument("--extension",    metavar="EXTS", default=None,
                   help='Extensions à suivre. Ex: --extension ".py .tex"')
    p.add_argument("--no_extension", metavar="EXTS", default=None,
                   help='Extensions à ignorer. Ex: --no_extension ".log .tmp"')

    # 2. Commit
    p = subparsers.add_parser("commit", help="Sauvegarder l'état actuel.")
    p.add_argument("name",        nargs="?", default=None, help="Nom du commit (optionnel).")
    p.add_argument("description", nargs="?", default="",   help="Description optionnelle.")

    # 3. Status
    subparsers.add_parser("status", help="Voir ce qui a changé depuis le dernier commit.")

    # 4. Log
    p = subparsers.add_parser("log", help="Afficher l'historique.")
    p.add_argument("-n", "--number", type=int, default=None, metavar="N",
                   help="Limiter aux N derniers commits.")

    # 5. Diff
    p = subparsers.add_parser("diff", help="Voir les modifications (tous les fichiers si aucun précisé).")
    p.add_argument("file",      nargs="?", default=None, help="Fichier à examiner (optionnel).")
    p.add_argument("commit_id", nargs="?", default=None, help="Commit à comparer (défaut : le dernier).")

    # 6. Amend
    p = subparsers.add_parser("amend", help="Modifier le nom/description du dernier commit.")
    p.add_argument("--name",        default=None, help="Nouveau nom.")
    p.add_argument("--description", default=None, help="Nouvelle description.")

    # 7. Undo
    p = subparsers.add_parser("undo", help="Annuler le dernier commit et revenir à l'état précédent.")
    p.add_argument("-f", "--force", action="store_true", help="Sans confirmation.")

    # 8. Rename
    p = subparsers.add_parser("rename", help="Renommer un commit.")
    p.add_argument("identifier", help="Nom ou ID du commit à renommer.")
    p.add_argument("new_name",   help="Nouveau nom.")

    # 9. Show
    p = subparsers.add_parser("show", help="Afficher les fichiers d'un commit avec leur taille et hash.")
    p.add_argument("identifier", help="Nom ou ID du commit.")

    # 10. Stats
    subparsers.add_parser("stats", help="Résumé de l'espace disque utilisé par .sologit.")

    # 11. Export
    p = subparsers.add_parser("export", help="Copier le snapshot d'un commit vers un dossier externe.")
    p.add_argument("identifier", help="Nom ou ID du commit.")
    p.add_argument("dest",       help="Dossier de destination.")

    # 12. Extensions
    p = subparsers.add_parser("extensions", help="Voir ou modifier les extensions suivies/ignorées.")
    p.add_argument("--extension",    metavar="EXTS", default=None,
                   help='Extensions à suivre. Ex: --extension ".py .tex"')
    p.add_argument("--no_extension", metavar="EXTS", default=None,
                   help='Extensions à ignorer. Ex: --no_extension ".log .tmp"')
    p.add_argument("--show", "-s", action="store_true",
                   help="Afficher le .sologitignore actuel.")

    # 13. Tag
    p = subparsers.add_parser("tag", help="Tagger un commit (v1.0, release…).")
    p.add_argument("identifier", nargs="?", default=None, help="Nom ou ID du commit.")
    p.add_argument("tag_name",   nargs="?", default=None, help="Nom du tag à ajouter.")
    p.add_argument("--delete", "-d", metavar="TAG", default=None,
                   help="Supprimer ce tag de tous les commits.")
    p.add_argument("--list",   "-l", action="store_true", help="Lister tous les tags.")

    # 13. Fsck
    subparsers.add_parser("fsck", help="Vérifier l'intégrité du dépôt.")

    # 14. Restore
    p = subparsers.add_parser("restore", help="Restaurer un seul fichier depuis le passé.")
    p.add_argument("commit_id", help="Nom ou ID du commit.")
    p.add_argument("file",      help="Fichier à restaurer.")
    p.add_argument("-f", "--force", action="store_true", help="Sans confirmation.")

    # 13. Checkout
    p = subparsers.add_parser("checkout", help="Restaurer TOUS les fichiers à l'état d'un commit.")
    p.add_argument("commit_id", help="Nom ou ID du commit.")
    p.add_argument("-f", "--force", action="store_true", help="Sans confirmation.")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if args.command == "init":
        SoloGit(Path.cwd()).init(
            extensions=parse_extensions(args.extension),
            no_extensions=parse_extensions(args.no_extension),
        )
        return

    repo_root = find_repo_root(Path.cwd())
    if repo_root is None:
        print("fatal : dépôt sologit introuvable. Lancez d'abord 'sologit init'.")
        sys.exit(1)

    app = SoloGit(repo_root)

    try:
        if args.command == "commit":
            name, description = args.name, args.description
            if name is not None and " " in name and not description:
                description, name = name, None
            app.commit(name, description)
        elif args.command == "status":
            app.status()
        elif args.command == "log":
            app.log(n=args.number)
        elif args.command == "diff":
            app.diff(args.file, args.commit_id)
        elif args.command == "amend":
            app.amend(new_name=args.name, new_description=args.description)
        elif args.command == "undo":
            app.undo(force=args.force)
        elif args.command == "rename":
            app.rename(args.identifier, args.new_name)
        elif args.command == "show":
            app.show(args.identifier)
        elif args.command == "stats":
            app.stats()
        elif args.command == "export":
            app.export(args.identifier, args.dest)
        elif args.command == "restore":
            app.restore(args.commit_id, args.file, force=args.force)
        elif args.command == "checkout":
            app.checkout(args.commit_id, force=args.force)
        elif args.command == "extensions":
            if args.show or (not args.extension and not args.no_extension):
                if app.ignore_file.exists():
                    print(app.ignore_file.read_text())
                else:
                    print("Aucun fichier .sologitignore.")
            else:
                app.set_extensions(
                    extensions=parse_extensions(args.extension),
                    no_extensions=parse_extensions(args.no_extension),
                )
        elif args.command == "tag":
            if args.delete:
                app.tag(tag_name=args.delete, delete=True)
            elif args.list or (not args.identifier and not args.tag_name):
                app.tag(list_tags=True)
            else:
                app.tag(identifier=args.identifier, tag_name=args.tag_name)
        elif args.command == "fsck":
            app.fsck()
    except SoloGitError as e:
        print(f"Erreur : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
