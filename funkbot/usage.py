"""Token and cost telemetry. What every run actually cost, and whether the
cache is doing its job.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import memory

# $ per million tokens, first-party API rates.
PRICES = {
    "claude-opus-5":     {"in": 5.00, "out": 25.00},
    "claude-fable-5-1":  {"in": 10.00, "out": 50.00},
    "claude-sonnet-5":   {"in": 2.00, "out": 10.00},
    "claude-haiku-4-5":  {"in": 1.00, "out": 5.00},
}
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    requests: int = 0
    tool_calls: int = 0
    started: float = field(default_factory=time.time)

    def add(self, u) -> None:
        """Accepts a dict (local backend) or an SDK usage object (cloud)."""
        get = u.get if isinstance(u, dict) else lambda k, d=0: getattr(u, k, d) or d
        self.requests += 1
        self.input_tokens += get("input_tokens", 0) or 0
        self.output_tokens += get("output_tokens", 0) or 0
        self.cache_read += get("cache_read", 0) or get("cache_read_input_tokens", 0) or 0
        self.cache_write += get("cache_write", 0) or \
            get("cache_creation_input_tokens", 0) or 0

    @property
    def cost(self) -> float:
        """Local models cost nothing to run — only cloud backends are priced."""
        p = PRICES.get(self.model)
        if p is None:
            return 0.0
        return (
            self.input_tokens * p["in"]
            + self.cache_write * p["in"] * CACHE_WRITE_MULT
            + self.cache_read * p["in"] * CACHE_READ_MULT
            + self.output_tokens * p["out"]
        ) / 1_000_000

    @property
    def cache_hit_rate(self) -> float:
        billed = self.input_tokens + self.cache_read
        return self.cache_read / billed if billed else 0.0

    def snapshot(self) -> dict:
        return {
            "model": self.model, "requests": self.requests,
            "tool_calls": self.tool_calls,
            "input": self.input_tokens, "output": self.output_tokens,
            "cache_read": self.cache_read, "cache_write": self.cache_write,
            "cache_hit_rate": round(self.cache_hit_rate, 3),
            "cost_usd": round(self.cost, 4),
            "elapsed_s": round(time.time() - self.started, 1),
        }

    def persist(self, session_id: str) -> None:
        snap = self.snapshot()
        with memory.db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS usage (
                session_id TEXT PRIMARY KEY, ts REAL, model TEXT, requests INTEGER,
                tool_calls INTEGER, input INTEGER, output INTEGER, cache_read INTEGER,
                cache_write INTEGER, cost_usd REAL)""")
            c.execute("""INSERT OR REPLACE INTO usage VALUES (?,?,?,?,?,?,?,?,?,?)""",
                      (session_id, time.time(), snap["model"], snap["requests"],
                       snap["tool_calls"], snap["input"], snap["output"],
                       snap["cache_read"], snap["cache_write"], snap["cost_usd"]))


def totals() -> dict:
    with memory.db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS usage (
            session_id TEXT PRIMARY KEY, ts REAL, model TEXT, requests INTEGER,
            tool_calls INTEGER, input INTEGER, output INTEGER, cache_read INTEGER,
            cache_write INTEGER, cost_usd REAL)""")
        row = c.execute(
            "SELECT COUNT(*) n, SUM(cost_usd) cost, SUM(input) inp, SUM(output) outp,"
            " SUM(cache_read) cr, SUM(tool_calls) tc FROM usage").fetchone()
    return {"sessions": row["n"] or 0, "cost_usd": round(row["cost"] or 0, 4),
            "input": row["inp"] or 0, "output": row["outp"] or 0,
            "cache_read": row["cr"] or 0, "tool_calls": row["tc"] or 0}
