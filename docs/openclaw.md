# Use the same memory from an OpenClaw agent

Pager Memory's incident history lives in the Hindsight bank `acorn-demo-pager`. The official
[Hindsight OpenClaw plugin](https://hindsight.vectorize.io/sdks/integrations/openclaw) lets an OpenClaw agent read the
same bank, so you can ask the agent about an outage in chat and it answers from your team's real history.

> Status: **verified end to end on this machine.** OpenClaw 2026.11.1 on Node 24, the Hindsight plugin on the
> `acorn-demo-pager` bank, and the model `google/gemini-3.6-flash`. Asked "Payments webhooks are returning 504s from the
> provider. Should I roll back?", the agent answered "No, do not roll back", citing INC-203 (rolling back wasted 20
> minutes) and the RB-19 fallback queue from INC-203 and INC-210. The plugin log shows
> `injecting 61 memories into context (bank: acorn-demo-pager)`.

## Gotchas we hit (in order)
1. **Node must be 24.16+** (not 25). With Homebrew: `brew install node@24` and put it first on `PATH` in that terminal.
2. **Groq's free tier caps requests at 8,000 tokens**, and OpenClaw's prompt is about 8,200. Every turn fails with
   "Context overflow". Use a larger-limit model (we used Google Gemini). Model notes: `gemini-2.5-flash` is no longer
   offered to new accounts, `gemini-3.8-flash` returned 503 "high demand" (OpenClaw silently retries 8 times, which looks
   like a hang), `gemini-3.6-flash` worked. Set it with `openclaw models set google/gemini-3.6-flash`.
3. **Allow the plugin to read conversations**, or its recall hooks are blocked:
   `openclaw config set plugins.entries.hindsight-openclaw.hooks.allowConversationAccess true` (then restart the gateway).
4. **Config changes show "persisted but not applied"**: run `openclaw daemon restart` and they take effect.
5. **Recall only runs on sessions that come from a real chat surface** (dashboard, terminal chat, a channel). A bare
   `openclaw agent --message ...` has no message provider and the plugin logs "Skipping recall". Use
   `--session-key agent:acorn:main`, or just use the dashboard.
6. **After your laptop sleeps, DNS can be down for a moment**: recall fails with "fetch failed" and the model with
   `ENOTFOUND`. Retry after a few seconds.
7. The installer warns the plugin is outside ClawHub's reviewed registry and needs `--force`. We checked the package
   first: `@vectorize-io` publisher, repo `vectorize-io/hindsight`, no install scripts.

## 1. Install OpenClaw (needs Node 24.16+)
```bash
node --version                                   # must be >= 24.16
npm install -g openclaw@latest --allow-scripts=openclaw   # or: curl -fsSL https://openclaw.ai/install.sh | bash
openclaw onboard --install-daemon                # interactive: pick a model provider, add its key
```

## 2. Install the Hindsight plugin
```bash
openclaw plugins install @vectorize-io/hindsight-openclaw --force   # --force after reviewing the package, see gotcha 7
```

## 3. Point it at the Acorn bank
Put the token in an env var (never in the file) and reference it as a SecretRef:
```bash
export HINDSIGHT_API_TOKEN=$(grep '^HINDSIGHT_API_KEY=' .env | cut -d= -f2)
openclaw config set plugins.entries.hindsight-openclaw.config.hindsightApiToken \
  --ref-source env --ref-provider default --ref-id HINDSIGHT_API_TOKEN
```
Then merge [`openclaw/openclaw.json.snippet`](../openclaw/openclaw.json.snippet) into `~/.openclaw/openclaw.json`
(`hindsightApiUrl`, `dynamicBankId: false`, `bankId: acorn-demo-pager`, `memoryMode: hybrid`, and the
`allowConversationAccess` hook permission). Or apply it with `openclaw config patch --file ...` and `openclaw daemon restart`.

`autoRetain` is `false` so chat turns do not pollute the seeded incident history. Set it to `true` if you want the
agent to retain what you tell it (for example, declaring a new incident in chat).
Use `bankId: acorn-demo` instead to share the follow-through (Acorn) memory.

## 4. Run and verify
```bash
openclaw gateway status && openclaw dashboard
.venv/bin/python -m scripts.openclaw_check       # confirms the bank is reachable and populated
```
Ask the agent: *"Payments webhooks are returning 504s from the provider. Should I roll back?"*
Expected: it recalls INC-203 / INC-210 (fallback queue RB-19, rolling back wasted 20 minutes) from Hindsight.

## What the plugin gives the agent
Automatic recall before each reply (up to 1024 tokens), plus the tools `hindsight_recall`, `hindsight_reflect` and
`hindsight_retain`.
