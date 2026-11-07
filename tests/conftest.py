import pytest
from fastapi.testclient import TestClient

from app import config, main


class FakeMemory:
    """Records what Acorn retains so tests can assert on memory behaviour without a Hindsight server."""
    def __init__(self):
        self.retained: list[dict] = []
        self.reflections: list[tuple[str, str | None]] = []

    def ensure_bank(self): pass
    def retain(self, content, *, context, timestamp=None, tags=(), document_id=None):
        self.retained.append({"content": content, "context": context, "timestamp": timestamp, "tags": list(tags), "document_id": document_id})
    def retain_many(self, items): self.retained.extend(items)
    def recall(self, query, limit=12): return [{"id": "1", "text": "fact", "type": "world", "when": None, "tags": []}]
    structured = {"prediction": "ignore", "confidence": 82, "reason": "you ignore these"}

    def reflect(self, query, context=None, schema=None, budget=None):
        self.reflections.append((query, context))
        out = {"text": "reflected", "facts": [{"id": "1", "text": "fact", "type": "experience", "when": None, "tags": []}]}
        if schema:
            out["structured"] = self.structured
        return out
    def reset(self): self.retained.clear()


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return FakeMemory()


@pytest.fixture
def client(mem):
    main.app.dependency_overrides[main.get_memory] = lambda: mem
    main.app.dependency_overrides[main.get_pager_memory] = lambda: mem
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
