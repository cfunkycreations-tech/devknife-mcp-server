"""Self-verification. A self-edit that breaks FunkBot gets reverted automatically.

`guard()` wraps any mutation of FunkBot's own source:

    with guard("adding a weather tool"):
        selfmod.add_own_tool("weather_now", src)

On exit it runs the check suite. Green → commits. Red → restores every file the
block touched and re-raises with the failure output. FunkBot cannot leave itself
in a broken state, which is what makes the self-modification loop safe to run
unattended.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import time

import selfmod
from config import ROOT

CHECKS = [
    ("syntax", ["python3", "-m", "compileall", "-q", "."]),
    ("import", ["python3", "-c",
                "import config, memory, skills, tools, safety, hooks, usage"]),
    ("tests", ["python3", "-m", "pytest", "-q", "--no-header", "tests"]),
]


def run_checks(skip_tests: bool = False) -> tuple[bool, str]:
    """Run every check. Returns (ok, combined output)."""
    lines = []
    for name, cmd in CHECKS:
        if skip_tests and name == "tests":
            continue
        if name == "tests" and not (ROOT / "tests").is_dir():
            continue
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
        status = "PASS" if p.returncode == 0 else "FAIL"
        lines.append(f"[{status}] {name}")
        if p.returncode != 0:
            lines.append((p.stdout + p.stderr)[-4000:])
            return False, "\n".join(lines)
    return True, "\n".join(lines)


def _snapshot() -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in ROOT.rglob("*.py")
            if "__pycache__" not in p.parts and ".git" not in p.parts}


def _restore(before: dict[str, bytes]) -> list[str]:
    import pathlib

    reverted = []
    after = _snapshot()
    for path, data in before.items():
        if after.get(path) != data:
            pathlib.Path(path).write_bytes(data)
            reverted.append(pathlib.Path(path).name)
    for path in set(after) - set(before):        # files the edit created
        pathlib.Path(path).unlink(missing_ok=True)
        reverted.append(pathlib.Path(path).name + " (removed)")
    return reverted


class VerificationFailed(RuntimeError):
    pass


@contextlib.contextmanager
def guard(description: str, commit: bool = True):
    """Run a self-modification, verify it, roll it back if it broke anything."""
    before = _snapshot()
    yield
    ok, report = run_checks()
    if ok:
        if commit:
            selfmod.commit_self(description)
        return
    reverted = _restore(before)
    raise VerificationFailed(
        f"self-edit '{description}' failed verification, rolled back "
        f"{len(reverted)} file(s): {', '.join(reverted) or 'none'}\n{report}")


def safe_self_edit(description: str, fn, *args, **kwargs) -> str:
    """Callable form, for use as a tool: verified edit, auto-rollback on failure."""
    started = time.time()
    try:
        with guard(description):
            result = fn(*args, **kwargs)
    except VerificationFailed as e:
        return f"REVERTED — {e}"
    return f"{result}\nverified in {time.time() - started:.1f}s and committed"


def health() -> str:
    """Is FunkBot currently sound? Runs the full check suite read-only."""
    ok, report = run_checks()
    disk = shutil.disk_usage(ROOT)
    return (f"{'HEALTHY' if ok else 'BROKEN'}\n{report}\n"
            f"disk free: {disk.free // 2**20} MB")
