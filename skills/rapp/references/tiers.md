# The three tiers

The same single `.py` file runs at every tier. That is the whole design — the rewrite
between prototype and production is where most AI projects die, so RAPP removes it.

```
Tier 1  Brainstem       your laptop          build and prove it
Tier 2  Spinal Cord     Azure Functions      make it always-on
Tier 3  Nervous System  Copilot Studio       put it in front of people
```

---

## Tier 1 — Brainstem

**Where:** your machine, at `~/.brainstem`.
**Needs:** Python 3.11+, `git`, `gh`, and a GitHub account (`gh auth login`).
**Costs:** nothing beyond what you already have. The runtime reaches models through
the GitHub Copilot CLI, which is the preferred backend, so there are no API keys to
provision and no second vendor to onboard. Whatever Copilot access your account has is
between you and GitHub.

**What you get:**

- The agent loop — tools, conversation, and a model, running locally
- Memory as JSON on disk. Not a vendor feature with a retention window; a file you can
  point at, back up, diff, and delete
- Hot-loading — drop an agent file in and it is available on the next request
- Auto-discovery of `*_agent.py` files and `*_sense.py` senses
- A `soul.md` identity file that shapes how it behaves

**Check it:** `rapp doctor` · **Start it:** `rapp up` · **Use it:** `rapp chat "..."`

This is where an agent should be born and proven. Everything else is distribution.

---

## Tier 2 — Spinal Cord

**Where:** Azure Functions, in your own subscription.
**Needs:** the Azure CLI (`az`) and Azure Functions Core Tools (`func`). `rapp doctor`
reports whether both are present.
**Costs:** your Azure bill. Nobody else's.

**What changes:** the storage shim swaps local JSON for cloud storage. **The agent file
does not change.** That is the promotion — not a port.

**What you get:** always-on execution, persistent storage that outlives your laptop,
and an HTTP surface other systems can call.

Reach for this when an agent has proven itself locally and something other than you
needs to call it.

---

## Tier 3 — Nervous System

**Where:** Copilot Studio, Teams, Microsoft 365.
**Needs:** the Power Platform CLI (`pac`) and a tenant you are allowed to publish into.
**Costs:** your Microsoft 365 / Power Platform licensing.

**What you get:** governance, channels, and an audience. Colleagues use the agent where
they already work, and your platform team gets something they already know how to
administer.

This is the hero destination. The local brainstem is the launchpad, not the parking
spot — an agent that never leaves Tier 1 only ever helps one person.

---

## The promotion path

1. **Build on Tier 1** until the agent actually does the thing. Use `rapp test` to
   prove it runs, not just that it reads well.
2. **Promote to Tier 2** when something other than you needs to call it, or it needs to
   run while your laptop is shut.
3. **Publish to Tier 3** when people other than you need to use it.

Do not skip to Tier 3 with an unproven agent. The reason this path exists is so that
what you publish is something you have already watched work.

## What blocks a promotion

`rapp tiers` reports where the current machine stands. A tier reads **blocked** when a
required tool is missing or a check failed; the `doctor` output names which one.

Tier 2 and Tier 3 spend money and need permissions in someone's tenant. Never provision
either on a user's behalf without asking first.
