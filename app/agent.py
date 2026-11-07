"""Acorn's behaviour. Memory is the product: every save and every outcome is retained; every suggestion is reflected
from that history."""
from __future__ import annotations

from datetime import datetime, timezone

from . import llm, store
from .memory import Memory

KINDS = ("job", "recipe", "article", "product", "idea", "document", "other")


def _day(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%A %d %B %Y")


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def save_content(item: dict) -> str:
    why = item["why"].strip() or "none given"
    return (f"On {_day(item['saved_at'])}, the user saved a {item['kind']} titled \"{item['title']}\". "
            f"Reason they gave for saving it: {why}. Content: {item['text']}")


def outcome_content(item: dict, status: str, resolved_at: str, note: str = "") -> str:
    days = max(0, (_parse(resolved_at) - _parse(item["saved_at"])).days)
    verb = "acted on" if status == "acted" else "ignored"
    tail = f" Note: {note}" if note else ""
    return (f"On {_day(resolved_at)}, the user {verb} the {item['kind']} they saved on {_day(item['saved_at'])} "
            f"titled \"{item['title']}\", {days} days after saving it.{tail}")


def save(mem: Memory, user: str, kind: str, title: str, text: str, why: str = "") -> dict:
    kind = kind if kind in KINDS else "other"
    item = store.add(user, kind, title.strip() or text[:60], text.strip(), why.strip())
    mem.retain(save_content(item), context="a thing the user saved to follow up on later",
               timestamp=_parse(item["saved_at"]), tags=["save", kind], document_id=f"save-{item['id']}")
    return item


def resolve(mem: Memory, user: str, item_id: str, status: str, note: str = "") -> dict | None:
    if status not in ("acted", "ignored"):
        raise ValueError("status must be 'acted' or 'ignored'")
    item = store.get(user, item_id)
    if not item or item["status"] != "open":
        return item
    done = store.resolve(user, item_id, status)
    mem.retain(outcome_content(item, status, done["resolved_at"], note),
               context="what the user actually did with something they saved; the strongest signal of what they care about",
               timestamp=_parse(done["resolved_at"]), tags=["outcome", item["kind"], status], document_id=f"outcome-{item_id}")
    pred = item.get("prediction")
    if pred:  # grade the ghost and teach memory from its own miss or hit
        correct = (pred["label"] == "act") == (status == "acted")
        done = store.update(user, item_id, correct=correct)
        verdict = "was right" if correct else "was wrong"
        mem.retain(f"Acorn predicted the user would {pred['label']} the {item['kind']} \"{item['title']}\" "
                   f"({pred['confidence']}% sure, reason: {pred['reason']}). The user actually {'acted on' if status == 'acted' else 'ignored'} it, "
                   f"so the prediction {verdict}.",
                   context="Acorn's own prediction accuracy; learn which signals predict this user's behaviour",
                   timestamp=_parse(done["resolved_at"]), tags=["prediction", "right" if correct else "wrong"],
                   document_id=f"prediction-{item_id}")
    return done


def brief(mem: Memory, user: str, item_id: str) -> dict | None:
    item = store.get(user, item_id)
    if not item:
        return None
    q = (f"The user saved a {item['kind']} titled \"{item['title']}\" ({item['text'][:300]}). "
         "Based on their history of saves and especially what they actually acted on or ignored: "
         "(1) what did they probably save it for, (2) which earlier saves relate to it, "
         "(3) give ONE concrete next step and when to do it. Be specific, under 90 words.")
    return {"item": item, **mem.reflect(q, context=f"Today is {datetime.now(timezone.utc):%A %d %B %Y}.\n" + state_context(user))}


def today(mem: Memory, user: str) -> dict:
    open_items = [i for i in store.list_items(user) if i["status"] == "open"]
    if not open_items:
        return {"text": "Nothing open. Save something and I'll start remembering it.", "facts": [], "open": []}
    listing = "\n".join(f"- [{i['kind']}] {i['title']} (saved {_day(i['saved_at'])}; id {i['id']})" for i in open_items)
    q = ("Which of these open saves deserve the user's attention TODAY, in priority order, and why? "
         "Rules: (1) anything with a stated deadline within the next 3 days goes FIRST, and look up each item's "
         "deadline in memory; (2) then rank by the user's track record: which kinds of saves they act on, how quickly, "
         "and which they habitually ignore; (3) say plainly which to drop. Max 120 words.\n\n" + listing)
    res = mem.reflect(q, context=f"Today is {datetime.now(timezone.utc):%A %d %B %Y}.\n" + state_context(user))
    return {**res, "open": open_items}


def state_context(user: str) -> str:
    """Authoritative item statuses from the app. Memory supplies history and patterns; this stops it mislabelling status."""
    by: dict[str, list[str]] = {"open": [], "acted": [], "ignored": []}
    for i in store.list_items(user):
        by[i["status"]].append(f"{i['title']} ({i['kind']})")
    lines = [f"{k.upper()}: " + ("; ".join(v[:25]) if v else "none") for k, v in by.items()]
    return ("Authoritative current status of every saved item (trust this over any inferred status; an item the user "
            "ACTED on is done and is not a pending task):\n" + "\n".join(lines))


def ask(mem: Memory, question: str, user: str | None = None) -> dict:
    """The money shot: same question, with Hindsight memory and without."""
    ctx = f"Today is {datetime.now(timezone.utc):%A %d %B %Y}."
    if user:
        ctx += "\n" + state_context(user)
    with_mem = mem.reflect(question + "\n\n(Answer in under 100 words. Lead with the verdict, then cite the user's own history.)", context=ctx)
    return {"with_memory": with_mem, "without_memory": llm.answer_without_memory(question)}


GHOST_SCHEMA = {
    "type": "object",
    "properties": {
        "prediction": {"type": "string", "enum": ["act", "ignore"]},
        "confidence": {"type": "integer", "minimum": 50, "maximum": 99},
        "reason": {"type": "string"},
    },
    "required": ["prediction", "confidence", "reason"],
}


def predict(mem: Memory, user: str, item_id: str, force: bool = False) -> dict | None:
    """Ghost Prediction: before the user acts, guess act/ignore from their own history, and remember the guess."""
    item = store.get(user, item_id)
    if not item or item["status"] != "open":
        return item
    if item.get("prediction") and not force:
        return item
    q = (f"Predict whether the user will ACT on or IGNORE this saved {item['kind']}: \"{item['title']}\" "
         f"({item['text'][:300]}). Stated reason for saving: {item['why'] or 'none'}. "
         "Base it on how this user treated similar saves (same kind, deadlines, how fast they acted, "
         "what they ignored) and on any past Acorn predictions that were wrong. "
         "Give prediction, an honest confidence 50-99, and a one-sentence reason citing their history.")
    res = mem.reflect(q, context=f"Today is {datetime.now(timezone.utc):%A %d %B %Y}.", schema=GHOST_SCHEMA, budget="low")
    out = res.get("structured") or {}
    label = out.get("prediction")
    if label not in ("act", "ignore"):
        return None
    conf = max(50, min(99, int(out.get("confidence") or 60)))
    pred = {"label": label, "confidence": conf, "reason": str(out.get("reason", ""))[:300],
            "made_at": datetime.now(timezone.utc).isoformat()}
    return store.update(user, item_id, prediction=pred, correct=None)


def ghost_score(user: str) -> dict:
    graded = [i for i in store.list_items(user) if i.get("prediction") and i.get("correct") is not None]
    right = sum(1 for i in graded if i["correct"])
    recent = [{"title": i["title"], "predicted": i["prediction"]["label"], "confidence": i["prediction"]["confidence"],
               "correct": i["correct"]} for i in sorted(graded, key=lambda i: i["resolved_at"] or "", reverse=True)[:5]]
    return {"graded": len(graded), "right": right,
            "accuracy": round(100 * right / len(graded)) if graded else None,
            "pending": sum(1 for i in store.list_items(user) if i.get("prediction") and i["status"] == "open"),
            "recent": recent}
