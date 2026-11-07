"""Pager Memory: an incident-response lens on the same engine as Acorn.

Retain every incident and its post-mortem (cause, the fix that worked, what was tried and did NOT work, time to
resolve). When a new incident opens, reflect over that history to triage it, then grade the triage when the real
root cause is recorded, and retain the hit or miss so the next triage is better."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, llm, store
from .memory import Memory

CAUSES = {
    "bad_deploy": "Bad deploy",
    "config_change": "Config change",
    "capacity": "Capacity / load",
    "dependency_outage": "Dependency outage",
    "data_or_schema": "Data / schema / DB",
    "network": "Network / DNS / certs",
    "unknown": "Unknown",
}
SEVERITIES = ("sev1", "sev2", "sev3")

PAGER_MISSION = (
    "Pager Memory is one engineering team's incident memory. Remember every incident: service, severity, symptoms "
    "and log signatures, the ROOT CAUSE, the fix that worked, steps that were tried and did NOT work, the runbook "
    "used, and time to resolve. Recurring patterns matter most: which services fail in which way, which fixes work "
    "for which cause, and which actions wasted time.")
PAGER_RETAIN = (
    "Extract per incident: id, service, severity, log signatures, root cause category, the fix that worked, failed "
    "attempts, runbook id, minutes to resolve, and whether Acorn's triage prediction was right or wrong.")
PAGER_REFLECT = (
    "Answer like a calm senior SRE mid-incident: short, specific, cite incident ids (INC-###) and runbook ids. "
    "Say what worked before AND what wasted time. Never invent incidents or runbooks.")
ROLE = "a generic SRE assistant with no access to this team's incident history"


def pager_user() -> str:
    return f"{config.ACORN_USER}-pager"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%A %d %B %Y %H:%M UTC")


def opened_content(i: dict) -> str:
    return (f"Incident {i['id']} ({i['severity']}) on service {i['service']}, opened {_day(i['saved_at'])}: "
            f"{i['title']}. Symptoms and logs: {i['text']}")


def postmortem_content(i: dict) -> str:
    r = i["resolution"]
    failed = f" Tried and did NOT work: {r['failed']}." if r.get("failed") else ""
    return (f"Post-mortem for {i['id']} ({i['severity']}, service {i['service']}): {i['title']}. "
            f"Symptoms and logs: {i['text']} Root cause category: {CAUSES[r['cause']]}. "
            f"Fix that worked: {r['fix']}.{failed} Resolved in {r['minutes']} minutes.")


def open_incident(mem: Memory, user: str, title: str, service: str, severity: str, text: str) -> dict:
    severity = severity if severity in SEVERITIES else "sev2"
    n = 300 + len(store.list_items(user))
    item = store.add(user, "incident", title.strip() or text[:60], text.strip(), why=service.strip(), item_id=f"INC-{n}")
    item = store.update(user, item["id"], service=service.strip() or "unknown-service", severity=severity)
    mem.retain(opened_content(item), context="a production incident that just opened",
               timestamp=_now(), tags=["incident", "opened", item["service"]], document_id=f"opened-{item['id']}")
    return item


TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {"type": "string", "enum": list(CAUSES)},
        "confidence": {"type": "integer", "minimum": 40, "maximum": 95},
        "first_step": {"type": "string"},
        "avoid": {"type": "string"},
        "similar": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["cause", "confidence", "first_step", "avoid", "similar", "reason"],
}


def triage(mem: Memory, user: str, item_id: str, force: bool = False) -> dict | None:
    item = store.get(user, item_id)
    if not item or item["status"] != "open":
        return item
    if item.get("triage") and not force:
        return item
    q = (f"Triage this live incident using ONLY this team's incident history.\n"
         f"{item['id']} ({item['severity']}) on {item['service']}: {item['title']}.\nSymptoms and logs: {item['text']}\n\n"
         "Give: cause (the most likely root cause category); confidence 40-95, CALIBRATED: 90+ only if 3 or more past incidents "
         "match both symptoms and log signature; 70-85 if 1-2 match; 50-65 if matches are partial or the history disagrees; "
         "first_step (ONE concrete action that worked on the most similar past incident, with its runbook id if any); "
         "avoid (a step that wasted time on similar incidents, or empty if none); similar (1-3 past incident ids, each "
         "with a few words on why it matches); reason (one sentence). Also weigh any past Acorn triage that was wrong.")
    res = mem.reflect(q, context=f"Now is {_now():%A %d %B %Y %H:%M} UTC.", schema=TRIAGE_SCHEMA, budget="low")
    out = res.get("structured") or {}
    if out.get("cause") not in CAUSES:
        return None
    t = {"cause": out["cause"], "confidence": max(40, min(95, int(out.get("confidence") or 60))),
         "first_step": str(out.get("first_step", ""))[:400], "avoid": str(out.get("avoid", ""))[:300],
         "similar": [str(x)[:140] for x in (out.get("similar") or [])][:3],
         "reason": str(out.get("reason", ""))[:300], "made_at": _now().isoformat(),
         "facts": res.get("facts", [])[:6]}
    return store.update(user, item_id, triage=t, correct=None)


def resolve(mem: Memory, user: str, item_id: str, cause: str, fix: str, minutes: int,
            failed: str = "", suggestion_worked: bool | None = None) -> dict | None:
    if cause not in CAUSES:
        raise ValueError("unknown cause")
    item = store.get(user, item_id)
    if not item or item["status"] != "open":
        return item
    now = _now().isoformat()
    res = {"cause": cause, "fix": fix.strip() or "not recorded", "failed": failed.strip(),
           "minutes": max(1, int(minutes)), "suggestion_worked": suggestion_worked}
    item = store.update(user, item_id, status="resolved", resolved_at=now, resolution=res)
    mem.retain(postmortem_content(item), context="a resolved incident post-mortem: the most valuable memory for future triage",
               timestamp=_now(), tags=["incident", "postmortem", cause, item["service"]], document_id=f"postmortem-{item_id}")
    t = item.get("triage")
    if t:
        correct = t["cause"] == cause
        item = store.update(user, item_id, correct=correct)
        step = ("" if suggestion_worked is None else
                f" Its suggested first step ({t['first_step'][:120]}) {'worked' if suggestion_worked else 'did not work'}.")
        mem.retain(f"Acorn triaged {item_id} on {item['service']} as {CAUSES[t['cause']]} ({t['confidence']}% sure). "
                   f"The actual root cause was {CAUSES[cause]}, so the triage was {'RIGHT' if correct else 'WRONG'}.{step}",
                   context="Acorn's own triage accuracy; learn which log signatures point to which causes",
                   timestamp=_now(), tags=["triage", "right" if correct else "wrong"], document_id=f"triage-{item_id}")
    return item


def score(user: str) -> dict:
    items = store.list_items(user)
    graded = [i for i in items if i.get("triage") and i.get("correct") is not None]
    right = sum(1 for i in graded if i["correct"])
    worked = [i for i in graded if i["resolution"].get("suggestion_worked") is not None]
    return {"graded": len(graded), "right": right,
            "accuracy": round(100 * right / len(graded)) if graded else None,
            "step_worked": sum(1 for i in worked if i["resolution"]["suggestion_worked"]), "step_graded": len(worked),
            "open": sum(1 for i in items if i["status"] == "open"),
            "resolved": sum(1 for i in items if i["status"] == "resolved")}


def ask(mem: Memory, user: str, question: str) -> dict:
    lines = "\n".join(f"- {i['id']} {i['status']} {i['service']}: {i['title']}" for i in store.list_items(user)[:40])
    ctx = f"Now is {_now():%A %d %B %Y %H:%M} UTC.\nIncident list (authoritative status):\n{lines}"
    with_mem = mem.reflect(question + "\n\n(Under 100 words. Verdict first, then cite incident ids.)", context=ctx)
    return {"with_memory": with_mem, "without_memory": llm.answer_without_memory(question, ROLE)}


# ------------------------------------------------------------------ demo history
# (days_ago, id, sev, service, title, logs, cause, fix, failed, minutes)
HISTORY = [
    (58, "INC-201", "sev2", "checkout-api", "p99 latency 3.8s after v2.31 deploy",
     "deploy v2.31 at 14:10; WARN db.pool wait_time=2.9s; checkout p99 3.8s; new cart code issues N+1 query to products",
     "bad_deploy", "Rolled back to v2.30 with `kubectl rollout undo deploy/checkout-api` (runbook RB-12); latency recovered in 2 min",
     "Scaling pods from 3 to 9 changed nothing", 12),
    (52, "INC-202", "sev1", "redis-sessions", "Users logged out, evicted_keys 40k/s",
     "used_memory 7.9GB maxmemory 8GB policy allkeys-lru; evicted_keys 40000/s; hit rate 38%; marketing email campaign sent 13:00",
     "capacity", "Raised maxmemory to 16GB and moved sessions to a dedicated cluster (runbook RB-07)",
     "Restarting redis wiped every session and made the outage worse", 34),
    (47, "INC-203", "sev2", "payments-api", "Webhook 504s, provider queue growing",
     "upstream connect error: provider.example 503; webhook retries 4/5; queue depth 12k; provider status page degraded",
     "dependency_outage", "Enabled the fallback retry queue (RB-19) and waited for the provider to recover; no rollback needed",
     "Rolled back payments-api v1.88, no effect, wasted 20 minutes", 55),
    (41, "INC-204", "sev2", "orders-db", "Connection pool exhausted after nightly migration",
     "FATAL remaining connection slots are reserved; 212 sessions idle in transaction; backfill job holds long transaction",
     "data_or_schema", "Killed idle-in-transaction sessions, set idle_in_transaction_session_timeout=30s, reran backfill in batches (RB-23)",
     "Raising max_connections only delayed the failure by 10 minutes", 28),
    (36, "INC-205", "sev3", "auth-service", "Login 5xx for 3% of users, TLS handshake errors",
     "x509: certificate has expired or is not yet valid; only clients pinned to the old intermediate fail",
     "network", "Renewed the intermediate certificate and added an expiry alert at 21 days (RB-31)", "", 9),
    (33, "INC-206", "sev2", "checkout-api", "Error rate 6% right after v2.34 deploy",
     "deploy v2.34 at 09:42; 5xx 6%; NullPointerException in PromoService.apply; started within 3 minutes of deploy",
     "bad_deploy", "Rolled back to v2.33 (RB-12)", "Restarting pods did not clear the errors", 10),
    (29, "INC-207", "sev2", "search-api", "Latency spike, Elasticsearch heap at 95%",
     "ES heap 95%; GC overhead warnings; fielddata cache 7GB; query p99 6s; traffic up 3x from partner feed",
     "capacity", "Added 2 data nodes and cleared the fielddata cache (RB-15)", "Rolling back search-api v4.2 had no effect", 41),
    (26, "INC-208", "sev3", "notifications", "Emails delayed by 40 minutes",
     "SES throttling: Maximum sending rate exceeded; rate limit changed from 50/s to 5/s in terraform PR #482 merged yesterday",
     "config_change", "Reverted the terraform change (RB-28)", "Scaling email workers did nothing", 22),
    (22, "INC-209", "sev1", "redis-sessions", "evicted_keys rising during flash sale",
     "evicted_keys 25k/s; used_memory 7.8GB of 8GB; flash sale started 14:00; hit rate 52%",
     "capacity", "Scaled to the dedicated 3-shard cluster (RB-07) without restarting anything", "", 14),
    (19, "INC-210", "sev2", "payments-api", "Webhook timeouts again, provider status page red",
     "upstream connect error: provider.example 503; queue depth 9k; provider status page red",
     "dependency_outage", "Fallback retry queue (RB-19); did not roll back", "", 18),
    (16, "INC-211", "sev2", "orders-db", "Slow queries after an index was dropped in a migration",
     "seq scan on orders (41M rows); p99 8s; migration 20260930 dropped idx_orders_customer; CPU 90%",
     "data_or_schema", "Recreated the index concurrently (RB-23)", "Adding a read replica did not help the write path", 31),
    (12, "INC-212", "sev3", "cdn", "Intermittent 502s from one region",
     "edge-fra 502 rate 11%; other regions healthy; edge provider incident acknowledged; traceroute loss at hop 7",
     "network", "Failed DNS over to the secondary edge provider with a 60s TTL (RB-33)", "Rolling back web-frontend had no effect", 25),
    (9, "INC-213", "sev2", "checkout-api", "p99 latency 4.1s after v2.40 deploy",
     "deploy v2.40 at 16:20; db.pool wait_time=3.4s; p99 4.1s; latency began 6 minutes after deploy",
     "bad_deploy", "Rolled back to v2.39 (RB-12)", "", 8),
    (6, "INC-214", "sev3", "search-api", "Index lag of 20 minutes",
     "indexing lag 20m; refresh_interval=-1 on products index; hotfix config PR #511 merged this morning",
     "config_change", "Reverted the hotfix config change (RB-28)", "Restarting the indexer did not help", 19),
]

OPEN = [
    ("INC-215", "sev2", "checkout-api", "p99 latency 4.4s since 14:02",
     "deploy v2.41 at 13:55; WARN db.pool wait_time=3.1s; checkout p99 4.4s; error rate 2%; started 7 minutes after deploy"),
    ("INC-216", "sev1", "redis-sessions", "Users being logged out, hit rate dropping",
     "evicted_keys 31k/s; used_memory 7.95GB of 8GB; hit rate 61%; flash sale started 14:00"),
    ("INC-217", "sev2", "payments-api", "Webhook 504s, retries piling up",
     "upstream connect error: provider.example 504; webhook queue depth 7k; provider status page shows degraded performance"),
    ("INC-218", "sev3", "orders-db", "Connections at 96% after the nightly job",
     "connection pool 96% used; idle in transaction sessions rising 40 to 180; nightly reconciliation job started 02:00"),
]


def _at(days_ago: float, hour: int = 14) -> str:
    return (_now().replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)).isoformat()


def load_history(mem: Memory, user: str) -> int:
    store.clear(user)
    mem.reset()
    batch: list[dict] = []
    for days_ago, iid, sev, svc, title, logs, cause, fix, failed, minutes in HISTORY:
        opened = _at(days_ago)
        done = (datetime.fromisoformat(opened) + timedelta(minutes=minutes)).isoformat()
        item = store.add(user, "incident", title, logs, why=svc, saved_at=opened, status="resolved", item_id=iid)
        item = store.update(user, iid, service=svc, severity=sev, resolved_at=done,
                            resolution={"cause": cause, "fix": fix, "failed": failed, "minutes": minutes, "suggestion_worked": None})
        batch.append({"content": postmortem_content(item), "context": "a resolved incident post-mortem: the most valuable memory for future triage",
                      "timestamp": done, "tags": ["incident", "postmortem", cause, svc], "document_id": f"postmortem-{iid}"})
    for iid, sev, svc, title, logs in OPEN:
        item = store.add(user, "incident", title, logs, why=svc, saved_at=_at(0.02, hour=_now().hour), item_id=iid)
        item = store.update(user, iid, service=svc, severity=sev)
        batch.append({"content": opened_content(item), "context": "a production incident that just opened",
                      "timestamp": item["saved_at"], "tags": ["incident", "opened", svc], "document_id": f"opened-{iid}"})
    mem.retain_many(batch)
    return len(batch)
