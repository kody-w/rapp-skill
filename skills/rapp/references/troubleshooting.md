# Troubleshooting

Symptom → what to run → what it means. Always start with `rapp doctor`; it prints a fix
line for every failing check, and those fix lines are authoritative. Use them verbatim
rather than improvising.

`rapp doctor --postmortem` reads what the *last* run actually did, which is the right
first move when a user says "that didn't work."

---

## "It won't install"

```bash
rapp doctor        # which prerequisite is missing
rapp install --dry-run
```

`install` runs the canonical one-liner from the install page. It does not reimplement
anything, so an install failure is almost always a missing prerequisite:

| Check fails | Fix |
|-------------|-----|
| `python` | Python 3.11+ required. macOS: `brew install python@3.11` |
| `git` | macOS: `xcode-select --install` |
| `gh` | macOS: `brew install gh` |
| `gh auth` | `gh auth login` |

On Windows the PowerShell installer auto-installs Python, Git and the GitHub CLI via
winget — skip the manual prerequisite hunt there.

---

## "The brainstem isn't responding"

```bash
rapp status
rapp up
```

If `up` reports it started but nothing answers, read the log it names
(`~/.brainstem/logs/brainstem.out`). Common causes: the port is already taken by an
older instance (`rapp down` first), or a broken agent file is crashing the boot.

A single malformed agent should be quarantined rather than fatal — if it is not, the
log names the file. Move it out of the agents directory and restart.

---

## "It answers, but it won't use my agent"

```bash
rapp agents list       # is the file even loaded?
rapp chat "what tools do you have?"
```

Three different failures look identical from the outside:

1. **The file did not load.** It will not appear in `agents list`. Run `rapp test <file>`
   to see the actual exception.
2. **It loaded but was quarantined.** A tool-illegal name or malformed `metadata` gets
   the class skipped so it cannot break every `/chat`. The brainstem log names it.
3. **It loaded fine but the model does not pick it.** The tool name, description, or
   parameter schema does not make its purpose obvious. This is a writing problem, not a
   loading problem — improve the `description` in `metadata`.

`rapp test` distinguishes 1 and 2 from 3, because it calls `perform()` directly rather
than hoping the model chooses it.

---

## "The model isn't answering"

```bash
rapp doctor --deep     # does a live chat round-trip
```

Check, in this order:

- `brainstem auth` — is there a working GitHub token? The engine reads the real token
  exchange result, not the device-flow poll.
- `model` — is one selected? Open the brainstem UI and pick one.
- `copilot cli` — is the GitHub Copilot CLI available to `gh`? It is the preferred
  backend.

If the token exchange fails, sign in again through the brainstem UI at
`http://127.0.0.1:7071`.

---

## "An agent install failed the integrity check"

```
✗ integrity check failed for @publisher/slug
```

The bytes served did not match the SHA-256 the catalog published. **Do not bypass
this.** Either the catalog is stale or the file changed. Report it; do not install the
file by hand to get around the check.

---

## "A catalog entry 404s"

```
✗ 404 for https://… — the catalog entry points at a path that is not in the
  repository (stale catalog entry — report it upstream)
```

Two causes, and the message distinguishes them:

- **Stale entry** — the catalog outlived the file. Report it upstream; nothing to fix
  locally.
- **Gated entry** — a private rapplication 404s by design for an unauthenticated
  caller. Set `GITHUB_TOKEN` to a PAT with read access to the declared private repo and
  retry.

`rapp doctor --deep` samples catalog links and reports which entries do not resolve.

---

## "Where did my data go?"

```bash
rapp memory
rapp memory backup
```

Everything is under `~/.brainstem`. Nothing is held anywhere you cannot reach. That is
the answer to the compliance question, and it is a path rather than a policy.

---

## Reporting a problem well

Include the output of:

```bash
rapp doctor --json
rapp doctor --postmortem
```

Between them they carry the environment, every check with its state, and what the last
command actually did.
