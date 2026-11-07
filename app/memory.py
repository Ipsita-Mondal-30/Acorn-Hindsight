"""The Hindsight memory layer. Everything Acorn remembers goes through retain(); everything it knows comes back
through recall() / reflect(). One memory bank per user."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Protocol

from hindsight_client import Hindsight

from . import config

BANK_MISSION = (
    "Acorn is one person's follow-through memory. Remember what they save (links, notes, screenshots, voice notes), "
    "why they saved it, deadlines, and above all what they actually DID with it: which kinds of saves they act on, "
    "how quickly, which they ignore, and on what days or conditions. Use that behaviour to judge what deserves "
    "their attention now."
)

RETAIN_MISSION = (
    "Extract: the saved item (what it is, deadlines, people, companies, amounts), the user's stated reason for saving, "
    "and every outcome (acted on, ignored, snoozed) with how many days it took. Outcomes are the most important facts."
)


REFLECT_MISSION = "Answer as a calm, specific personal assistant. Cite the user's own history. Never invent saves."


class Memory(Protocol):
    def ensure_bank(self) -> None: ...
    def retain(self, content: str, *, context: str, timestamp: datetime | None, tags: list[str], document_id: str | None) -> None: ...
    def retain_many(self, items: list[dict[str, Any]]) -> None: ...
    def recall(self, query: str, limit: int = 12) -> list[dict]: ...
    def reflect(self, query: str, context: str | None = None, schema: dict | None = None, budget: str = "mid") -> dict: ...
    def reset(self) -> None: ...


def bank_id(user: str) -> str:
    return f"acorn-{user}"


def _fact(r: Any) -> dict:
    return {
        "id": r.id,
        "text": r.text,
        "type": r.type,
        "when": (r.occurred_start or r.mentioned_at or None),
        "tags": r.tags or [],
    }


class HindsightMemory:
    def __init__(self, user: str, client: Hindsight | None = None, mission: str = BANK_MISSION,
                 retain_mission: str = RETAIN_MISSION, reflect_mission: str = REFLECT_MISSION):
        self.bank = bank_id(user)
        self.missions = (mission, retain_mission, reflect_mission)
        self.client = client or Hindsight(base_url=config.HINDSIGHT_BASE_URL, api_key=config.HINDSIGHT_API_KEY)
        # The client keeps an aiohttp session bound to one thread's event loop. FastAPI serves requests on many
        # threads, so every Hindsight call is funnelled through one worker thread.
        self._ex = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hindsight")

    def _call(self, fn, *args, **kwargs):
        return self._ex.submit(fn, *args, **kwargs).result()

    def ensure_bank(self) -> None:
        # create_bank is an upsert, so this is safe to call on every start
        self._call(self.client.create_bank,
            self.bank,
            name="Acorn",
            mission=self.missions[0],
            retain_mission=self.missions[1],
            reflect_mission=self.missions[2],
            enable_observations=True,
        )

    def retain(self, content, *, context, timestamp=None, tags=(), document_id=None) -> None:
        self._call(self.client.retain, self.bank, content, context=context,
                   timestamp=timestamp or datetime.now(timezone.utc), tags=list(tags), document_id=document_id)

    def retain_many(self, items: list[dict[str, Any]]) -> None:
        self._call(self.client.retain_batch, self.bank, items)

    def recall(self, query: str, limit: int = 12) -> list[dict]:
        res = self._call(self.client.recall, self.bank, query, max_tokens=2048, budget="mid")
        return [_fact(r) for r in (res.results or [])][:limit]

    def reflect(self, query: str, context: str | None = None, schema: dict | None = None, budget: str = "mid") -> dict:
        res = self._call(self.client.reflect, self.bank, query, budget=budget, context=context,
                         include_facts=True, response_schema=schema)
        out = {"text": res.text, "facts": [_fact(f) for f in _based_on(res)]}
        if schema:
            out["structured"] = getattr(res, "structured_output", None) or _json_in(res.text)
        return out

    def reset(self) -> None:
        try:
            self._call(self.client.delete_bank, self.bank)
        except Exception:
            pass
        self.ensure_bank()


def _json_in(text: str | None) -> dict | None:
    import json, re
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


def _based_on(res: Any) -> list[Any]:
    b = getattr(res, "based_on", None)
    if b is None:
        return []
    if isinstance(b, list):
        return b
    # newer clients group facts by type
    out: list[Any] = []
    for v in (b.model_dump().values() if hasattr(b, "model_dump") else []):
        out.extend(v or [])
    return [_Dict(x) if isinstance(x, dict) else x for x in out]


class _Dict:
    def __init__(self, d: dict):
        self.id = d.get("id")
        self.text = d.get("text")
        self.type = d.get("type")
        self.occurred_start = d.get("occurred_start")
        self.mentioned_at = d.get("mentioned_at")
        self.tags = d.get("tags")
