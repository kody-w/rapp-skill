# rapp-skill

**Hand this package to Claude Code, GitHub Copilot CLI, Codex, or any agent harness,
and it can run your whole RAPP ecosystem and move capabilities between RAPP agents
and Agent Skills without a rewrite.**

Install a local agent brainstem with no API keys, keep it healthy, install and test
single-file agents from two public catalogs, talk to it, and promote what works to
Azure and Copilot Studio.

The package contains two discoverable skills:

| Skill | Engine | Purpose |
|---|---|---|
| `rapp` | `skills/rapp/scripts/rapp.py` | Install, operate, test, and promote the RAPP ecosystem. |
| `rapp-agent-converter` | `skills/rapp-agent-converter/scripts/toast.py` | Convert `agent.py` ↔ Agent Skill with a byte-exact linked-agent pair. |

```bash
python3 skills/rapp/scripts/rapp.py doctor
```

---

## What this is

RAPP is a three-tier platform: a **brainstem** on your laptop, **Azure Functions** in
your subscription, and **Copilot Studio** in front of your users. The same single `.py`
agent file runs at every tier, so there is no rewrite between prototype and production.

This repository is the **skill that ties it together**. It reimplements nothing — it
calls the same installer one-liner a human would run and reads the same public catalogs
a human would browse. What it adds is a single, consistent command surface an AI can
drive without improvising.

| Tier | Name | Where | What it gives you |
|------|------|-------|-------------------|
| 1 | Brainstem | Your laptop | The agent loop and memory on disk at `~/.brainstem`. Reached through the GitHub Copilot CLI, so no API keys to provision. |
| 2 | Spinal Cord | Azure Functions | Always-on, cloud storage. Same agent file. |
| 3 | Nervous System | Copilot Studio / Teams | Governed, published, in front of real users. |

## Install the skill

```bash
# Claude Code
/plugin marketplace add kody-w/rapp-skill
/plugin install rapp

# Any agent directory (Codex, OpenClaw, .agents)
git clone https://github.com/kody-w/rapp-skill ~/.agents/skills/rapp-skill
```

Then just ask: *"install my brainstem"*, *"is my brainstem healthy?"*, *"find me an
agent that tracks projects"*, *"test this agent"*.

## RAPP runtime commands

Runtime operations route through `skills/rapp/scripts/rapp.py`, so an AI never
has to hand-write a `curl` call against the brainstem or a multipart upload.

| Command | What it does |
|---------|--------------|
| `doctor` | Health check across every tier, with a fix line for anything broken. `--deep` adds a live chat round-trip; `--postmortem` reads what the last run did. |
| `install` | Runs **the canonical installer one-liner**. `--dry-run` shows it without executing. |
| `up` / `down` / `status` | Start, stop, and check the local brainstem. |
| `search <query>` | Search RAR — 200+ single-file agents, ranked by AI critic score, votes and downloads. |
| `agents list/install/remove/export` | Manage what is loaded. Installs are **SHA-256 verified** and hot-loaded without a restart. |
| `store list/install` | RAPPstore — converged **rapplications** and **senses**. |
| `chat "…"` | Send a turn and see the tool trace. |
| `test <file>` | Load an agent through the brainstem's own loader and **actually run it** — sandboxed, timed out, contract-checked. |
| `map` | Which repo owns which layer of the ecosystem. |
| `tiers` | Where this machine stands across all three tiers. |
| `memory` | Inspect and back up what the brainstem remembers. |

Add `--json` to any `rapp.py` command for structured output.

## Agent Skill conversion commands

Conversion is a separate CLI owned by the sibling skill:

```bash
python3 skills/rapp-agent-converter/scripts/toast.py \
  convert path/to/foo_agent.py --to skill -o out/SKILL.md
python3 skills/rapp-agent-converter/scripts/toast.py \
  convert out/SKILL.md --to agent
python3 skills/rapp-agent-converter/scripts/toast.py \
  roundtrip path/to/foo_agent.py
```

`toast.py` does not accept `--json`. Its stdout is already a stable
human-readable verdict and `inspect` emits JSON.

## Zero to a working agent

```bash
rapp doctor          # what is missing
rapp install         # the canonical one-liner
rapp up              # start it
rapp doctor --deep   # prove the model answers
rapp search notes    # find something useful
rapp agents install @kody-w/context_memory_agent
rapp chat "what tools do you have?"
```

The last command should list the agent you just installed.

## Prerequisites

Python 3.11+, `git`, `gh`, and a GitHub account (`gh auth login`). Nothing else — the
runtime reaches models through the GitHub Copilot CLI, which is the preferred backend,
so there are no API keys to provision. Whatever Copilot access your account has is
between you and GitHub; this skill makes no claim about it.

Tiers 2 and 3 use your own Azure and Microsoft 365 subscriptions and need the `az`,
`func`, and `pac` CLIs. `rapp doctor` reports which are present without assuming any.

## Design rules

- **Reimplements nothing.** The installer, the catalogs, and the brainstem are upstream.
  The submitted `rapp-agent-converter` skill owns conversion. This package is the seam
  between them; `rapp.py` does not grow a second converter.
- **Integrity is not optional.** Every install is SHA-256 verified against the catalog.
  A mismatch stops the install.
- **Third-party code is sandboxed.** `test` runs agents in a subprocess, in a throwaway
  working directory, with a timeout.
- **Never diagnose from memory.** `doctor` reads the live system and prints a fix line;
  the AI relays it rather than improvising shell surgery.
- **No entitlement claims.** The tool is named; the subscription is not characterized.
  Enforced by a test and by CI.

## Repository layout

```
skills/rapp/
  SKILL.md               the contract an AI reads
  scripts/rapp.py        the engine — every command
  references/            tiers, agent contract, troubleshooting
skills/rapp-agent-converter/
  SKILL.md               conversion operating procedure
  scripts/toast.py       byte-exact agent.py ↔ Agent Skill engine
  references/            RAPP contract + rapp/1 wire
  assets/                executable sample cartridge
tests/                   offline contract tests
.claude-plugin/          Claude Code plugin + marketplace
.codex-plugin/           Codex plugin
.grok-plugin/            Grok plugin + marketplace
.agents/plugins/         generic agent-directory marketplace
gemini-extension.json    Gemini extension
```

## Tests

```bash
python -m pytest tests/ -q
```

The suite is offline by design: no brainstem and no network required, so CI stays
honest on a machine with neither.

The converter's own selftest and sample roundtrip run in the same suite.

## The ecosystem

[rapp-installer](https://github.com/kody-w/rapp-installer) ·
[rapp-brainstem](https://github.com/kody-w/rapp-brainstem) ·
[RAR](https://github.com/kody-w/RAR) ·
[RAPP_Store](https://github.com/kody-w/RAPP_Store) ·
[rapp-twin](https://github.com/kody-w/rapp-twin) ·
[rapp-map](https://github.com/kody-w/rapp-map)

Run `rapp map` for the full picture.

---

MIT licensed. RAPP and the RAPP family of names are trademarks of the RAPP project.
Microsoft, Azure, Microsoft 365, Copilot, Copilot Studio and Teams are trademarks of
Microsoft Corporation; GitHub and GitHub Copilot are trademarks of GitHub, Inc. Named
here only to describe interoperability.
