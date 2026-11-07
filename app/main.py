from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, config, pager, seed, store
from .memory import HindsightMemory, Memory

_mem: Memory | None = None


def get_memory() -> Memory:
    global _mem
    if _mem is None:
        _mem = HindsightMemory(config.ACORN_USER)
        _mem.ensure_bank()
    return _mem


_pager_mem: Memory | None = None
PAGER_USER = pager.pager_user()


def get_pager_memory() -> Memory:
    global _pager_mem
    if _pager_mem is None:
        _pager_mem = HindsightMemory(PAGER_USER, mission=pager.PAGER_MISSION, retain_mission=pager.PAGER_RETAIN,
                                     reflect_mission=pager.PAGER_REFLECT)
        _pager_mem.ensure_bank()
    return _pager_mem


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


@app.post("/api/items/{item_id}/predict")
def predict(item_id: str, mem: Memory = Depends(get_memory)):
    item = store.get(USER, item_id)
    if not item:
        raise HTTPException(404, "no such item")
    if item["status"] != "open":
        raise HTTPException(409, "only open items can be predicted")
    res = agent.predict(mem, USER, item_id)
    if not res or not res.get("prediction"):
        raise HTTPException(502, "the ghost could not decide")
    return res


@app.get("/api/ghost")
def ghost():
    return agent.ghost_score(USER)


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


class IncidentIn(BaseModel):
    title: str = ""
    service: str = Field(min_length=1, max_length=80)
    severity: str = "sev2"
    text: str = Field(min_length=1, max_length=8000)


class ResolveIncidentIn(BaseModel):
    cause: str
    fix: str = ""
    minutes: int = Field(ge=1, le=100000)
    failed: str = ""
    suggestion_worked: bool | None = None


@app.get("/api/pager/items")
def pager_items():
    return store.list_items(PAGER_USER)


@app.post("/api/pager/items")
def pager_open(body: IncidentIn, mem: Memory = Depends(get_pager_memory)):
    return pager.open_incident(mem, PAGER_USER, body.title, body.service, body.severity, body.text)


@app.post("/api/pager/items/{item_id}/triage")
def pager_triage(item_id: str, mem: Memory = Depends(get_pager_memory)):
    item = store.get(PAGER_USER, item_id)
    if not item:
        raise HTTPException(404, "no such incident")
    if item["status"] != "open":
        raise HTTPException(409, "incident already resolved")
    res = pager.triage(mem, PAGER_USER, item_id)
    if not res or not res.get("triage"):
        raise HTTPException(502, "triage could not decide")
    return res


@app.post("/api/pager/items/{item_id}/resolve")
def pager_resolve(item_id: str, body: ResolveIncidentIn, mem: Memory = Depends(get_pager_memory)):
    if body.cause not in pager.CAUSES:
        raise HTTPException(422, "unknown cause")
    item = pager.resolve(mem, PAGER_USER, item_id, body.cause, body.fix, body.minutes, body.failed, body.suggestion_worked)
    if not item:
        raise HTTPException(404, "no such incident")
    return item


@app.get("/api/pager/score")
def pager_score():
    return pager.score(PAGER_USER)


@app.get("/api/pager/causes")
def pager_causes():
    return pager.CAUSES


@app.post("/api/pager/ask")
def pager_ask(body: AskIn, mem: Memory = Depends(get_pager_memory)):
    return pager.ask(mem, PAGER_USER, body.question)


@app.post("/api/pager/demo/load")
def pager_load(mem: Memory = Depends(get_pager_memory)):
    return {"retained": pager.load_history(mem, PAGER_USER)}


_static = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=_static), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(_static, "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/pager")
def pager_page():
    return FileResponse(os.path.join(_static, "pager.html"), headers={"Cache-Control": "no-store"})
