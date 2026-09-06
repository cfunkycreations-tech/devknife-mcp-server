"""
FunkBot self-modification toolkit.

Drop this file next to FunkBot's main module and import it. Every function is a
plain callable, so it registers as a tool in any framework (see README.md).

Safety rails baked in:
  - all writes confined to ROOT (no path escapes)
  - .bak backup + AST syntax check before any write; auto-rollback on bad syntax
  - optional git commit per change so you can always `git revert`
"""

from __future__ import annotations

import ast
import difflib
import importlib
import os
import pathlib
import shutil
import subprocess
import sys
import time

# The directory FunkBot is allowed to edit — its own source tree.
ROOT = pathlib.Path(__file__).resolve().parent


def _safe(rel_path: str) -> pathlib.Path:
    p = (ROOT / rel_path).resolve()
    if not str(p).startswith(str(ROOT)):
        raise ValueError(f"refusing to touch path outside {ROOT}: {rel_path}")
    return p


# --------------------------------------------------------------------------
# 1. Look at itself
# --------------------------------------------------------------------------

def list_own_files(pattern: str = "**/*.py") -> list[str]:
    """List FunkBot's own source files."""
    return sorted(
        str(p.relative_to(ROOT))
        for p in ROOT.glob(pattern)
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    )


def read_own_code(rel_path: str, start: int = 1, end: int | None = None) -> str:
    """Read FunkBot's own source, numbered, optionally a line range."""
    lines = _safe(rel_path).read_text(encoding="utf-8").splitlines()
    end = end or len(lines)
    return "\n".join(f"{i:>5}  {l}" for i, l in enumerate(lines[start - 1:end], start))


def search_own_code(needle: str) -> list[str]:
    """Grep FunkBot's own source."""
    hits = []
    for rel in list_own_files():
        for i, line in enumerate(_safe(rel).read_text(encoding="utf-8").splitlines(), 1):
            if needle in line:
                hits.append(f"{rel}:{i}: {line.strip()}")
    return hits


# --------------------------------------------------------------------------
# 2. Change itself
# --------------------------------------------------------------------------

def _check_and_write(path: pathlib.Path, new_src: str, note: str) -> str:
    old_src = path.read_text(encoding="utf-8") if path.exists() else ""
    if path.suffix == ".py":
        try:
            ast.parse(new_src)
        except SyntaxError as e:
            return f"REJECTED (syntax error line {e.lineno}): {e.msg}"

    backup = path.with_suffix(path.suffix + f".bak.{int(time.time())}")
    if path.exists():
        shutil.copy2(path, backup)
    path.write_text(new_src, encoding="utf-8")

    diff = "\n".join(
        difflib.unified_diff(
            old_src.splitlines(), new_src.splitlines(),
            fromfile=f"a/{path.name}", tofile=f"b/{path.name}", lineterm="",
        )
    )
    return f"wrote {path.relative_to(ROOT)} ({note}); backup {backup.name}\n{diff or '(no textual change)'}"


def patch_own_code(rel_path: str, find: str, replace: str, count: int = 1) -> str:
    """Exact-string patch of FunkBot's own source. `find` must appear verbatim."""
    path = _safe(rel_path)
    src = path.read_text(encoding="utf-8")
    if find not in src:
        return f"NOT FOUND in {rel_path}: {find[:80]!r}"
    return _check_and_write(path, src.replace(find, replace, count), "patch")


def write_own_file(rel_path: str, source: str) -> str:
    """Create or fully overwrite one of FunkBot's own files (e.g. a brand-new tool)."""
    path = _safe(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return _check_and_write(path, source, "write")


def add_own_tool(name: str, source: str, module: str = "tools_generated.py") -> str:
    """Append a new tool function to FunkBot's generated-tools module and load it."""
    path = _safe(module)
    header = "" if path.exists() else '"""Tools FunkBot wrote for itself."""\n'
    src = (path.read_text(encoding="utf-8") if path.exists() else header) + "\n\n" + source.strip() + "\n"
    result = _check_and_write(path, src, f"add tool {name}")
    if result.startswith("REJECTED"):
        return result
    return result + "\n" + reload_self(module.removesuffix(".py"))


def rollback(rel_path: str) -> str:
    """Restore the most recent backup of a file FunkBot edited."""
    path = _safe(rel_path)
    backups = sorted(path.parent.glob(path.name + ".bak.*"))
    if not backups:
        return f"no backups for {rel_path}"
    shutil.copy2(backups[-1], path)
    return f"restored {rel_path} from {backups[-1].name}"


# --------------------------------------------------------------------------
# 3. Apply the change without a full restart
# --------------------------------------------------------------------------

def reload_self(module_name: str) -> str:
    """Hot-reload one of FunkBot's own modules in the running process."""
    try:
        mod = sys.modules.get(module_name) or importlib.import_module(module_name)
        importlib.reload(mod)
        return f"reloaded {module_name}"
    except Exception as e:  # noqa: BLE001 - report, don't crash the bot
        return f"reload failed for {module_name}: {type(e).__name__}: {e}"


def restart_self(reason: str = "self-update") -> str:
    """Re-exec FunkBot's process so all edits take effect. This does not return."""
    print(f"[funkbot] restarting: {reason}", flush=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)


# --------------------------------------------------------------------------
# 4. Keep a record
# --------------------------------------------------------------------------

def commit_self(message: str) -> str:
    """Git-commit FunkBot's own changes so any edit is revertible."""
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()

    git("add", "-A")
    git("commit", "-m", f"funkbot: {message}")
    return git("log", "-1", "--oneline") or "nothing to commit"


def self_status() -> str:
    """What FunkBot changed about itself recently."""
    out = subprocess.run(
        ["git", "log", "-10", "--oneline"], cwd=ROOT, capture_output=True, text=True
    )
    return (out.stdout or out.stderr).strip()


SELF_MOD_TOOLS = [
    list_own_files, read_own_code, search_own_code,
    patch_own_code, write_own_file, add_own_tool, rollback,
    reload_self, restart_self, commit_self, self_status,
]
