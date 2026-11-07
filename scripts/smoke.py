"""Live check against Hindsight: create bank, retain, wait for recall, reflect. Run: .venv/bin/python -m scripts.smoke"""
import time

from app import config
from app.memory import HindsightMemory

print("endpoint:", config.HINDSIGHT_BASE_URL, "| key set:", bool(config.HINDSIGHT_API_KEY))
m = HindsightMemory("smoke")
m.ensure_bank(); print("bank ok")
m.retain('On Monday 02 November 2026, the user saved a job titled "Staff Eng". Reason: payments fit. Content: apply by 9 Nov.',
         context="a thing the user saved", tags=["save", "job"], document_id="save-t1")
print("retain ok")
r = []
for _ in range(18):
    r = m.recall("what job did the user save?")
    if r: break
    time.sleep(5)
print("recall:", r[:2])
print("reflect:", m.reflect("Which saved job should the user act on?"))
