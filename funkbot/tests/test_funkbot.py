"""FunkBot's own check suite. Runs after every self-edit; a red test rolls it back.

No network, no API key needed — everything here is the local machinery.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import hooks          # noqa: E402
import memory         # noqa: E402
import safety         # noqa: E402
import selfmod        # noqa: E402
import skills         # noqa: E402
import tools          # noqa: E402
import usage          # noqa: E402


# ------------------------------------------------------------------ memory

def test_remember_then_recall():
    memory.remember("test-subject", "a distinctive marmalade fact", "fact")
    hits = memory.recall("marmalade")
    assert any("marmalade" in h["snip"] for h in hits)


def test_lessons_reach_the_prompt():
    lid = memory.add_lesson("running the test suite", "keep lessons actionable")
    assert lid > 0
    assert "keep lessons actionable" in memory.memory_prompt()


def test_bad_lesson_retires_itself():
    lid = memory.add_lesson("a doomed situation", "a lesson that keeps losing")
    for _ in range(4):
        memory.score_lesson(lid, -1.0)
    assert all(row["id"] != lid for row in memory.active_lessons())


# ------------------------------------------------------------------ safety

@pytest.mark.parametrize("command", [
    "rm -rf /", "mkfs.ext4 /dev/sda", "dd if=/dev/zero of=/dev/sda",
    ":(){ :|:& };:",
])
def test_destructive_commands_are_denied(command):
    level, _ = safety.decide("bash", {"command": command})
    assert level == "deny"


def test_read_only_commands_are_allowed():
    assert safety.decide("bash", {"command": "git status"})[0] == "allow"
    assert safety.decide("read_file", {"path": "/tmp/x"})[0] == "allow"


def test_writes_require_approval():
    assert safety.decide("write_file", {"path": "/tmp/x"})[0] == "ask"


def test_unattended_gate_declines_by_default():
    gate = safety.Gate(approver=None)
    safety.UNATTENDED = "deny"
    ok, _ = gate.check("write_file", {"path": "/tmp/x", "content": ""})
    assert ok is False


def test_gate_remembers_an_approval():
    gate = safety.Gate(approver=lambda *a: True)
    assert gate.check("bash", {"command": "echo hi"})[0] is True
    gate.approver = lambda *a: False          # would decline now
    assert gate.check("bash", {"command": "echo hi"})[0] is True


# ------------------------------------------------------------------ hooks

def test_pre_tool_hook_can_block():
    @hooks.on("pre_tool")
    def blocker(ctx):
        if ctx.get("tool") == "forbidden":
            return {"block": "nope"}
        return {}

    assert hooks.fire("pre_tool", {"tool": "forbidden"}).get("block") == "nope"
    assert hooks.fire("pre_tool", {"tool": "fine"}).get("block") is None


def test_broken_hook_does_not_break_the_run():
    @hooks.on("post_tool")
    def explode(ctx):
        raise ValueError("boom")

    assert "error" in hooks.fire("post_tool", {})


# ------------------------------------------------------------------ tools

def test_every_tool_has_a_valid_spec():
    for spec in tools.specs():
        assert spec["name"] and spec["description"]
        assert spec["input_schema"]["type"] == "object"


def test_tool_dispatch_round_trip():
    out = tools.call("bash", {"command": "echo funkbot"})
    assert "funkbot" in out


def test_unknown_tool_is_reported_not_raised():
    assert "unknown tool" in tools.call("no_such_tool", {})


# ------------------------------------------------------------------ selfmod

def test_self_writes_stay_inside_the_package():
    with pytest.raises(ValueError):
        selfmod._safe("../../etc/passwd")


def test_syntax_gate_rejects_broken_python(tmp_path):
    target = selfmod.ROOT / "_syntax_probe.py"
    try:
        assert "wrote" in selfmod.write_own_file("_syntax_probe.py", "x = 1\n")
        assert "REJECTED" in selfmod.write_own_file("_syntax_probe.py", "def (:\n")
        assert target.read_text() == "x = 1\n"      # unchanged by the bad write
    finally:
        target.unlink(missing_ok=True)
        for bak in selfmod.ROOT.glob("_syntax_probe.py.bak.*"):
            bak.unlink()


def test_rollback_restores_the_previous_version():
    target = selfmod.ROOT / "_rollback_probe.py"
    try:
        selfmod.write_own_file("_rollback_probe.py", "value = 1\n")
        selfmod.write_own_file("_rollback_probe.py", "value = 2\n")
        selfmod.rollback("_rollback_probe.py")
        assert target.read_text() == "value = 1\n"
    finally:
        target.unlink(missing_ok=True)
        for bak in selfmod.ROOT.glob("_rollback_probe.py.bak.*"):
            bak.unlink()


# ------------------------------------------------------------------ skills

def test_skill_round_trip():
    skills.write_skill("probe-skill", "a test skill", "# body\ndo the thing")
    assert any(s["name"] == "probe-skill" for s in skills.catalog())
    assert "do the thing" in skills.load("probe-skill")


def test_missing_skill_reports_alternatives():
    assert "no skill named" in skills.load("definitely-not-a-skill")


# ------------------------------------------------------------------ usage

def test_cost_and_cache_math():
    u = usage.Usage(model="claude-opus-5", input_tokens=1_000_000,
                    output_tokens=1_000_000, cache_read=1_000_000)
    assert u.cost == pytest.approx(5.0 + 25.0 + 0.5)
    assert u.cache_hit_rate == pytest.approx(0.5)
