# Use the same memory from an OpenClaw agent

Pager Memory's incident history lives in the Hindsight bank `acorn-demo-pager`. The official
[Hindsight OpenClaw plugin](https://hindsight.vectorize.io/sdks/integrations/openclaw) lets an OpenClaw agent read the
same bank, so you can ask the agent about an outage in chat and it answers from your team's real history.

> Status: the plugin config and bank were checked against the plugin docs and live Hindsight
> (`python -m scripts.openclaw_check`). The OpenClaw install itself has not been run on this machine yet.

## 1. Install OpenClaw (needs Node 24.16+)
```bash
node --version                                   # must be >= 24.16
npm install -g openclaw@latest --allow-scripts=openclaw   # or: curl -fsSL https://openclaw.ai/install.sh | bash
openclaw onboard --install-daemon                # interactive: pick a model provider, add its key
```

## 2. Install the Hindsight plugin
```bash
openclaw plugins install @vectorize-io/hindsight-openclaw
```

## 3. Point it at the Acorn bank
Put the token in an env var (never in the file) and reference it as a SecretRef:
```bash
export HINDSIGHT_API_TOKEN=$(grep '^HINDSIGHT_API_KEY=' .env | cut -d= -f2)
openclaw config set plugins.entries.hindsight-openclaw.config.hindsightApiToken \
  --ref-source env --ref-provider default --ref-id HINDSIGHT_API_TOKEN
```
Then merge [`openclaw/openclaw.json.snippet`](../openclaw/openclaw.json.snippet) into `~/.openclaw/openclaw.json`
(`hindsightApiUrl`, `dynamicBankId: false`, `bankId: acorn-demo-pager`, `memoryMode: hybrid`).

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
