# Working on rapp-skill

This repo is a **skill**, not a product. It ties the existing RAPP ecosystem together
behind one command surface an AI can drive. The most important rule follows from that.

## Rule 1 — reimplement nothing

The installer, the brainstem, RAR and RAPPstore are upstream and own their own truth.
This repo calls them.

- Install runs the canonical one-liner from the install page. Do not fork it.
- Catalogs are read from their published JSON. Do not vendor a copy.
- Agent loading uses the brainstem's own loader. Do not write a second one.
- Agent Skill conversion uses `skills/rapp-agent-converter/` verbatim. Do not add
  capsule, projection, or restore logic to `rapp.py`.

Two tests enforce this (`test_install_uses_the_canonical_one_liner`,
`test_catalogs_are_the_public_ones`). If a change makes them fail, the change is
probably wrong.

## Rule 2 — never claim entitlement

The brainstem reaches models through **the GitHub Copilot CLI (the preferred backend)**.
Name the tool. Never write "unlimited", "infinite", or "free tokens", and never
characterize what a user's subscription includes. A test and a CI job both enforce this.

## Rule 3 — the engine reports, the AI relays

`doctor` prints a fix line for every failing check. SKILL.md tells the model to use it
verbatim. So: **every check that can fail must carry a `fix`.**
`test_doctor_names_a_fix_for_every_failure` enforces it.

## Rule 4 — third-party code is third-party code

Registry agents are arbitrary Python from strangers. `rapp test` runs them in a
subprocess, in a throwaway cwd, under a timeout. Never import an agent into the engine's
own process.

## Rule 5 — integrity is a stop, not a warning

Installs verify SHA-256 against the catalog. A mismatch aborts. Do not add a
`--force-install` that skips it.

## Layout

| Path | Role |
|------|------|
| `skills/rapp/SKILL.md` | The contract the model reads. Behavior changes start here. |
| `skills/rapp/scripts/rapp.py` | The engine. One file, stdlib only, no dependencies. |
| `skills/rapp/references/` | Loaded on demand, not on every run. |
| `skills/rapp-agent-converter/SKILL.md` | The converter contract, vendored as a complete sibling skill. |
| `skills/rapp-agent-converter/scripts/toast.py` | The only Agent Skill conversion engine in this repository. |
| `tests/` | Offline contract tests. |

Keep both engines dependency-free. They have to run on a machine that has just been
handed the package and nothing else.

## Adding a command

1. Write the `cmd_*` function. Return 0 on success, 1 on a real failure, 2 on misuse.
2. Register it with `add("name", ...)` so it inherits the global flags.
3. Support `--json` through `emit(args, report, human)`.
4. Call `save_run()` so `doctor --postmortem` can see it.
5. Document it in SKILL.md's routing table — `test_every_documented_command_is_registered`
   checks the two stay in sync.

## Versioning

`skills/rapp/SKILL.md` frontmatter is the source of truth. Every plugin manifest must
match it; CI fails the build otherwise.

## Tests

```bash
python -m pytest tests/ -q
```

Offline by design. Anything needing a live brainstem is skipped, never failed.
