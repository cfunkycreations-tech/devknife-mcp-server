---
name: self-improvement
description: Use when you notice yourself repeating work, hitting the same failure twice, or missing a capability. Turns a rough edge into a permanent fix in your own code.
---

# Improving yourself

Trigger this the moment you think "I've done this before" or "I wish I could X".

1. **Name the gap precisely.** Missing capability, or existing tool used badly?
   Only the first justifies new code.
2. **Check you don't already have it** — `search_own_code` and `load_skill` first.
   Duplicated tools are worse than none.
3. **Missing capability → new tool.** Write one self-contained function with a
   docstring, add it with `add_own_tool`, then call it once on a real input.
   If it errors, fix it in the same turn or `rollback`.
4. **Repeated procedure → new skill.** `write_skill` with a description that
   names the *trigger situation*, not the topic — you only see the description
   when deciding whether to load it.
5. **Wrong behavior → a lesson.** `record_lesson` with a concrete trigger. Bad:
   "be careful with files". Good: "when asked to edit a file over 1000 lines,
   read the target range first instead of the whole file".
6. **Commit.** `commit_self` with what changed and why. Every self-edit is
   revertible or it doesn't ship.

Never make a change you cannot test in the same turn.
