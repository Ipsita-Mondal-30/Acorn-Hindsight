"""Realistic 5-week history with deliberate behavioural patterns for memory to learn:
  - job posts: always acted on, within 1-2 days, especially when a deadline is stated
  - recipes: ignored on weekdays, cooked only when saved on a Friday/Saturday
  - long technical articles: read on Sunday, never midweek
  - product bookmarks: ignored unless there was a price/deadline
  - voice-note ideas: acted on same day or never
Then six OPEN items so 'Today' has something to judge."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import agent, store
from .memory import Memory

# (days_ago, kind, title, text, why, outcome)  outcome = None | (status, days_later, note)
HISTORY = [
    (35, "job", "Staff Backend Engineer, Ledgerly (Berlin, remote ok)", "Ledgerly (Series B fintech) hiring Staff Backend Engineer. Go, Postgres, event sourcing. EUR 140-165k. Apply by 28 Oct.", "Fits my payments background", ("acted", 1, "Sent application with tailored CV; emphasised event sourcing work")),
    (34, "recipe", "Miso butter roast chicken", "Whole chicken, white miso, butter, lemon, 1h20m roast. Serves 4.", "Looks easy for guests", ("ignored", 9, "Never cooked it")),
    (31, "article", "Designing Data-Intensive Apps: LSM trees explained (45 min read)", "Long technical post comparing LSM trees and B-trees with benchmarks.", "Read properly when I have time", ("acted", 3, "Read it on Sunday morning with coffee")),
    (30, "product", "Keychron Q1 Pro keyboard", "Keychron Q1 Pro, USD 199, no sale mentioned.", "Maybe", ("ignored", 14, "Forgot about it")),
    (28, "idea", "Voice note: cohort retention dashboard for onboarding", "Idea: weekly cohort retention view segmented by signup source, to show onboarding drop-off.", "Pitch to Priya Monday", ("acted", 0, "Sent Priya a one-pager the same day")),
    (27, "job", "Senior Platform Engineer, Northwind Cloud (remote EU)", "Northwind Cloud hiring Senior Platform Engineer. Kubernetes, Terraform. Apply by 3 Nov. Referral possible via Tomas.", "Referral through Tomas", ("acted", 1, "Messaged Tomas for referral next morning")),
    (25, "recipe", "Shakshuka with feta", "Eggs poached in spiced tomato sauce, 30 min.", "Weeknight dinner", ("ignored", 7, "Ordered takeaway instead")),
    (24, "recipe", "Slow-braised lamb ragu (4 hours)", "Lamb shoulder, red wine, 4 hour braise, pappardelle.", "Saturday project cook", ("acted", 1, "Cooked it Saturday evening, saved leftovers")),
    (23, "article", "Postgres vacuum internals (30 min)", "Deep dive on autovacuum tuning and bloat.", "For the prod incident review", ("ignored", 12, "Skimmed the headings only, midweek")),
    (21, "document", "Car insurance renewal letter (PDF)", "Renewal premium EUR 612, up from 540. Must confirm or switch by 30 Oct.", "Compare quotes before it auto-renews", ("acted", 2, "Switched provider, saved EUR 90")),
    (20, "product", "Standing desk converter, 30% off ends Friday", "Flexispot converter EUR 129 (was 185). Sale ends Friday.", "Back pain", ("acted", 1, "Bought it the next day before sale ended")),
    (18, "job", "Engineering Manager, Kestrel Health (Hybrid, Hamburg)", "Kestrel Health seeks Engineering Manager, team of 8, digital therapeutics. Apply by 10 Nov.", "Interesting but not sure about management", ("acted", 2, "Applied; the deadline made it feel real")),
    (17, "recipe", "Sourdough focaccia", "24h cold ferment, rosemary and sea salt.", "Friday prep for weekend", ("acted", 2, "Baked Saturday, shared with neighbours")),
    (14, "article", "Event sourcing without the pain (20 min)", "Practical patterns for snapshots and projections.", "Relevant to Ledgerly interview", ("acted", 1, "Read before the interview, used two ideas in it")),
    (13, "idea", "Voice note: offsite agenda, add a failure-sharing session", "Suggest a 'what broke this quarter' session at the team offsite.", "Raise at planning", ("acted", 0, "Added to the offsite doc same day")),
    (12, "recipe", "Thai green curry paste from scratch", "Mortar and pestle paste, 1h.", "Weekday dinner?", ("ignored", 6, "Too long for a weeknight")),
    (10, "product", "Noise-cancelling headphones (Sony XM6)", "EUR 379, no deadline.", "Open office is loud", ("ignored", 10, "Never revisited")),
    (9, "document", "Co-working space contract (PDF)", "Month-to-month EUR 220, cancel with 30 days notice before the 1st.", "Cancel before it renews", ("acted", 1, "Sent cancellation email next day")),
    (8, "article", "Raft consensus visualised (60 min)", "Interactive walkthrough of Raft.", "Learn properly", ("ignored", 5, "Opened Tuesday, closed after 3 minutes")),
    (7, "job", "Principal Engineer, Vantage Robotics (Munich)", "Vantage Robotics hiring Principal Engineer. C++/Rust. Apply by 8 Nov. Relocation offered.", "Robotics is exciting, relocation unclear", ("acted", 1, "Asked recruiter about remote policy first, then applied")),
    (6, "idea", "Voice note: write up the migration retro as a blog post", "Turn the Postgres migration retro into a public post.", "Good portfolio piece", ("ignored", 6, "Never opened the draft")),
    (4, "recipe", "Weeknight chickpea stew", "20 minute stew, pantry ingredients.", "Easy dinners", ("ignored", 3, "Cooked something else")),
]

OPEN_ITEMS = [
    (3, "job", "Staff Engineer, Hexagon Pay (Remote EU)", "Hexagon Pay hiring Staff Engineer, payments infra, Go. EUR 150-175k. Apply by 9 Nov.", "Payments again, strong fit"),
    (3, "recipe", "Burnt basque cheesecake", "Six ingredients, 45 min bake, fridge overnight.", "Birthday dessert"),
    (2, "article", "Why we moved from Kafka to Postgres queues (25 min)", "Case study on replacing Kafka with SKIP LOCKED queues.", "Might apply to our infra"),
    (2, "document", "Passport renewal reminder (PDF)", "Passport expires 14 Jan. Some countries need 6 months validity. Renewal appointment needed.", "Check before booking travel"),
    (1, "product", "Ergonomic vertical mouse", "Logitech Lift EUR 69, no deadline.", "Wrist pain"),
    (1, "idea", "Voice note: ask Tomas to review the Ledgerly offer terms", "If an offer comes, have Tomas sanity check the equity terms.", "Prepare ahead"),
]


def _at(days_ago: float, hour: int = 9) -> str:
    d = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return d.isoformat()


def load(mem: Memory, user: str) -> int:
    """Wipe local items, rebuild the Hindsight bank, and retain the whole history in one batch."""
    store.clear(user)
    mem.reset()
    batch: list[dict] = []
    n = 0
    for days_ago, kind, title, text, why, outcome in HISTORY:
        item = store.add(user, kind, title, text, why, saved_at=_at(days_ago),
                         status=outcome[0] if outcome else "open", item_id=f"s{n:02d}")
        batch.append({"content": agent.save_content(item), "context": "a thing the user saved to follow up on later",
                      "timestamp": item["saved_at"], "tags": ["save", kind], "document_id": f"save-{item['id']}"})
        if outcome:
            status, later, note = outcome
            resolved = _at(days_ago - later, hour=19)
            items = store._load(user)
            for i in items:
                if i["id"] == item["id"]:
                    i["resolved_at"] = resolved
            store._dump(user, items)
            batch.append({"content": agent.outcome_content(item, status, resolved, note),
                          "context": "what the user actually did with something they saved; the strongest signal of what they care about",
                          "timestamp": resolved, "tags": ["outcome", kind, status], "document_id": f"outcome-{item['id']}"})
        n += 1
    for days_ago, kind, title, text, why in OPEN_ITEMS:
        item = store.add(user, kind, title, text, why, saved_at=_at(days_ago), item_id=f"o{n:02d}")
        batch.append({"content": agent.save_content(item), "context": "a thing the user saved to follow up on later",
                      "timestamp": item["saved_at"], "tags": ["save", kind], "document_id": f"save-{item['id']}"})
        n += 1
    mem.retain_many(batch)
    return len(batch)
