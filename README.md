# Acorn

Memory-first follow-through agent for work: the leads, job applications, articles, contracts and ideas you save and mean to get to. (The demo data also has a few personal items to show it works across kinds.) Acorn
remembers *what* you saved, *why*, and, most importantly, **what you actually did with it**. It uses that history
to tell you what deserves attention today and to answer "should I bother with this?" from your own track record.

## Where Hindsight sits
| Moment | Hindsight call | Code |
|---|---|---|
| You save an item | `retain` (reason, content, timestamp, tags) | `agent.save` |
| You mark it acted / ignoring | `retain` an *outcome* fact with days elapsed | `agent.resolve` |
| "Brief me" on an item | `reflect` over saves + outcomes | `agent.brief` |
| "Today" | `reflect` over open items + track record | `agent.today` |
| Ask (with vs without memory) | `reflect` vs a plain Groq call | `agent.ask` |
| 5-week demo | `retain_batch` with backdated timestamps | `seed.load` |

Outcomes are the key design choice: saving is cheap, acting is the signal. Memory is what turns "a bookmark list"
into "you act on payments jobs within 2 days and never cook weeknight recipes, so skip the stew, do the job".

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # add HINDSIGHT_API_KEY (+ base URL for Cloud), optional GROQ_API_KEY
.venv/bin/uvicorn app.main:app --reload
```
Open http://localhost:8000, click **Load 5-week demo history**, then try **Today** and the **Ask** tab.
Tests (no Hindsight needed): `.venv/bin/python -m pytest`.

## Status
- Unit tests run against a fake memory backend (`tests/`), so they need no network or key.
- Retain, recall and reflect, the demo history load, Today, Brief and Ask have been run against Hindsight Cloud (`python -m scripts.smoke` re-checks the connection).
- The "without memory" column needs `GROQ_API_KEY`; without it the UI shows a placeholder.
- Demo data is synthetic. It is generated with deliberate habits so you can see the agent learn them.
