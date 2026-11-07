from app import agent, seed, store


def test_save_retains_item_with_reason_and_tags(client, mem):
    r = client.post("/api/items", json={"kind": "job", "title": "Staff Eng", "text": "Apply by 9 Nov", "why": "payments fit"})
    assert r.status_code == 200
    m = mem.retained[-1]
    assert "payments fit" in m["content"] and "Apply by 9 Nov" in m["content"]
    assert m["tags"] == ["save", "job"] and m["document_id"].startswith("save-")


def test_unknown_kind_falls_back_to_other(client, mem):
    client.post("/api/items", json={"kind": "bogus", "text": "x"})
    assert mem.retained[-1]["tags"] == ["save", "other"]


def test_outcome_is_retained_with_days_elapsed(client, mem):
    item = client.post("/api/items", json={"kind": "recipe", "title": "Ragu", "text": "t"}).json()
    r = client.post(f"/api/items/{item['id']}/resolve", json={"status": "ignored", "note": "too long"})
    assert r.json()["status"] == "ignored"
    m = mem.retained[-1]
    assert "ignored" in m["content"] and "0 days after saving" in m["content"] and "too long" in m["content"]
    assert m["tags"] == ["outcome", "recipe", "ignored"]


def test_resolving_twice_does_not_retain_twice(client, mem):
    item = client.post("/api/items", json={"kind": "job", "text": "t"}).json()
    client.post(f"/api/items/{item['id']}/resolve", json={"status": "acted"})
    n = len(mem.retained)
    client.post(f"/api/items/{item['id']}/resolve", json={"status": "ignored"})
    assert len(mem.retained) == n


def test_bad_status_and_missing_item(client):
    assert client.post("/api/items/nope/resolve", json={"status": "acted"}).status_code == 404
    assert client.post("/api/items/nope/resolve", json={"status": "weird"}).status_code == 422


def test_today_with_empty_inbox_makes_no_memory_call(client, mem):
    assert "Nothing open" in client.get("/api/today").json()["text"]
    assert mem.reflections == []


def test_today_lists_only_open_items_to_reflect(client, mem):
    a = client.post("/api/items", json={"kind": "job", "title": "Open one", "text": "t"}).json()
    b = client.post("/api/items", json={"kind": "job", "title": "Done one", "text": "t"}).json()
    client.post(f"/api/items/{b['id']}/resolve", json={"status": "acted"})
    client.get("/api/today")
    q = mem.reflections[-1][0]
    assert "Open one" in q and "Done one" not in q and a["id"] in q


def test_ask_returns_both_sides(client, mem, monkeypatch):
    monkeypatch.setattr("app.llm.answer_without_memory", lambda q: "generic")
    r = client.post("/api/ask", json={"question": "Should I apply?"}).json()
    assert r["without_memory"] == "generic" and r["with_memory"]["text"] == "reflected"
    assert "Today is" in mem.reflections[-1][1]


def test_seed_history_contains_patterns_and_open_items(mem):
    n = seed.load(mem, "demo")
    items = store.list_items("demo")
    assert n == len(mem.retained) and n > 40
    assert sum(1 for i in items if i["status"] == "open") == len(seed.OPEN_ITEMS)
    jobs = [i for i in items if i["kind"] == "job" and i["status"] != "open"]
    assert jobs and all(i["status"] == "acted" for i in jobs)
    recipes = [i for i in items if i["kind"] == "recipe" and i["status"] != "open"]
    assert sum(1 for i in recipes if i["status"] == "ignored") > sum(1 for i in recipes if i["status"] == "acted")
    assert len({m["document_id"] for m in mem.retained}) == len(mem.retained)  # idempotent ids


def test_brief_unknown_item(client):
    assert client.get("/api/items/zzz/brief").status_code == 404


def test_index_served(client):
    assert "Acorn" in client.get("/").text


def test_ask_passes_authoritative_status_to_memory(client, mem, monkeypatch):
    monkeypatch.setattr("app.llm.answer_without_memory", lambda q: "generic")
    a = client.post("/api/items", json={"kind": "job", "title": "Done job", "text": "t"}).json()
    client.post("/api/items", json={"kind": "job", "title": "Pending job", "text": "t"})
    client.post(f"/api/items/{a['id']}/resolve", json={"status": "acted"})
    client.post("/api/ask", json={"question": "what is pending?"})
    ctx = mem.reflections[-1][1]
    assert "OPEN: Pending job (job)" in ctx and "ACTED: Done job (job)" in ctx


def _item(client, title="Podcast idea"):
    return client.post("/api/items", json={"kind": "idea", "title": title, "text": "t"}).json()


def test_ghost_predicts_and_stores_before_action(client, mem):
    it = _item(client)
    r = client.post(f"/api/items/{it['id']}/predict").json()
    assert r["prediction"]["label"] == "ignore" and r["prediction"]["confidence"] == 82 and r["correct"] is None
    assert client.get("/api/ghost").json()["pending"] == 1


def test_ghost_wrong_then_right_scores_and_teaches_memory(client, mem):
    a, b = _item(client, "A"), _item(client, "B")
    client.post(f"/api/items/{a['id']}/predict"); client.post(f"/api/items/{b['id']}/predict")
    wrong = client.post(f"/api/items/{a['id']}/resolve", json={"status": "acted"}).json()   # predicted ignore, acted
    right = client.post(f"/api/items/{b['id']}/resolve", json={"status": "ignored"}).json()  # predicted ignore, ignored
    assert wrong["correct"] is False and right["correct"] is True
    s = client.get("/api/ghost").json()
    assert (s["graded"], s["right"], s["accuracy"], s["pending"]) == (2, 1, 50, 0)
    fb = [m for m in mem.retained if "prediction" in m["tags"]]
    assert len(fb) == 2 and "wrong" in fb[0]["tags"] and "predicted the user would ignore" in fb[0]["content"]


def test_ghost_clamps_confidence_and_rejects_garbage(client, mem):
    it = _item(client)
    mem.structured = {"prediction": "act", "confidence": 250, "reason": "x"}
    assert client.post(f"/api/items/{it['id']}/predict").json()["prediction"]["confidence"] == 99
    it2 = _item(client, "C")
    mem.structured = {"prediction": "maybe", "confidence": 60, "reason": "x"}
    assert client.post(f"/api/items/{it2['id']}/predict").status_code == 502


def test_ghost_only_for_open_items_and_is_not_regenerated(client, mem):
    it = _item(client)
    client.post(f"/api/items/{it['id']}/predict")
    n = len(mem.reflections)
    client.post(f"/api/items/{it['id']}/predict")
    assert len(mem.reflections) == n  # cached, no second memory call
    client.post(f"/api/items/{it['id']}/resolve", json={"status": "ignored"})
    assert client.post(f"/api/items/{it['id']}/predict").status_code == 409
    assert client.post("/api/items/nope/predict").status_code == 404


def test_unpredicted_items_do_not_affect_score(client):
    it = _item(client)
    client.post(f"/api/items/{it['id']}/resolve", json={"status": "acted"})
    assert client.get("/api/ghost").json()["accuracy"] is None
