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
import os
import sys
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


IN_CHECK = "FUNKBOT_IN_CHECK"

# A packaged build has no source tree, no interpreter to shell out to, and no
# git — so the source checks below cannot run, and neither can self-editing.
PACKAGED = getattr(sys, "frozen", False)
PACKAGED_NOTE = ("packaged build — source checks and self-modification need a "
                 "source checkout; run from source for those")


def run_checks(skip_tests: bool = False) -> tuple[bool, str]:
    """Run every check. Returns (ok, combined output).

    The test step shells out to pytest, so a self-edit made *from inside* a
    check would re-enter the suite and hang. The child is marked, and a marked
    process runs syntax and imports only.
    """
    if PACKAGED:
        return True, f"[SKIP] {PACKAGED_NOTE}"

    nested = os.getenv(IN_CHECK) == "1"
    env = {**os.environ, IN_CHECK: "1"}

    lines = []
    for name, cmd in CHECKS:
        if (skip_tests or nested) and name == "tests":
            continue
        if name == "tests" and not (ROOT / "tests").is_dir():
            continue
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           timeout=300, env=env)
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
    if PACKAGED:
        raise VerificationFailed(
            f"refusing to self-edit '{description}': {PACKAGED_NOTE}")
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


_LAST_FULL: dict = {}
FULL_HEALTH_TTL = 300          # seconds


def health(full: bool = False) -> str:
    """Is FunkBot currently sound?

    Default is the quick pass — syntax and imports, well under a second. The
    full pass also runs the test suite, which takes seconds and pins a core, so
    it is cached for FULL_HEALTH_TTL and never runs on a UI poll. Gating a
    self-edit always uses the full suite via guard(), not this.
    """
    if full:
        cached = _LAST_FULL.get("at", 0)
        if time.time() - cached < FULL_HEALTH_TTL:
            ok, report = _LAST_FULL["ok"], _LAST_FULL["report"]
        else:
            ok, report = run_checks()
            _LAST_FULL.update(at=time.time(), ok=ok, report=report)
    else:
        ok, report = run_checks(skip_tests=True)

    disk = shutil.disk_usage(ROOT)
    state = "PACKAGED" if PACKAGED else ("HEALTHY" if ok else "BROKEN")
    return f"{state}\n{report}\ndisk free: {disk.free // 2**20} MB"
