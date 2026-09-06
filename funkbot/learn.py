"""Recursive learning.

Three loops, each feeding the next:

  1. reflect(session)   — read what just happened, extract lessons + facts,
                          and (when a pattern repeats) write a new skill or tool.
  2. consolidate()      — reflect on the LESSONS THEMSELVES: merge duplicates,
                          promote repeated lessons into skills, retire dead ones.
                          This is the recursive step — output of learning becomes
                          input to learning, bounded by MAX_LEARN_DEPTH.
  3. score_outcome()    — cheap reinforcement: lessons that were live during a
                          good run gain score, during a bad run lose it. Score
                          decides what makes it into the system prompt, and a
                          lesson that keeps losing retires itself.

Everything the model writes here goes through the same syntax gate and git
commit as any other self-modification, so a bad lesson is revertible.
"""

from __future__ import annotations

import json

import memory
import selfmod
import skills
from config import MAX_LEARN_DEPTH, MODEL


REFLECT_SYSTEM = """You are FunkBot's learning loop, reviewing a transcript of your own run.

Return ONLY a JSON object:
{
  "facts":   [{"subject": "...", "body": "...", "kind": "preference|project|person|fact"}],
  "lessons": [{"trigger": "the situation, concretely", "lesson": "what to do next time",
               "evidence": "what in the transcript shows this"}],
  "skill":   {"name": "...", "description": "when to use it", "body": "markdown"} | null,
  "tool":    {"name": "...", "source": "a complete python function"} | null
}

Rules:
- A lesson must be actionable and specific. "Be more careful" is worthless; "when
  the user says 'just fix it', skip the explanation and push the diff" is a lesson.
- Only propose a skill when the same multi-step procedure has now come up more than
  once — a skill is a playbook, not a note.
- Only propose a tool when a capability was missing, not when an existing tool was
  used badly. The source must be a self-contained function with a docstring.
- Prefer zero lessons to filler. Empty lists are a valid answer."""


CONSOLIDATE_SYSTEM = """You are FunkBot's meta-learning pass, reviewing its own lessons.

Return ONLY JSON:
{
  "merge":   [{"keep": <id>, "absorb": [<id>, ...], "rewrite": "merged lesson text"}],
  "retire":  [<id>, ...],
  "promote": {"name": "...", "description": "...", "body": "markdown"} | null
}

- merge lessons that say the same thing in different words.
- retire lessons that are contradicted by newer ones, or that were situational and
  are now stale.
- promote a cluster of related lessons into a single skill when three or more of them
  describe one recurring procedure. The skill body must fold in what those lessons say.
- Empty everything is a valid answer. Do not invent lessons here; only reorganize."""


def _client():
    from anthropic import Anthropic
    return Anthropic()


def _ask_json(system: str, user: str, effort: str = "high") -> dict:
    client = _client()
    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()

    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}


# --------------------------------------------------------------------- loop 1

def reflect(session_id: str) -> str:
    """Learn from one finished session."""
    with memory.db() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,)).fetchall()
        runs = c.execute(
            "SELECT tool, ok, ms FROM tool_runs WHERE session_id = ? ORDER BY id",
            (session_id,)).fetchall()
    if not rows:
        return "nothing to reflect on"

    transcript = "\n".join(f"[{r['role']}] {r['content'][:4000]}" for r in rows)
    tool_log = ", ".join(f"{r['tool']}{'' if r['ok'] else '(FAILED)'}" for r in runs)
    out = _ask_json(
        REFLECT_SYSTEM,
        f"TRANSCRIPT:\n{transcript}\n\nTOOL CALLS: {tool_log or 'none'}\n\n"
        f"EXISTING LESSONS:\n{memory.memory_prompt()}",
    )

    notes = []
    for f in out.get("facts") or []:
        memory.remember(f["subject"], f["body"], f.get("kind", "fact"), source="reflection")
        notes.append(f"fact: {f['subject']}")
    for l in out.get("lessons") or []:
        memory.add_lesson(l["trigger"], l["lesson"], l.get("evidence", ""))
        notes.append(f"lesson: {l['lesson'][:60]}")
    if out.get("skill"):
        s = out["skill"]
        notes.append(skills.write_skill(s["name"], s["description"], s["body"]))
    if out.get("tool"):
        t = out["tool"]
        notes.append(selfmod.add_own_tool(t["name"], t["source"]).splitlines()[0])

    if notes:
        selfmod.commit_self(f"learned from session {session_id}")
    return "; ".join(notes) or "nothing new learned"


# --------------------------------------------------------------------- loop 2

def consolidate(depth: int = 0) -> str:
    """Recursive step: learn from the lessons themselves."""
    if depth >= MAX_LEARN_DEPTH:
        return f"depth limit {MAX_LEARN_DEPTH} reached"

    lessons = memory.active_lessons(limit=200)
    if len(lessons) < 5:
        return "not enough lessons to consolidate"

    listing = "\n".join(
        f"[{l['id']}] (depth {l['depth']}, score {l['score']:.1f}) "
        f"when {l['trigger']} -> {l['lesson']}" for l in lessons)
    out = _ask_json(CONSOLIDATE_SYSTEM, listing)

    changed = []
    with memory.db() as c:
        for m in out.get("merge") or []:
            c.execute("UPDATE lessons SET lesson = ?, depth = ? WHERE id = ?",
                      (m["rewrite"], depth + 1, m["keep"]))
            for absorbed in m.get("absorb", []):
                c.execute("UPDATE lessons SET retired = 1 WHERE id = ?", (absorbed,))
            changed.append(f"merged {len(m.get('absorb', []))} into #{m['keep']}")
        for lid in out.get("retire") or []:
            c.execute("UPDATE lessons SET retired = 1 WHERE id = ?", (lid,))
            changed.append(f"retired #{lid}")

    if out.get("promote"):
        p = out["promote"]
        changed.append(skills.write_skill(p["name"], p["description"], p["body"]))

    if changed:
        selfmod.commit_self(f"consolidated lessons (depth {depth + 1})")
        # Recurse: the merged set may itself contain a new pattern.
        deeper = consolidate(depth + 1)
        changed.append(f"depth {depth + 1}: {deeper}")
    return "; ".join(changed) or "nothing to consolidate"


# --------------------------------------------------------------------- loop 3

def score_outcome(session_id: str, good: bool) -> str:
    """Reinforce or penalize the lessons that were live during a session."""
    delta = 1.0 if good else -1.0
    ids = [l["id"] for l in memory.active_lessons()]
    for lid in ids:
        memory.score_lesson(lid, delta)
    return f"scored {len(ids)} lessons {delta:+.0f}"


def learn(session_id: str, good: bool | None = None) -> str:
    """Full pass: reflect, score, then recursively consolidate."""
    parts = [reflect(session_id)]
    if good is not None:
        parts.append(score_outcome(session_id, good))
    parts.append(consolidate())
    return " | ".join(parts)
