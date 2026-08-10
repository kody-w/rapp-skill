---
name: rapp
version: "1.1.0"
description: "Run the whole RAPP ecosystem end to end. Installs the local brainstem (a GitHub-Copilot-powered agent server that needs no API keys), keeps it healthy with a doctor, installs and tests single-file agents from RAR and RAPPstore, converts RAPP agent.py cartridges into Agent Skills and back through the bundled rapp-agent-converter skill, talks to the brainstem over /chat, and promotes what works to Azure and Copilot Studio."
argument-hint: 'rapp doctor | rapp install | rapp search memory | rapp chat "what can you do?"'
allowed-tools: Bash, Read, Write, AskUserQuestion
homepage: https://github.com/kody-w/rapp-skill
repository: https://github.com/kody-w/rapp-skill
author: kody-w
license: MIT
user-invocable: true
metadata:
  openclaw:
    emoji: "🧠"
    requires:
      env: []
      optionalEnv:
        - GITHUB_TOKEN
        - BRAINSTEM_URL
        - RAPP_HOME
      bins:
        - python3
        - git
        - gh
    files:
      - "scripts/*"
    homepage: https://github.com/kody-w/rapp-skill
    tags:
      - rapp
      - brainstem
      - local-first
      - ai-agents
      - single-file-agent
      - github-copilot
      - copilot-studio
      - azure-functions
      - agent-registry
      - rappstore
      - on-device
      - m365
      - teams
      - agent-runtime
      - ai-skill
---

# SKILL CONTRACT — READ BEFORE ANY TOOL CALL

You are inside the `/rapp` skill. It drives a real ecosystem that already exists: a
local agent server, two public catalogs, and a promotion path to Azure and Copilot
Studio. **This skill installs nothing of its own and reimplements nothing.** It calls
the same installer one-liner a human would run and the same public catalogs a human
would browse. If you find yourself writing an install script, a registry parser, or an
agent loader from scratch, stop — the engine already does it, and the ecosystem owns
the source of truth.

**Each surface has one engine.** Runtime and ecosystem operations route through
`scripts/rapp.py`. Agent Skill conversion routes through the sibling
`rapp-agent-converter` skill and its `scripts/toast.py`. Do not implement conversion
inside `rapp.py`, improvise `curl` calls against the brainstem, hand-write multipart
uploads, or shell into `~/.brainstem` to move files.

```bash
SKILL_DIR="/absolute/path/to/the/skills/rapp directory"
python3 "$SKILL_DIR/scripts/rapp.py" <command>
```

Resolve `SKILL_DIR` from the actual path of the `SKILL.md` the host loaded, using
the host's workspace/file tools. **Do not derive it from shell `$0`** — that names
the shell, not this skill. Whichever install supplied this file is the install whose
engine runs; do not search for another copy.

---

## What RAPP actually is

A three-tier platform. The same single Python file runs at every tier, which is the
whole point — there is no rewrite between prototype and production.

| Tier | Name | Where it runs | What it gives you |
|------|------|---------------|-------------------|
| 1 | **Brainstem** | Your laptop | The agent loop, tools, memory on disk at `~/.brainstem`. Reached through the GitHub Copilot CLI, so there are no API keys to provision. |
| 2 | **Spinal Cord** | Azure Functions | Always-on, cloud storage. The storage shim swaps local JSON for cloud storage; the agent file does not change. |
| 3 | **Nervous System** | Copilot Studio / Teams | Governed, published, in front of real users. |

An **agent** is one `.py` file: a docstring is the README, a `__manifest__` dict is the
metadata, a class inherits `BasicAgent`, and `perform(**kwargs)` returns a `str`. That
constraint is the reason any of this is portable.

Two public catalogs feed it:

- **RAR** (RAPP Agent Registry) — 200+ single-file agents with votes, user scores and
  AI critic scores. `rapp search`, `rapp agents install`.
- **RAPPstore** — converged **rapplications** (multi-persona pipelines collapsed into
  one file) and **senses** (translations of a response into another mode: haiku, TLDR,
  ELI5). `rapp store list`, `rapp store install`.

---

## STEP 1 — ALWAYS START WITH doctor

Never assume the environment. The first tool call of any RAPP task is:

```bash
python3 "$SKILL_DIR/scripts/rapp.py" doctor
```

It checks every tier and prints a fix line for anything broken. Read the verdict before
doing anything else:

- **healthy** — proceed with what the user asked.
- **warnings only** — proceed, but mention the warning if it touches the task.
- **failing** — fix the named blocker first. The fix line is in the output; use it. Do
  not work around a failing check by improvising.

`--deep` adds a live chat round-trip and samples catalog links — use it when the user
reports something is broken rather than on every run. `--postmortem` reads what the
last run actually did, which is the right first move when the user says "that didn't
work."

**Never diagnose from memory.** If a user reports a problem, run `doctor` and report
what it says. The engine knows the current state; you do not.

---

## STEP 2 — ROUTE THE REQUEST

| The user wants | Command |
|----------------|---------|
| To get started from nothing | `install` → `up` → `doctor` |
| To know if it is working | `doctor`, or `status` for a one-liner |
| To start / stop it | `up` / `down` |
| An agent that does X | `search X`, then `agents install <@publisher/slug>` |
| A rapplication or a sense | `store list`, then `store install <id> [--sense]` |
| To see what is loaded | `agents list` |
| To actually use it | `chat "…"` |
| To know whether an agent works | `test <file-or-@publisher/slug>` |
| Convert `agent.py` into an Agent Skill | Use sibling `rapp-agent-converter`: `convert <agent.py> --to skill` |
| Convert `SKILL.md` into `agent.py` | Use sibling `rapp-agent-converter`: `convert <SKILL.md> --to agent` |
| To understand the ecosystem | `map` |
| To know where a build stands | `tiers` |
| "Where does the AI's memory live?" | `memory` |

Add `--json` to any `scripts/rapp.py` command when you need to parse rather
than relay. The sibling converter has its own CLI and does not accept this
flag.

---

## The commands

### install — get a brainstem

```bash
python3 "$SKILL_DIR/scripts/rapp.py" install
```

Runs **the canonical installer one-liner**, the same one a human runs from the install
page — `curl -fsSL https://kody-w.github.io/rapp-installer/install.sh | bash` on
macOS/Linux, the PowerShell equivalent on Windows. It does not reimplement install.

Prerequisites are `git`, `gh`, and Python 3.11+; `doctor` names any that are missing.
The user needs a GitHub account and `gh auth login` — nothing else, no API keys.

`--repair` re-runs it over an existing install. `--dry-run` prints the one-liner
without executing, which is the polite thing to do when a user has not yet agreed to
run a remote script.

### up / down / status

`up` starts the brainstem on its own interpreter and waits for `/health` to answer.
`status` is the one-line liveness check. `down` stops it.

### search — find an agent in RAR

```bash
python3 "$SKILL_DIR/scripts/rapp.py" search "meeting notes"
python3 "$SKILL_DIR/scripts/rapp.py" search --category devtools --publisher @kody-w
```

Results are ranked by **critic score**, then votes, then downloads, and each row shows
its verdict badge (`✦ Certified` / `● Fresh` / `◯ Rotten` / `– unrated`). Those scores
come from a panel that actually executes each agent, so treat `◯ Rotten` as a real
warning and say so rather than installing silently.

### agents — list, install, test, remove

```bash
python3 "$SKILL_DIR/scripts/rapp.py" agents list
python3 "$SKILL_DIR/scripts/rapp.py" agents install @rapp/learn_new
python3 "$SKILL_DIR/scripts/rapp.py" agents remove learn_new_agent.py
```

`install` downloads the file, **verifies its SHA-256 against the registry**, and
hot-loads it into the running brainstem — no restart. If the brainstem is not running,
or with `--to-disk`, it writes to the agents directory instead. A digest mismatch
aborts the install; never bypass that.

### store — rapplications and senses

```bash
python3 "$SKILL_DIR/scripts/rapp.py" store list
python3 "$SKILL_DIR/scripts/rapp.py" store install bookfactory
python3 "$SKILL_DIR/scripts/rapp.py" store install haiku --sense
```

Rapplications install like agents (verified, hot-loaded). Senses install to the
brainstem's `senses/` directory and are auto-discovered on the next chat request.
Gated rapplications live in a private repo and 404 by design for an unauthenticated
caller — the engine says so explicitly and honours `GITHUB_TOKEN`.

### chat — actually use it

```bash
python3 "$SKILL_DIR/scripts/rapp.py" chat "summarize what you remember about me"
```

Sends a turn and returns the reply plus the tool trace. When the trace is non-empty the
model chose a tool on its own — that is the signal an agent is genuinely wired in, and
it is worth reporting. Use `--session <id>` to continue a conversation.

### test — prove an agent works

```bash
python3 "$SKILL_DIR/scripts/rapp.py" test ~/.brainstem/src/rapp_brainstem/agents/foo_agent.py
```

Loads the file **through the brainstem's own loader** and calls `perform()` for real
with arguments synthesized from the agent's own parameter schema. It runs in a
subprocess, in a throwaway working directory, with a timeout, because agent code is
third-party code. Reports load failures, exceptions, and contract violations
(a `perform()` that does not return a `str`).

Reading an agent's source is not testing it. Run this before telling a user an agent
works.

### Agent Skill conversion — use the sibling skill

This package ships `skills/rapp-agent-converter/` beside this skill. It is the exact
converter submitted to the CAT Agent Skills gallery and is the only conversion
implementation in this repository.

```bash
python3 "$SKILL_DIR/../rapp-agent-converter/scripts/toast.py" \
  convert path/to/foo_agent.py --to skill -o out/SKILL.md
python3 "$SKILL_DIR/../rapp-agent-converter/scripts/toast.py" \
  convert out/SKILL.md --to agent
python3 "$SKILL_DIR/../rapp-agent-converter/scripts/toast.py" \
  roundtrip path/to/foo_agent.py
```

The skill projection is a pair: `SKILL.md` plus a byte-exact linked agent file.
Never hand-transform either direction and never add conversion code to `rapp.py`.
Follow the sibling skill's `SKILL.md` for restoration, drift, and host-tier rules.

### memory — the filesystem answer

```bash
python3 "$SKILL_DIR/scripts/rapp.py" memory
python3 "$SKILL_DIR/scripts/rapp.py" memory backup
```

State lives at `~/.brainstem`. You can point at it, back it up, and delete it. When
someone asks where their AI's memory lives, this is the answer — a path, not a policy.

### map / tiers

`map` prints which repo owns which layer. `tiers` reports where the current machine
stands across all three, so you can tell a user what is actually blocking a promotion.

---

## Rules

**Report what the engine reported.** Its output is grounded in the live system. Do not
paraphrase a failure into something more optimistic, and do not present a warning as
success.

**Never invent a repair.** Every failing check carries a fix line. Use it verbatim. If
none fits, say the check failed and what it said — do not improvise shell surgery
inside `~/.brainstem`.

**Never claim entitlement.** The brainstem reaches models through **the GitHub Copilot
CLI (the preferred backend)**. Name the tool. Do not tell a user their access is
"unlimited", "free", or "included" — whatever access their account has is between them
and GitHub, and this skill makes no claim about it.

**Integrity is not optional.** Agent installs are SHA-256 verified against the catalog.
A mismatch is a stop, not a warning to route around.

**Conversion has one authority.** The sibling `rapp-agent-converter` skill is vendored
as a complete skill. Do not reproduce its parser, capsule, linked-pair, or restoration
logic in this skill's engine.

**Ask before installing to a machine.** `install` runs a remote script. Unless the user
has clearly asked to install, show them `--dry-run` output first and let them agree.

**Third-party code is third-party code.** `test` sandboxes it. Do not run a registry
agent by importing it into your own process.

**Tier 2 and Tier 3 use the user's own subscriptions.** Azure and Microsoft 365 cost
money and need permissions. Never provision on someone's behalf without asking.

---

## Worked flow — zero to a working agent

```bash
python3 "$SKILL_DIR/scripts/rapp.py" doctor          # what is missing
python3 "$SKILL_DIR/scripts/rapp.py" install         # the canonical one-liner
python3 "$SKILL_DIR/scripts/rapp.py" up              # start it
python3 "$SKILL_DIR/scripts/rapp.py" doctor --deep   # prove the model answers
python3 "$SKILL_DIR/scripts/rapp.py" search notes    # find something useful
python3 "$SKILL_DIR/scripts/rapp.py" agents install @kody-w/context_memory_agent
python3 "$SKILL_DIR/scripts/rapp.py" chat "what tools do you have?"
```

The last command should show the newly installed agent in the tool list. If it does
not, run `doctor --deep` and report what it says.

## Reference

- `references/tiers.md` — what each tier costs, needs, and gives you; the promotion path
- `references/agent-contract.md` — how to write and publish a single-file agent
- `references/troubleshooting.md` — symptom → check → fix, keyed to `doctor` output
