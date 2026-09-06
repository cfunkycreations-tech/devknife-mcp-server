"""Skills: markdown playbooks FunkBot loads on demand (and writes for itself).

A skill is a directory under skills/ containing SKILL.md with frontmatter:

    ---
    name: invoice-audit
    description: Use when the user asks to check an invoice against the contract.
    ---
    <the actual instructions>

Only name+description go in the system prompt (cheap). The body loads when the
skill is invoked — progressive disclosure, the same shape Claude Code uses.
"""

from __future__ import annotations

import re

from config import SKILLS_DIR


def _parse(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = dict(re.findall(r"^([a-zA-Z_]+):\s*(.+)$", m.group(1), re.M))
    return meta, m.group(2)


def catalog() -> list[dict]:
    out = []
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta, _ = _parse(path.read_text(encoding="utf-8"))
        out.append({"name": meta.get("name", path.parent.name),
                    "description": meta.get("description", ""),
                    "path": str(path)})
    return out


def load(name: str) -> str:
    for s in catalog():
        if s["name"] == name:
            _, body = _parse(open(s["path"], encoding="utf-8").read())
            folder = SKILLS_DIR / name
            extras = sorted(p.name for p in folder.glob("*") if p.name != "SKILL.md")
            note = f"\n\nBundled files in skills/{name}/: {', '.join(extras)}" if extras else ""
            return body + note
    return f"no skill named {name}. Available: {[s['name'] for s in catalog()]}"


def write_skill(name: str, description: str, body: str) -> str:
    """FunkBot writing a new skill for itself."""
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower())
    d = SKILLS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body.strip()}\n",
        encoding="utf-8")
    return f"skill '{name}' written to {d}/SKILL.md"


def prompt_block() -> str:
    items = catalog()
    if not items:
        return ""
    lines = ["Skills available (call load_skill with the name for full instructions):"]
    lines += [f"- {s['name']}: {s['description']}" for s in items]
    return "\n".join(lines)
