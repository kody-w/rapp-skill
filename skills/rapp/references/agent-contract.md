# The single-file agent contract

Every RAPP agent is **one `.py` file**. No manifest beside it, no README, no package
directory. The file is the package:

1. A **docstring** — serves as the documentation
2. A **`__manifest__` dict** — serves as the package metadata (extracted by AST, never
   executed)
3. A **class inheriting `BasicAgent`**
4. A **`perform(**kwargs)` method that returns a `str`**

That constraint is the reason an agent is portable across all three tiers and installable
by a single verified download.

---

## Minimum viable agent

```python
"""
Weather Agent

Returns a plain-language weather summary for a city. Uses the OPENWEATHER_KEY
environment variable; without it, returns an explanatory message rather than crashing.
"""

from agents.basic_agent import BasicAgent
import os

__manifest__ = {
    "schema": "rapp-agent/1.0",
    "name": "@yourname/weather",
    "version": "1.0.0",
    "display_name": "Weather",
    "description": "Plain-language weather summary for a city.",
    "author": "Your Name",
    "tags": ["weather", "demo"],
    "category": "integrations",
    "quality_tier": "community",
    "requires_env": ["OPENWEATHER_KEY"],
    "dependencies": ["@rapp/basic_agent"],
}


class Weather(BasicAgent):
    def __init__(self):
        self.name = "Weather"
        self.metadata = {
            "name": self.name,
            "description": __manifest__["description"],
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City to report on"},
                },
                "required": ["city"],
            },
        }
        super().__init__(name=self.name, metadata=self.metadata)

    def perform(self, **kwargs) -> str:
        city = kwargs.get("city", "").strip()
        if not city:
            return "No city given. Pass a city name."
        key = os.environ.get("OPENWEATHER_KEY")
        if not key:
            return "OPENWEATHER_KEY is not set, so I can't reach the weather service."
        return f"Weather for {city}: …"
```

---

## Rules that are actually enforced

| Rule | Why it exists |
|------|---------------|
| `perform()` returns a `str`, always | The tool layer serializes the return value. Anything else breaks the turn. |
| No network calls in `__init__()` | Constructors run at load time for every agent. A slow one delays every request. |
| Secrets via `os.environ.get()`, declared in `requires_env` | So a reader can see what an agent needs without running it. Never hardcode. |
| Missing env vars degrade gracefully | Return an explanatory string; do not raise. A crash takes out the request. |
| `display_name` matches `self.name` | The registry and the tool list must agree. |
| Filenames end `_agent.py`, snake_case | Auto-discovery globs for it. Dashes are rejected. |
| Don't hardcode model names | The platform selects the model. |

`rapp test <file>` checks the ones that can be checked mechanically: that it loads,
that `perform()` runs, and that it returns a `str`.

---

## Senses are not agents

A **sense** is a translation of the response into another mode of expression — haiku,
TLDR, ELI5, emoji. It is a `*_sense.py` file, it installs to the brainstem's `senses/`
directory rather than `agents/`, and it is auto-discovered on each chat request with no
restart. Senses declare a `slot` and a `delimiter`.

```bash
rapp store list                       # senses are listed separately
rapp store install haiku --sense
```

---

## Rapplications

A **rapplication** is a multi-persona pipeline authored across several files and then
*collapsed* into one singleton `.py` file. From the brainstem's point of view it is
still just an agent — one file, one `perform()`. From the author's point of view it is a
whole workflow (for example a five-persona content pipeline in a single call).

They live in RAPPstore with a `singleton_url` and a `singleton_sha256`, and install
exactly like an agent:

```bash
rapp store list
rapp store install bookfactory
```

---

## Publishing

**To RAR** — open an issue on `kody-w/RAR` with the agent code; CI validates the
manifest, runs the contract tests, and rebuilds `registry.json`. Agents may submit
themselves; no human owner is required.

**To RAPPstore** — author with the multi-file source pattern, run the convergence loop
until it collapses cleanly, build the singleton, and submit a PR adding an entry to
`index.json`. Required fields: `id`, `name`, `version`, `summary`, `manifest_name`,
`singleton_url`.

Both catalogs publish a SHA-256 for every file, and every installer verifies it. If you
change the file, the digest changes, and the catalog entry must be updated with it —
that is a feature, not friction.

---

## Before you publish

```bash
rapp test path/to/your_agent.py
```

An agent that reads beautifully and does not run is not a good agent. The registry runs
an AI critic panel that executes submissions and scores them; a silent failure or an
agent that ignores its own arguments will be caught and published as `◯ Rotten`. Test
it yourself first.
