from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, config, seed, store
from .memory import HindsightMemory, Memory

_mem: Memory | None = None


def get_memory() -> Memory:
    global _mem
    if _mem is None:
        _mem = HindsightMemory(config.ACORN_USER)
        _mem.ensure_bank()
    return _mem


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="Acorn", lifespan=lifespan)
USER = config.ACORN_USER


class SaveIn(BaseModel):
    kind: str = "other"
    title: str = ""
    text: str = Field(min_length=1, max_length=8000)
    why: str = ""


class ResolveIn(BaseModel):
    status: str
    note: str = ""


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@app.get("/api/items")
def items():
    return store.list_items(USER)


@app.post("/api/items")
def save_item(body: SaveIn, mem: Memory = Depends(get_memory)):
    return agent.save(mem, USER, body.kind, body.title, body.text, body.why)


@app.post("/api/items/{item_id}/resolve")
def resolve_item(item_id: str, body: ResolveIn, mem: Memory = Depends(get_memory)):
    if body.status not in ("acted", "ignored"):
        raise HTTPException(422, "status must be 'acted' or 'ignored'")
    item = agent.resolve(mem, USER, item_id, body.status, body.note)
    if not item:
        raise HTTPException(404, "no such item")
    return item


@app.get("/api/items/{item_id}/brief")
def brief(item_id: str, mem: Memory = Depends(get_memory)):
    res = agent.brief(mem, USER, item_id)
    if not res:
        raise HTTPException(404, "no such item")
    return res


@app.get("/api/today")
def today(mem: Memory = Depends(get_memory)):
    return agent.today(mem, USER)


@app.post("/api/ask")
def ask(body: AskIn, mem: Memory = Depends(get_memory)):
    return agent.ask(mem, body.question, USER)


@app.get("/api/recall")
def recall(q: str, mem: Memory = Depends(get_memory)):
    return mem.recall(q)


@app.post("/api/demo/load")
def load_demo(mem: Memory = Depends(get_memory)):
    return {"retained": seed.load(mem, USER)}


@app.get("/api/health")
def health():
    return {"ok": True, "user": USER, "hindsight": config.HINDSIGHT_BASE_URL}


_static = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=_static), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(_static, "index.html"), headers={"Cache-Control": "no-store"})
