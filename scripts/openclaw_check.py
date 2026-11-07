"""Read-only check that the bank an OpenClaw agent points at is reachable and populated.
Usage: .venv/bin/python -m scripts.openclaw_check [bank_id]      (default: acorn-demo-pager)"""
import sys

from hindsight_client import Hindsight

from app import config

bank = sys.argv[1] if len(sys.argv) > 1 else "acorn-demo-pager"
c = Hindsight(base_url=config.HINDSIGHT_BASE_URL, api_key=config.HINDSIGHT_API_KEY)
print("endpoint:", config.HINDSIGHT_BASE_URL, "| bank:", bank)
mem = c.list_memories(bank, limit=5)
print("memories visible:", getattr(mem, "total", None) or len(mem.items or []))
for m in (mem.items or [])[:3]:
    print("  -", (getattr(m, "text", "") or "")[:110])
probe = "payments webhook 504s from the provider, should I roll back?"
res = c.recall(bank, probe, max_tokens=1024, budget="low")
print(f"recall probe: {probe!r}")
for r in (res.results or [])[:3]:
    print("  >", r.text[:130])
print("OK: an OpenClaw agent using this bank will recall the same memories." if res.results else "No recall hits: load the history first (/pager -> LOAD INCIDENT HISTORY).")
