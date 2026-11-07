"""Tiny JSON store for the saved items the UI lists. Hindsight holds the *memory*; this holds the *inbox*."""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()


def _path(user: str) -> str:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return os.path.join(config.DATA_DIR, f"items-{user}.json")


def _load(user: str) -> list[dict]:
    try:
        with open(_path(user)) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _dump(user: str, items: list[dict]) -> None:
    with open(_path(user), "w") as f:
        json.dump(items, f, indent=2)


def list_items(user: str) -> list[dict]:
    with _lock:
        return sorted(_load(user), key=lambda i: i["saved_at"], reverse=True)


def get(user: str, item_id: str) -> dict | None:
    return next((i for i in list_items(user) if i["id"] == item_id), None)


def add(user: str, kind: str, title: str, text: str, why: str = "", saved_at: str | None = None,
        status: str = "open", item_id: str | None = None) -> dict:
    item = {
        "id": item_id or uuid.uuid4().hex[:10],
        "kind": kind,
        "title": title,
        "text": text,
        "why": why,
        "saved_at": saved_at or datetime.now(timezone.utc).isoformat(),
        "status": status,  # open | acted | ignored
        "resolved_at": None,
    }
    with _lock:
        items = _load(user)
        items.append(item)
        _dump(user, items)
    return item


def resolve(user: str, item_id: str, status: str) -> dict | None:
    with _lock:
        items = _load(user)
        for i in items:
            if i["id"] == item_id:
                i["status"] = status
                i["resolved_at"] = datetime.now(timezone.utc).isoformat()
                _dump(user, items)
                return i
    return None


def clear(user: str) -> None:
    with _lock:
        _dump(user, [])
