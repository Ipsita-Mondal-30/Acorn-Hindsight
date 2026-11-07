from app import pager, store

U = pager.pager_user()
TRIAGE = {"cause": "bad_deploy", "confidence": 90, "first_step": "Roll back with RB-12", "avoid": "Do not scale pods",
          "similar": ["INC-201 same latency after deploy"], "reason": "matches INC-201"}


def _open(client, title="checkout latency"):
    return client.post("/api/pager/items", json={"title": title, "service": "checkout-api", "severity": "sev2",
                                                  "text": "deploy v2.41, p99 4s"}).json()


def test_open_incident_retains_context(client, mem):
    i = _open(client)
    assert i["id"].startswith("INC-") and i["status"] == "open" and i["service"] == "checkout-api"
    m = mem.retained[-1]
    assert "checkout-api" in m["content"] and "p99 4s" in m["content"] and m["tags"][:2] == ["incident", "opened"]


def test_bad_severity_defaults_and_empty_service_rejected(client):
    r = client.post("/api/pager/items", json={"service": "x", "severity": "sev9", "text": "t"}).json()
    assert r["severity"] == "sev2"
    assert client.post("/api/pager/items", json={"service": "", "text": "t"}).status_code == 422


def test_triage_stores_structured_result_and_is_cached(client, mem):
    mem.structured = TRIAGE
    i = _open(client)
    t = client.post(f"/api/pager/items/{i['id']}/triage").json()["triage"]
    assert t["cause"] == "bad_deploy" and t["confidence"] == 90 and t["similar"]
    n = len(mem.reflections)
    client.post(f"/api/pager/items/{i['id']}/triage")
    assert len(mem.reflections) == n
    assert "INC-" in mem.reflections[0][0] and "ONLY this team" in mem.reflections[0][0]


def test_triage_rejects_unknown_cause_and_clamps_confidence(client, mem):
    i = _open(client)
    mem.structured = {**TRIAGE, "cause": "aliens"}
    assert client.post(f"/api/pager/items/{i['id']}/triage").status_code == 502
    j = _open(client, "other")
    mem.structured = {**TRIAGE, "confidence": 5}
    assert client.post(f"/api/pager/items/{j['id']}/triage").json()["triage"]["confidence"] == 40


def test_resolve_retains_postmortem_and_grades_triage(client, mem):
    mem.structured = TRIAGE
    i = _open(client)
    client.post(f"/api/pager/items/{i['id']}/triage")
    r = client.post(f"/api/pager/items/{i['id']}/resolve", json={
        "cause": "capacity", "fix": "scaled the cluster", "minutes": 17, "failed": "restart made it worse",
        "suggestion_worked": False}).json()
    assert r["status"] == "resolved" and r["correct"] is False
    pm = [m for m in mem.retained if "postmortem" in m["tags"]][0]["content"]
    assert "Capacity / load" in pm and "scaled the cluster" in pm and "did NOT work: restart made it worse" in pm and "17 minutes" in pm
    fb = [m for m in mem.retained if "triage" in m["tags"]][0]
    assert "WRONG" in fb["content"] and "did not work" in fb["content"] and "wrong" in fb["tags"]


def test_score_counts_only_triaged_incidents(client, mem):
    mem.structured = TRIAGE
    a, b, c = _open(client, "a"), _open(client, "b"), _open(client, "c")
    client.post(f"/api/pager/items/{a['id']}/triage"); client.post(f"/api/pager/items/{b['id']}/triage")
    client.post(f"/api/pager/items/{a['id']}/resolve", json={"cause": "bad_deploy", "minutes": 5, "suggestion_worked": True})
    client.post(f"/api/pager/items/{b['id']}/resolve", json={"cause": "network", "minutes": 9})
    client.post(f"/api/pager/items/{c['id']}/resolve", json={"cause": "network", "minutes": 9})  # never triaged
    s = client.get("/api/pager/score").json()
    assert (s["graded"], s["right"], s["accuracy"], s["step_graded"], s["step_worked"]) == (2, 1, 50, 1, 1)
    assert s["resolved"] == 3 and s["open"] == 0


def test_resolve_validation_and_state_guards(client, mem):
    i = _open(client)
    assert client.post(f"/api/pager/items/{i['id']}/resolve", json={"cause": "gremlins", "minutes": 5}).status_code == 422
    assert client.post(f"/api/pager/items/{i['id']}/resolve", json={"cause": "network", "minutes": 0}).status_code == 422
    assert client.post("/api/pager/items/INC-nope/resolve", json={"cause": "network", "minutes": 5}).status_code == 404
    client.post(f"/api/pager/items/{i['id']}/resolve", json={"cause": "network", "minutes": 5})
    n = len(mem.retained)
    client.post(f"/api/pager/items/{i['id']}/resolve", json={"cause": "capacity", "minutes": 5})
    assert len(mem.retained) == n  # second resolve is ignored
    assert client.post(f"/api/pager/items/{i['id']}/triage").status_code == 409


def test_seed_history_has_recurring_patterns(mem):
    n = pager.load_history(mem, U)
    items = store.list_items(U)
    assert n == len(pager.HISTORY) + len(pager.OPEN) == len(items)
    assert sum(1 for i in items if i["status"] == "open") == len(pager.OPEN)
    causes = [i["resolution"]["cause"] for i in items if i["status"] == "resolved"]
    assert causes.count("bad_deploy") >= 3 and causes.count("capacity") >= 3 and "dependency_outage" in causes
    assert all(c in pager.CAUSES for c in causes)
    pm = [m["content"] for m in mem.retained if "postmortem" in m["tags"]]
    assert any("did NOT work" in c for c in pm) and len({m["document_id"] for m in mem.retained}) == n


def test_pager_ask_uses_incident_status_and_baseline(client, mem, monkeypatch):
    seen = {}
    monkeypatch.setattr("app.llm.answer_without_memory", lambda q, role="x": seen.setdefault("role", role) and "generic")
    _open(client)
    r = client.post("/api/pager/ask", json={"question": "seen this before?"}).json()
    assert r["without_memory"] == "generic" and "no access" in seen["role"]
    assert "open checkout-api" in mem.reflections[-1][1]


def test_pager_page_served(client):
    r = client.get("/pager")
    assert r.status_code == 200 and "Pager Memory" in r.text
