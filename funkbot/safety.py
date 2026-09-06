"""Permission policy. Nothing dangerous runs just because the model asked.

Every tool call is classified allow / ask / deny before it executes. Rules are
patterns in policy.json, so you tune them without touching code:

    {
      "deny":  ["bash:rm -rf /*", "bash:*mkfs*", "write_file:/etc/*"],
      "ask":   ["bash:*", "write_file:*", "patch_own_code:*"],
      "allow": ["bash:git *", "bash:ls*", "read_file:*", "recall:*"]
    }

Precedence: deny always wins. Between allow and ask the most specific pattern
wins, so a blanket `"ask": ["bash:*"]` still lets `"allow": ["bash:git status*"]`
through; on an exact tie, ask wins. Anything unmatched falls to
DEFAULT_DECISION. In headless runs (no approver attached) "ask" resolves to the
value of FUNKBOT_UNATTENDED — "deny" by default, so an unsupervised bot cannot
quietly escalate.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from typing import Callable

from config import ROOT

POLICY_PATH = ROOT / "policy.json"
DEFAULT_DECISION = "ask"
UNATTENDED = os.getenv("FUNKBOT_UNATTENDED", "deny")

DEFAULT_POLICY = {
    "deny": [
        "bash:*rm -rf /*", "bash:*mkfs*", "bash:*dd if=*of=/dev/*",
        "bash:*:(){ :|:& };:*", "bash:*chmod -R 777 /*",
        "bash:*curl*|*sh", "bash:*wget*|*sh",
        "write_file:/etc/*", "write_file:*/.ssh/*", "write_file:*/.aws/*",
        "read_file:*/.ssh/id_*", "read_file:*/.aws/credentials",
        "bash:*git push*--force*", "bash:*git reset --hard*",
    ],
    "ask": [
        "bash:*", "write_file:*", "edit_file:*", "restart_self:*",
        "patch_own_code:*", "write_own_file:*", "add_own_tool:*",
    ],
    "allow": [
        "read_file:*", "recall:*", "remember:*", "record_lesson:*",
        "list_own_files:*", "read_own_code:*", "search_own_code:*",
        "self_status:*", "load_skill:*", "write_skill:*", "http_get:*",
        "rollback:*", "commit_self:*", "reload_self:*", "spawn_agent:*",
        "bash:git status*", "bash:git diff*", "bash:git log*", "bash:ls*",
        "bash:cat *", "bash:grep *", "bash:rg *", "bash:find *", "bash:pytest*",
        "mcp__*",
    ],
}

# Things that are never a good idea regardless of policy file.
HARD_BLOCK = re.compile(
    r"(rm\s+-rf\s+/(?:\s|$))|(:\(\)\{.*\};:)|(>\s*/dev/sd[a-z])|"
    r"(mkfs\.)|(shutdown\b)|(\bhalt\b)|(dd\s+if=.*of=/dev/)",
    re.I,
)


def load_policy() -> dict:
    if POLICY_PATH.exists():
        try:
            user = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            return {k: DEFAULT_POLICY.get(k, []) + user.get(k, [])
                    for k in ("deny", "ask", "allow")}
        except json.JSONDecodeError:
            pass
    return DEFAULT_POLICY


def _signature(tool: str, args: dict) -> str:
    """'bash:git push origin main' — what the patterns match against."""
    if tool == "bash":
        payload = args.get("command", "")
    elif tool in {"read_file", "write_file", "edit_file"}:
        payload = args.get("path", "")
    elif tool == "http_get":
        payload = args.get("url", "")
    else:
        payload = " ".join(str(v) for v in args.values())[:200]
    return f"{tool}:{payload}"


def decide(tool: str, args: dict) -> tuple[str, str]:
    """Returns (allow|ask|deny, reason)."""
    sig = _signature(tool, args)

    if tool == "bash" and HARD_BLOCK.search(args.get("command", "")):
        return "deny", "matches a hard-blocked destructive pattern"

    policy = load_policy()

    def matches(level: str) -> list[str]:
        return [p for p in policy.get(level, [])
                if fnmatch.fnmatch(sig, p) or fnmatch.fnmatch(sig, p + "*")]

    if denied := matches("deny"):
        return "deny", f"matched deny rule {denied[0]!r}"

    # Most specific wins; a blanket ask must not override a targeted allow.
    best_ask = max(matches("ask"), key=len, default=None)
    best_allow = max(matches("allow"), key=len, default=None)
    if best_allow and (best_ask is None or len(best_allow) > len(best_ask)):
        return "allow", f"matched allow rule {best_allow!r}"
    if best_ask:
        return "ask", f"matched ask rule {best_ask!r}"
    if best_allow:
        return "allow", f"matched allow rule {best_allow!r}"
    return DEFAULT_DECISION, "no rule matched"


class Gate:
    """Wraps an approver. `approve(tool, args, reason) -> bool`, or None for headless."""

    def __init__(self, approver: Callable[[str, dict, str], bool] | None = None):
        self.approver = approver
        self.granted: set[str] = set()      # "always allow" for this process

    def check(self, tool: str, args: dict) -> tuple[bool, str]:
        level, reason = decide(tool, args)
        if level == "allow":
            return True, reason
        if level == "deny":
            return False, f"blocked: {reason}"

        sig = _signature(tool, args)
        if sig in self.granted or f"{tool}:*" in self.granted:
            return True, "approved earlier this session"
        if self.approver is None:
            return UNATTENDED == "allow", f"unattended, {reason}"
        if self.approver(tool, args, reason):
            self.granted.add(sig)
            return True, "approved"
        return False, "declined by operator"
