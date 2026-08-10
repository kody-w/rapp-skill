#!/usr/bin/env python3
"""
rapp.py — one engine for the whole RAPP ecosystem.

The brainstem is a local Flask server that turns a GitHub Copilot CLI session into
a tool-using agent runtime. This engine is the thing an AI harness drives to install
it, keep it healthy, load agents into it, talk to it, and promote what works to
Azure and Copilot Studio.

Every command prints a compact human report by default and structured JSON with
--json, so a harness can either relay the text or parse the result.

Commands
    doctor          health check across every tier; --postmortem reads the last run
    install         install or repair the global brainstem
    status          one-line liveness for the running brainstem
    up / down       start and stop the local brainstem
    agents          list, install, export, remove agents
    search          search the RAPP Agent Registry (RAR)
    chat            send a turn to the brainstem and read the tool trace
    test            load an agent and actually run it
    map             the ecosystem: which repo owns which layer
    tiers           where a build stands across laptop -> Azure -> Copilot Studio
    memory          inspect, back up, and clear what the brainstem remembers

Exit codes: 0 healthy or succeeded, 1 a real failure, 2 misuse.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "1.1.0"

HOME = Path.home()
BRAINSTEM_HOME = Path(os.environ.get("RAPP_HOME", HOME / ".brainstem"))
BRAINSTEM_SRC = BRAINSTEM_HOME / "src" / "rapp_brainstem"
BRAINSTEM_VENV = BRAINSTEM_HOME / "venv"
DEFAULT_URL = os.environ.get("BRAINSTEM_URL", "http://127.0.0.1:7071")
STATE_DIR = BRAINSTEM_HOME / "rapp-skill"
LAST_RUN = STATE_DIR / "last_run.json"

INSTALL_SH = "https://kody-w.github.io/rapp-installer/install.sh"
INSTALL_PS1 = "https://raw.githubusercontent.com/kody-w/rapp-installer/main/install.ps1"
RAR_REGISTRY = "https://raw.githubusercontent.com/kody-w/RAR/main/registry.json"
RAR_METRICS = "https://raw.githubusercontent.com/kody-w/RAR/main/state/metrics.json"
RAR_CRITIC = "https://raw.githubusercontent.com/kody-w/RAR/main/state/critic_reviews.json"
RAR_RAW = "https://raw.githubusercontent.com/kody-w/RAR/main"
# RAPP_Store is the second catalog: converged single-file "rapplications" and
# "senses" (response translations). Different shape from RAR, same install idea.
STORE_INDEX = "https://raw.githubusercontent.com/kody-w/RAPP_Store/main/index.json"

OK, WARN, BAD, INFO = "ok", "warn", "fail", "info"
MARK = {OK: "✓", WARN: "!", BAD: "✗", INFO: "·"}

# The ecosystem, as owned repos. `map` renders this; `doctor` uses the tier column.
ECOSYSTEM = [
    ("rapp-installer", 1, "The canonical installer — one line to a running brainstem",
     "https://github.com/kody-w/rapp-installer"),
    ("rapp-brainstem", 1, "The local agent engine itself (Tier 1)",
     "https://github.com/kody-w/rapp-brainstem"),
    ("RAR", 1, "RAPP Agent Registry — single-file agents, votes, critic scores",
     "https://github.com/kody-w/RAR"),
    ("RAPP_Store", 1, "RAPPstore — converged rapplications and senses",
     "https://github.com/kody-w/RAPP_Store"),
    ("rapp-agents", 1, "Drop-in agent stack for any brainstem",
     "https://github.com/kody-w/rapp-agents"),
    ("rapp-twin", 1, "Twin in residence — a project-local AI twin (.twin/)",
     "https://github.com/kody-w/rapp-twin"),
    ("rapp-keyring", 1, "On-device credential broker — agents use a secret without seeing it",
     "https://github.com/kody-w/rapp-keyring"),
    ("vbrainstem", 1, "Browser-native brainstem runtime (Pyodide)",
     "https://github.com/kody-w/vbrainstem"),
    ("rapp-spinal-cord", 2, "The Azure path (Tier 2) — always-on, persistent storage",
     "https://github.com/kody-w/rapp-spinal-cord"),
    ("rapp-base", 2, "Hosted RAPP Base reference deployment",
     "https://github.com/kody-w/rapp-base"),
    ("rapp-hippocampus", 2, "Memory tier of the platform",
     "https://github.com/kody-w/rapp-hippocampus"),
    ("rapp-nervous-system", 3, "The M365 / Copilot Studio path (Tier 3)",
     "https://github.com/kody-w/rapp-nervous-system"),
    ("rapp-cortex", 3, "Higher-order orchestration across agents",
     "https://github.com/kody-w/rapp-cortex"),
    ("rapp-sdk", 0, "Build on the platform",
     "https://github.com/kody-w/rapp-sdk"),
    ("rapp-cli", 0, "Command-line control",
     "https://github.com/kody-w/rapp-cli"),
    ("rapp-docs", 0, "Documentation",
     "https://github.com/kody-w/rapp-docs"),
    ("rapp-map", 0, "Which repo houses which part of the spec",
     "https://github.com/kody-w/rapp-map"),
    ("rapp-flight-deck", 0, "Install any pre-release ring from one page",
     "https://github.com/kody-w/rapp-flight-deck"),
    ("rapp-brainstem-walkthrough", 0, "The 14-step guided tour, runnable in a browser",
     "https://github.com/kody-w/rapp-brainstem-walkthrough"),
]

TIERS = {
    1: ("Brainstem", "Your laptop. Local agent loop, memory on disk, no keys."),
    2: ("Spinal Cord", "Azure Functions. Always-on, cloud storage, same agent file."),
    3: ("Nervous System", "Copilot Studio / Teams. Governed, published, in front of users."),
}


# ─────────────────────────────────────────────────────────── plumbing

def log(msg=""):
    print(msg, file=sys.stderr)


def run(cmd, timeout=60, cwd=None, env=None):
    """Run a command. Never raises — a failure is a result."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=cwd, env=env)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    except Exception as e:  # pragma: no cover - defensive
        return 1, "", f"{type(e).__name__}: {e}"


def have(binary):
    return shutil.which(binary) is not None


def api(path, method="GET", payload=None, timeout=180, url=None, raw_body=None, ctype=None):
    """Call the local brainstem. Returns (ok, data_or_error)."""
    base = url or DEFAULT_URL
    data = raw_body
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(f"{base}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
        try:
            return True, json.loads(body)
        except json.JSONDecodeError:
            return True, {"raw": body[:2000]}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400] if hasattr(e, "read") else ""
        return False, {"error": f"HTTP {e.code}", "detail": detail}
    except Exception as e:
        return False, {"error": f"{type(e).__name__}", "detail": str(e)[:200]}


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": f"rapp-skill/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def brainstem_python():
    """The brainstem's own interpreter — it has flask and the agent deps."""
    for cand in (BRAINSTEM_VENV / "bin" / "python", BRAINSTEM_VENV / "Scripts" / "python.exe"):
        if cand.exists():
            return str(cand)
    return sys.executable


def save_run(kind, payload):
    """Record what the last command did, for `doctor --postmortem`.

    Best-effort by design: an unwritable state directory must never take down the
    command the user actually asked for.
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_RUN.write_text(json.dumps(
            {"command": kind, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "result": payload}, indent=1) + "\n")
    except OSError:
        pass


def emit(args, report, human):
    if getattr(args, "json", False):
        print(json.dumps(report, indent=1))
    else:
        print(human)


# ─────────────────────────────────────────────────────────── doctor

def check(name, state, detail, fix=None, tier=None):
    return {"check": name, "state": state, "detail": detail, "fix": fix, "tier": tier}


def doctor_checks(url=DEFAULT_URL, deep=False):
    out = []

    # Tier 0 — the prerequisites
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok_py = sys.version_info >= (3, 11)
    out.append(check("python", OK if ok_py else BAD, f"Python {py}",
                     None if ok_py else "Install Python 3.11+ — macOS: brew install python@3.11", 0))

    for tool, fix in (("git", "macOS: xcode-select --install"),
                      ("gh", "macOS: brew install gh — then: gh auth login")):
        out.append(check(tool, OK if have(tool) else BAD,
                         "installed" if have(tool) else "not found", None if have(tool) else fix, 0))

    if have("gh"):
        rc, so, se = run(["gh", "auth", "status"], timeout=20)
        signed = rc == 0
        who = ""
        if signed:
            rc2, so2, _ = run(["gh", "api", "user", "--jq", ".login"], timeout=20)
            who = so2 if rc2 == 0 else ""
        out.append(check("gh auth", OK if signed else BAD,
                         f"signed in as {who}" if who else ("signed in" if signed else "signed out"),
                         None if signed else "Run: gh auth login", 0))
        # The Copilot CLI is the preferred backend for the brainstem's model calls.
        rc3, so3, se3 = run(["gh", "copilot", "--version"], timeout=30)
        avail = rc3 == 0
        out.append(check("copilot cli", OK if avail else WARN,
                         (so3.splitlines()[0][:60] if so3 else "available") if avail
                         else "not available on this gh install",
                         None if avail else "Install the GitHub Copilot CLI extension: gh extension install github/gh-copilot", 0))

    # Tier 1 — the brainstem itself
    installed = BRAINSTEM_SRC.exists()
    ver = ""
    vf = BRAINSTEM_SRC / "VERSION"
    if vf.exists():
        try:
            ver = vf.read_text().strip()
        except OSError:
            pass
    out.append(check("brainstem installed", OK if installed else BAD,
                     f"{BRAINSTEM_SRC} (v{ver})" if ver else (str(BRAINSTEM_SRC) if installed else "not installed"),
                     None if installed else "Run: rapp install", 1))

    if installed:
        venv_ok = BRAINSTEM_VENV.exists()
        out.append(check("brainstem venv", OK if venv_ok else WARN,
                         str(BRAINSTEM_VENV) if venv_ok else "no venv — using system python",
                         None if venv_ok else "Run: rapp install --repair", 1))
        adir = BRAINSTEM_SRC / "agents"
        n = len(list(adir.glob("*_agent.py"))) if adir.exists() else 0
        out.append(check("agent files", OK if n else WARN, f"{n} agent file(s) in {adir}",
                         None if n else "Install one: rapp agents install @rapp/learn_new", 1))
        soul = BRAINSTEM_SRC / "soul.md"
        out.append(check("soul.md", OK if soul.exists() else WARN,
                         "present" if soul.exists() else "missing — the agent has no identity",
                         None if soul.exists() else "Create soul.md in the brainstem directory", 1))

    ok, health = api("/health", timeout=8, url=url)
    out.append(check("brainstem running", OK if ok else WARN,
                     f"responding at {url}" if ok else f"not responding at {url}",
                     None if ok else "Run: rapp up", 1))

    if ok:
        ok_a, agents = api("/agents", timeout=20, url=url)
        if ok_a and isinstance(agents, dict):
            files = agents.get("files") or []
            loaded = sorted({a for f in files for a in (f.get("agents") or [])})
            out.append(check("agents loaded", OK if loaded else WARN,
                             f"{len(loaded)} loaded: {', '.join(loaded[:6])}"
                             + (" …" if len(loaded) > 6 else "") if loaded else "none loaded",
                             None if loaded else "Check for quarantined agents in the brainstem log", 1))
        ok_m, models = api("/models", timeout=25, url=url)
        if ok_m:
            cur = (models or {}).get("current") or (models or {}).get("model") or ""
            avail = (models or {}).get("models") or (models or {}).get("available") or []
            out.append(check("model", OK if cur else WARN,
                             f"{cur}" + (f" ({len(avail)} available)" if avail else "")
                             if cur else "no model selected",
                             None if cur else "Sign in through the brainstem UI at " + url, 1))
        # /login/status is the device-flow poll ({"pending": bool}), NOT an auth
        # indicator — reading it as one reports a signed-in brainstem as signed out.
        # /debug/auth carries the real token exchange result.
        ok_l, auth = api("/debug/auth", timeout=20, url=url)
        if ok_l:
            authed = bool((auth or {}).get("exchange_ok") and (auth or {}).get("github_token_exists"))
            prefix = (auth or {}).get("github_token_prefix", "")
            out.append(check("brainstem auth", OK if authed else BAD,
                             f"token exchange ok ({str(prefix)[:8]}…)" if authed else "no working GitHub token",
                             None if authed else f"Open {url} and sign in with GitHub", 1))
        if deep:
            ok_c, chat = api("/chat", "POST",
                             {"user_input": "Reply with the single word: pong"}, timeout=180, url=url)
            reply = (chat or {}).get("response", "") if ok_c else ""
            out.append(check("chat round-trip", OK if reply else BAD,
                             f"model replied ({len(reply)} chars)" if reply
                             else f"no reply: {(chat or {}).get('error', 'unknown')}",
                             None if reply else "Check model selection and Copilot CLI availability", 1))

    # Memory
    mem_root = BRAINSTEM_HOME
    out.append(check("memory", OK if mem_root.exists() else WARN,
                     f"{mem_root}" if mem_root.exists() else "no ~/.brainstem yet",
                     None if mem_root.exists() else "Run: rapp install", 1))

    # Registry reachability
    reg = fetch(RAR_REGISTRY, timeout=25)
    n_agents = len((reg or {}).get("agents") or [])
    out.append(check("registry (RAR)", OK if reg else WARN,
                     f"{n_agents} agents available" if reg else "unreachable (offline?)",
                     None if reg else "Check network; the registry is a static file on GitHub Pages", 1))

    store = fetch(STORE_INDEX, timeout=25)
    if store:
        out.append(check("rappstore", OK,
                         f"{len(store.get('rapplications') or [])} rapplications, "
                         f"{len(store.get('senses') or [])} senses", None, 1))
    else:
        out.append(check("rappstore", WARN, "unreachable (offline?)", None, 1))
    if store and deep:
        broken = []
        for e in (store.get("rapplications") or [])[:6] + (store.get("senses") or [])[:3]:
            u = e.get("singleton_url") or e.get("url")
            if not u or e.get("access") == "private":
                continue
            try:
                req = urllib.request.Request(u, method="HEAD",
                                             headers={"User-Agent": f"rapp-skill/{VERSION}"})
                urllib.request.urlopen(req, timeout=15)
            except Exception:
                broken.append(e.get("id"))
        out.append(check("rappstore links", OK if not broken else WARN,
                         "sampled entries resolve" if not broken
                         else f"{len(broken)} entry/entries 404: {', '.join(broken)}",
                         None if not broken else "Stale catalog entries — report upstream", 1))

    if installed:
        sdir = BRAINSTEM_SRC / "senses"
        n_s = len(list(sdir.glob("*_sense.py"))) if sdir.exists() else 0
        out.append(check("senses", OK if n_s else INFO,
                         f"{n_s} sense(s) installed" if n_s else "none installed (optional)",
                         None if n_s else "Try: rapp store install haiku --sense", 1))

    # Tier 2 / 3 — reported, never assumed
    az = have("az")
    out.append(check("azure cli", OK if az else INFO,
                     "installed" if az else "not installed (only needed for Tier 2)",
                     None if az else "macOS: brew install azure-cli", 2))
    func = have("func")
    out.append(check("functions core tools", OK if func else INFO,
                     "installed" if func else "not installed (only needed for Tier 2)",
                     None if func else "npm i -g azure-functions-core-tools@4", 2))
    pac = have("pac")
    out.append(check("pac cli", OK if pac else INFO,
                     "installed" if pac else "not installed (only needed for Tier 3)",
                     None if pac else "dotnet tool install --global Microsoft.PowerApps.CLI.Tool", 3))
    return out


def cmd_doctor(args):
    if args.postmortem:
        if not LAST_RUN.exists():
            print("No previous run recorded. Run a command first, then: rapp doctor --postmortem")
            return 1
        prev = json.loads(LAST_RUN.read_text())
        if args.json:
            print(json.dumps(prev, indent=1))
        else:
            print(f"Last run: {prev.get('command')} at {prev.get('at')}")
            print(json.dumps(prev.get("result"), indent=1)[:3000])
        return 0

    checks = doctor_checks(args.url, deep=args.deep)
    fails = [c for c in checks if c["state"] == BAD]
    warns = [c for c in checks if c["state"] == WARN]
    report = {"schema": "rapp-doctor/1.0", "version": VERSION, "url": args.url,
              "platform": platform.platform(), "checks": checks,
              "failed": len(fails), "warned": len(warns),
              "healthy": not fails}
    save_run("doctor", {"failed": len(fails), "warned": len(warns)})

    lines = [f"RAPP doctor · v{VERSION} · {platform.system()}", ""]
    by_tier = {}
    for c in checks:
        by_tier.setdefault(c.get("tier") if c.get("tier") is not None else 0, []).append(c)
    for tier in sorted(by_tier):
        label = {0: "Prerequisites", 1: "Tier 1 — Brainstem (local)",
                 2: "Tier 2 — Spinal Cord (Azure)", 3: "Tier 3 — Nervous System (Copilot Studio)"}[tier]
        lines.append(label)
        for c in by_tier[tier]:
            lines.append(f"  {MARK[c['state']]} {c['check']:<22} {c['detail']}")
            if c["fix"] and c["state"] in (BAD, WARN):
                lines.append(f"      fix: {c['fix']}")
        lines.append("")
    verdict = ("healthy" if not fails and not warns
               else f"{len(fails)} failing, {len(warns)} warning" if fails
               else f"{len(warns)} warning")
    lines.append(f"Verdict: {verdict}")
    if fails:
        lines.append("Blocked on: " + ", ".join(c["check"] for c in fails))
    emit(args, report, "\n".join(lines))
    return 1 if fails else 0


# ─────────────────────────────────────────────────────────── install / lifecycle

def cmd_install(args):
    if BRAINSTEM_SRC.exists() and not args.repair and not args.force:
        print(f"Brainstem already installed at {BRAINSTEM_SRC}")
        print("Use --repair to re-run the installer, or 'rapp doctor' to check it.")
        return 0

    if platform.system() == "Windows":
        cmd = ["powershell", "-NoProfile", "-Command", f"irm {INSTALL_PS1} | iex"]
        human = f"irm {INSTALL_PS1} | iex"
    else:
        cmd = ["bash", "-c", f"curl -fsSL {INSTALL_SH} | bash"]
        human = f"curl -fsSL {INSTALL_SH} | bash"

    if args.dry_run:
        print(f"Would run:\n  {human}")
        return 0

    if not have("gh"):
        print("The GitHub CLI is required first. Install it, then run: gh auth login")
        return 1

    log(f"· installing the brainstem via {human}")
    rc, so, se = run(cmd, timeout=args.timeout)
    tail = (so or se).splitlines()[-14:]
    report = {"installed": rc == 0, "exit_code": rc, "home": str(BRAINSTEM_HOME),
              "output_tail": tail}
    save_run("install", report)
    if rc != 0:
        emit(args, report, "Install failed.\n" + "\n".join(tail)
             + f"\n\nRun 'rapp doctor' to see which prerequisite is missing.")
        return 1
    emit(args, report, "\n".join(tail) + f"\n\n✓ Brainstem installed at {BRAINSTEM_HOME}\n"
         "Next: rapp up   then   rapp doctor --deep")
    return 0


def cmd_up(args):
    if not BRAINSTEM_SRC.exists():
        print("No brainstem installed. Run: rapp install")
        return 1
    ok, _ = api("/health", timeout=5, url=args.url)
    if ok:
        print(f"Already running at {args.url}")
        return 0
    entry = BRAINSTEM_SRC / "brainstem.py"
    logf = BRAINSTEM_HOME / "logs"
    logf.mkdir(parents=True, exist_ok=True)
    out = open(logf / "brainstem.out", "ab")
    proc = subprocess.Popen([brainstem_python(), str(entry)], cwd=str(BRAINSTEM_SRC),
                            stdout=out, stderr=out, start_new_session=True)
    for _ in range(args.wait):
        time.sleep(1)
        ok, _ = api("/health", timeout=3, url=args.url)
        if ok:
            print(f"✓ Brainstem up at {args.url} (pid {proc.pid})")
            print(f"  log: {logf / 'brainstem.out'}")
            return 0
    print(f"Started pid {proc.pid} but {args.url} did not answer within {args.wait}s.")
    print(f"Check the log: {logf / 'brainstem.out'}")
    return 1


def cmd_down(args):
    rc, so, _ = run(["pgrep", "-f", "brainstem.py"], timeout=15)
    pids = [p for p in so.split() if p.isdigit()]
    if not pids:
        print("No brainstem process found.")
        return 0
    for pid in pids:
        run(["kill", pid], timeout=10)
    print(f"✓ Stopped: {', '.join(pids)}")
    return 0


def cmd_status(args):
    ok, health = api("/health", timeout=8, url=args.url)
    if not ok:
        report = {"running": False, "url": args.url, "error": health}
        emit(args, report, f"✗ No brainstem at {args.url}. Run: rapp up")
        return 1
    ok_v, ver = api("/version", timeout=10, url=args.url)
    ok_a, agents = api("/agents", timeout=15, url=args.url)
    loaded = sorted({a for f in (agents or {}).get("files", []) for a in (f.get("agents") or [])}) if ok_a else []
    report = {"running": True, "url": args.url, "health": health,
              "version": ver if ok_v else None, "agents": loaded}
    v = (ver or {}).get("version") if ok_v else ""
    emit(args, report,
         f"✓ Brainstem up at {args.url}" + (f" (v{v})" if v else "")
         + f"\n  {len(loaded)} agent(s): {', '.join(loaded[:10])}" + (" …" if len(loaded) > 10 else ""))
    return 0


# ─────────────────────────────────────────────────────────── registry + agents

def load_registry():
    reg = fetch(RAR_REGISTRY)
    if not reg:
        return None, "registry unreachable"
    return reg, None


def cmd_search(args):
    reg, err = load_registry()
    if err:
        print(f"✗ {err}")
        return 1
    metrics = fetch(RAR_METRICS) or {}
    critic = (fetch(RAR_CRITIC) or {}).get("agents") or {}
    am = metrics.get("agent_metrics") or {}

    def norm(s):
        return "".join(ch if ch.isalnum() else "_" for ch in str(s or "").lower())

    critic_n = {norm(k): v for k, v in critic.items()}
    metrics_n = {norm(k): v for k, v in am.items()}

    q = " ".join(args.query).lower().strip()
    rows = []
    for a in reg.get("agents", []):
        hay = " ".join([str(a.get("name", "")), str(a.get("display_name", "")),
                        str(a.get("description", "")), " ".join(a.get("tags") or []),
                        str(a.get("category", "")), str(a.get("author", ""))]).lower()
        if q and not all(w in hay for w in q.split()):
            continue
        if args.category and a.get("category") != args.category:
            continue
        if args.publisher and not str(a.get("name", "")).startswith(args.publisher.rstrip("/") + "/"):
            continue
        k = norm(a.get("name"))
        c = critic_n.get(k) or {}
        m = metrics_n.get(k) or {}
        rows.append({
            "name": a.get("name"), "display_name": a.get("display_name"),
            "description": a.get("description"), "category": a.get("category"),
            "tier": a.get("quality_tier"), "file": a.get("_file"),
            "sha256": a.get("_sha256"), "lines": a.get("_lines"),
            "downloads": m.get("d", 0), "votes": m.get("s", 0),
            "critic_score": c.get("critic_score"), "user_score": c.get("user_score"),
            "verdict": c.get("state", "unrated"),
        })

    def sort_key(r):
        return (-(r["critic_score"] or -1), -(r["votes"] or 0), -(r["downloads"] or 0), r["name"])

    rows.sort(key=sort_key)
    rows = rows[: args.limit]
    report = {"query": q, "matches": len(rows), "agents": rows,
              "registry_agents": len(reg.get("agents", []))}
    save_run("search", {"query": q, "matches": len(rows)})

    if not rows:
        emit(args, report, f"No agents matched {q!r} across {len(reg.get('agents', []))} registry agents.")
        return 0
    lines = [f"{len(rows)} match(es) for {q!r} — of {len(reg.get('agents', []))} agents in RAR", ""]
    for r in rows:
        badge = {"certified": "✦ Certified", "fresh": "● Fresh",
                 "rotten": "◯ Rotten", "unrated": "– unrated"}.get(r["verdict"], "– unrated")
        score = f"{r['critic_score']}%" if r["critic_score"] is not None else "—"
        lines.append(f"  {r['display_name']}  ({r['name']})")
        lines.append(f"    {(r['description'] or '')[:96]}")
        lines.append(f"    {badge} critic {score} · votes {r['votes']:+d} · "
                     f"downloads {r['downloads']} · {r['category']} · {r['lines']} lines")
        lines.append("")
    lines.append("Install one:  rapp agents install <@publisher/slug>")
    emit(args, report, "\n".join(lines))
    return 0


def find_agent(name):
    reg, err = load_registry()
    if err:
        return None, err
    want = str(name).strip().lower()
    for a in reg.get("agents", []):
        if str(a.get("name", "")).lower() == want:
            return a, None
    # tolerate a bare slug
    for a in reg.get("agents", []):
        if str(a.get("name", "")).lower().split("/")[-1] == want.split("/")[-1]:
            return a, None
    return None, f"no agent named {name!r} in the registry"


def cmd_agents(args):
    action = args.action

    if action == "list":
        ok, data = api("/agents", timeout=20, url=args.url)
        if not ok:
            print(f"✗ brainstem not reachable at {args.url}. Run: rapp up")
            return 1
        files = (data or {}).get("files") or []
        report = {"files": files,
                  "loaded": sorted({a for f in files for a in (f.get("agents") or [])})}
        lines = [f"{len(files)} file(s) loaded in the brainstem", ""]
        for f in sorted(files, key=lambda x: x.get("filename", "")):
            names = ", ".join(f.get("agents") or []) or "(no agent class)"
            lines.append(f"  {f.get('filename'):<52} {names}")
        emit(args, report, "\n".join(lines))
        return 0

    if action == "install":
        if not args.name:
            print("Usage: rapp agents install @publisher/slug")
            return 2
        a, err = find_agent(args.name)
        if err:
            print(f"✗ {err}")
            return 1
        url = f"{RAR_RAW}/{urllib.parse.quote(a['_file'])}"
        req = urllib.request.Request(url, headers={"User-Agent": f"rapp-skill/{VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = r.read()
        except Exception as e:
            print(f"✗ could not download {url}: {type(e).__name__}")
            return 1

        import hashlib
        digest = hashlib.sha256(payload).hexdigest()
        expected = a.get("_sha256")
        if expected and digest != expected:
            print(f"✗ integrity check failed for {a['name']}")
            print(f"  expected {expected[:16]}… got {digest[:16]}…")
            return 1

        fname = Path(a["_file"]).name
        if not fname.endswith("_agent.py"):
            fname = fname[:-3] + "_agent.py"

        ok_live, _ = api("/health", timeout=5, url=args.url)
        if ok_live and not args.to_disk:
            boundary = "----rapp" + os.urandom(8).hex()
            body = b"".join([
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"sha256\"\r\n\r\n{digest}\r\n".encode(),
                (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\n"
                 f"Content-Type: text/x-python\r\n\r\n").encode(),
                payload, f"\r\n--{boundary}--\r\n".encode()])
            ok, res = api("/agents/import", "POST", raw_body=body,
                          ctype=f"multipart/form-data; boundary={boundary}", timeout=180, url=args.url)
            report = {"agent": a["name"], "file": fname, "sha256": digest,
                      "hot_loaded": ok and not (res or {}).get("error"), "response": res}
            save_run("agents install", report)
            if not ok or (res or {}).get("error"):
                print(f"✗ import failed: {(res or {}).get('error') or res}")
                return 1
            loaded = (res or {}).get("agents") or (res or {}).get("loaded") or []
            emit(args, report,
                 f"✓ {a['name']} verified (sha256 {digest[:12]}…) and hot-loaded as {fname}\n"
                 f"  classes: {', '.join(loaded) if loaded else '(none reported)'}\n"
                 f"  try it:  rapp chat \"use {a.get('display_name')}\"")
            return 0

        dest = Path(args.dest) if args.dest else (BRAINSTEM_SRC / "agents")
        dest.mkdir(parents=True, exist_ok=True)
        (dest / fname).write_bytes(payload)
        report = {"agent": a["name"], "path": str(dest / fname), "sha256": digest, "hot_loaded": False}
        save_run("agents install", report)
        emit(args, report, f"✓ {a['name']} verified and written to {dest / fname}\n"
                           f"  Start the brainstem to load it: rapp up")
        return 0

    if action == "remove":
        if not args.name:
            print("Usage: rapp agents remove <filename_agent.py>")
            return 2
        ok, res = api(f"/agents/{urllib.parse.quote(args.name)}", "DELETE", timeout=30, url=args.url)
        if not ok:
            print(f"✗ {res}")
            return 1
        print(f"✓ removed {args.name}")
        return 0

    if action == "export":
        if not args.name:
            print("Usage: rapp agents export <filename_agent.py>")
            return 2
        ok, res = api(f"/agents/export/{urllib.parse.quote(args.name)}", timeout=30, url=args.url)
        if not ok:
            print(f"✗ {res}")
            return 1
        body = res.get("raw") if isinstance(res, dict) and "raw" in res else json.dumps(res)
        out = Path(args.dest or args.name)
        out.write_text(body)
        print(f"✓ exported to {out}")
        return 0

    print(f"Unknown action {action!r}")
    return 2


def load_store():
    d = fetch(STORE_INDEX)
    if not d:
        return None, "RAPPstore index unreachable"
    return d, None


def _download(url, expect_sha=None, timeout=90, token=None):
    headers = {"User-Agent": f"rapp-skill/{VERSION}"}
    tok = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # A catalog entry can outlive the file it points at, and a gated entry
            # 404s by design for an unauthenticated caller. Say which it is.
            hint = ("the catalog entry points at a path that is not in the repository "
                    "(stale catalog entry — report it upstream)")
            if not tok:
                hint += "; if the entry is gated, set GITHUB_TOKEN and retry"
            raise ValueError(f"404 for {url} — {hint}")
        raise ValueError(f"HTTP {e.code} for {url}")
    import hashlib
    digest = hashlib.sha256(payload).hexdigest()
    if expect_sha and digest != expect_sha:
        raise ValueError(f"integrity check failed: expected {expect_sha[:16]}… got {digest[:16]}…")
    return payload, digest


def cmd_store(args):
    """Browse and install from RAPPstore — rapplications and senses."""
    idx, err = load_store()
    if err:
        print(f"✗ {err}")
        return 1
    rapps = idx.get("rapplications") or []
    senses = idx.get("senses") or []

    if args.action == "list":
        q = " ".join(args.name or []).lower() if isinstance(args.name, list) else (args.name or "").lower()
        def match(e):
            if not q:
                return True
            hay = json.dumps(e).lower()
            return all(w in hay for w in q.split())
        rl = [r for r in rapps if match(r)]
        sl = [s_ for s_ in senses if match(s_)]
        report = {"catalog": idx.get("name"), "version": idx.get("version"),
                  "rapplications": rl, "senses": sl}
        lines = [f"{idx.get('name')} v{idx.get('version')} — "
                 f"{len(rapps)} rapplication(s), {len(senses)} sense(s)", ""]
        if rl:
            lines.append("Rapplications — converged single-file agents:")
            for r in rl[: args.limit]:
                gate = " [gated]" if r.get("access") == "private" else ""
                lines.append(f"  {r['id']:<20} v{r.get('version', '?'):<8} {r.get('category', '')}{gate}")
                lines.append(f"    {(r.get('summary') or '')[:100]}")
            lines.append("")
        if sl:
            lines.append("Senses — translations of the response into another mode:")
            for s_ in sl[: args.limit]:
                lines.append(f"  {s_['id']:<20} slot {s_.get('slot', ''):<10} {(s_.get('summary') or '')[:70]}")
            lines.append("")
        lines.append("Install:  rapp store install <id>      (rapplication)")
        lines.append("          rapp store install <id> --sense")
        emit(args, report, "\n".join(lines))
        return 0

    if args.action == "install":
        want = (args.name[0] if isinstance(args.name, list) and args.name else args.name) or ""
        if not want:
            print("Usage: rapp store install <id> [--sense]")
            return 2

        if args.sense:
            e = next((x for x in senses if x.get("id") == want or x.get("filename") == want), None)
            if not e:
                print(f"✗ no sense {want!r}. Try: rapp store list")
                return 1
            try:
                payload, digest = _download(e["url"], e.get("sha256"), token=args.token)
            except Exception as ex:
                print(f"✗ {ex}")
                return 1
            # Senses install to the brainstem source tree, not agents/.
            dest = BRAINSTEM_SRC / "senses"
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / e["filename"]
            path.write_bytes(payload)
            report = {"sense": e["id"], "path": str(path), "sha256": digest, "slot": e.get("slot")}
            save_run("store install", report)
            emit(args, report,
                 f"✓ sense {e['id']} verified (sha256 {digest[:12]}…) → {path}\n"
                 f"  slot {e.get('slot')} · delimiter {e.get('delimiter')}\n"
                 f"  Auto-discovered on the next chat request — no restart.")
            return 0

        e = next((x for x in rapps if x.get("id") == want or x.get("manifest_name") == want), None)
        if not e:
            print(f"✗ no rapplication {want!r}. Try: rapp store list")
            return 1
        if e.get("access") == "private":
            print(f"! {e['id']} is gated (SPEC §11). Its source lives in a private repo")
            print(f"  ({e.get('private_repo', 'undisclosed')}); unauthenticated fetches 404 by design.")
            print("  Authenticate with a PAT scoped to read that repo, then retry.")
            if not args.token and not os.environ.get("GITHUB_TOKEN"):
                return 1
        url = e.get("singleton_url")
        if not url:
            print(f"✗ {e['id']} has no singleton_url")
            return 1
        try:
            payload, digest = _download(url, e.get("singleton_sha256"), token=args.token)
        except Exception as ex:
            print(f"✗ {ex}")
            return 1

        fname = e.get("singleton_filename") or f"{e['id']}_agent.py"
        ok_live, _ = api("/health", timeout=5, url=args.url)
        if ok_live and not args.to_disk:
            boundary = "----rapp" + os.urandom(8).hex()
            body = b"".join([
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"sha256\"\r\n\r\n{digest}\r\n".encode(),
                (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\n"
                 f"Content-Type: text/x-python\r\n\r\n").encode(),
                payload, f"\r\n--{boundary}--\r\n".encode()])
            ok, res = api("/agents/import", "POST", raw_body=body,
                          ctype=f"multipart/form-data; boundary={boundary}", timeout=180, url=args.url)
            report = {"rapplication": e["id"], "file": fname, "sha256": digest,
                      "hot_loaded": ok and not (res or {}).get("error"), "response": res}
            save_run("store install", report)
            if not ok or (res or {}).get("error"):
                print(f"✗ import failed: {(res or {}).get('error') or res}")
                return 1
            emit(args, report,
                 f"✓ {e['name']} v{e.get('version')} verified (sha256 {digest[:12]}…) and hot-loaded\n"
                 f"  {e.get('summary', '')[:110]}\n"
                 f"  try it:  rapp chat \"use {e.get('name')}\"")
            return 0

        dest = Path(args.dest) if args.dest else (BRAINSTEM_SRC / "agents")
        dest.mkdir(parents=True, exist_ok=True)
        (dest / fname).write_bytes(payload)
        report = {"rapplication": e["id"], "path": str(dest / fname), "sha256": digest}
        save_run("store install", report)
        emit(args, report, f"✓ {e['name']} verified → {dest / fname}\n  Start it: rapp up")
        return 0

    print(f"Unknown action {args.action!r}")
    return 2


# ─────────────────────────────────────────────────────────── chat + test

def cmd_chat(args):
    text = " ".join(args.message).strip()
    if not text:
        print("Usage: rapp chat \"your message\"")
        return 2
    ok_h, _ = api("/health", timeout=6, url=args.url)
    if not ok_h:
        print(f"✗ no brainstem at {args.url}. Run: rapp up")
        return 1
    payload = {"user_input": text}
    if args.session:
        payload["session_id"] = args.session
    t0 = time.time()
    ok, res = api("/chat", "POST", payload, timeout=args.timeout, url=args.url)
    elapsed = round(time.time() - t0, 2)
    if not ok:
        print(f"✗ chat failed: {res}")
        return 1
    reply = (res or {}).get("response") or (res or {}).get("error") or ""
    logs = (res or {}).get("agent_logs") or ""
    report = {"prompt": text, "reply": reply, "agent_logs": logs,
              "model": (res or {}).get("model"), "seconds": elapsed,
              "session_id": (res or {}).get("session_id"),
              "tool_invoked": bool(logs.strip())}
    save_run("chat", {"prompt": text[:120], "tool_invoked": bool(logs.strip()), "seconds": elapsed})
    human = reply
    if logs and args.show_tools:
        human = f"[tools]\n{logs}\n\n[reply]\n{reply}"
    human += f"\n\n— {(res or {}).get('model', '?')} · {elapsed}s" + (" · tool used" if logs.strip() else "")
    emit(args, report, human)
    return 0


def cmd_test(args):
    """Load an agent and actually run it — the difference between a lint and a test."""
    target = Path(args.file)
    if not target.exists():
        a, err = find_agent(args.file)
        if err:
            print(f"✗ {err} (and no such file)")
            return 1
        local = BRAINSTEM_SRC / "agents" / Path(a["_file"]).name
        if not local.exists():
            print(f"✗ {a['name']} is not installed locally. Run: rapp agents install {a['name']} --to-disk")
            return 1
        target = local

    child = r'''
import importlib.util, io, json, sys, time, traceback
from contextlib import redirect_stdout, redirect_stderr
target = sys.argv[1]; bs = sys.argv[2]
out = {"loaded": False, "classes": [], "calls": [], "error": None}
buf = io.StringIO()
instances = {}
try:
    with redirect_stdout(buf), redirect_stderr(buf):
        sys.path.insert(0, bs); sys.path.insert(0, bs + "/agents")
        from brainstem import _load_agent_from_file
        instances = _load_agent_from_file(target) or {}
    out["loaded"] = bool(instances); out["classes"] = sorted(instances)
except BaseException as e:
    out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
for name, inst in list(instances.items())[:2]:
    meta = getattr(inst, "metadata", {}) or {}
    props = (meta.get("parameters") or {}).get("properties") or {}
    req = (meta.get("parameters") or {}).get("required") or []
    args_ = {}
    for k in (req or list(props)[:2]):
        spec = props.get(k) or {}
        if spec.get("enum"): args_[k] = spec["enum"][0]
        elif spec.get("type") == "integer": args_[k] = 1
        elif spec.get("type") == "boolean": args_[k] = True
        else: args_[k] = "rapp test probe"
    c = {"agent": name, "args": args_}
    t = time.time(); b = io.StringIO()
    try:
        with redirect_stdout(b), redirect_stderr(b):
            r = inst.perform(**args_)
        c.update(ok=True, seconds=round(time.time()-t, 3), returns_str=isinstance(r, str),
                 chars=len(r if isinstance(r, str) else repr(r)),
                 preview=(r if isinstance(r, str) else repr(r))[:600])
    except BaseException as e:
        c.update(ok=False, exception=type(e).__name__, message=str(e)[:300],
                 trace=traceback.format_exc()[-400:])
    out["calls"].append(c)
print("___RAPPTEST___" + json.dumps(out))
'''
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(child)
        cf = fh.name
    sandbox = tempfile.mkdtemp(prefix="rapp-test-")
    try:
        rc, so, se = run([brainstem_python(), cf, str(target.resolve()), str(BRAINSTEM_SRC)],
                         timeout=args.timeout, cwd=sandbox)
    finally:
        os.unlink(cf)
        shutil.rmtree(sandbox, ignore_errors=True)

    data = {}
    if "___RAPPTEST___" in so:
        try:
            data = json.loads(so.split("___RAPPTEST___", 1)[1].splitlines()[0])
        except Exception:
            pass
    if not data:
        print(f"✗ harness produced no result.\n{(se or so)[-500:]}")
        return 1

    lines = [f"Test: {target.name}", ""]
    if data["loaded"]:
        lines.append(f"  ✓ loaded on the brainstem loader — {', '.join(data['classes'])}")
    else:
        lines.append(f"  ✗ did NOT load: {data.get('error')}")
    for c in data["calls"]:
        if c.get("ok"):
            flag = "" if c.get("returns_str") else "  ← perform() did not return a str"
            lines.append(f"  ✓ perform({', '.join(c['args']) or ''}) → {c['chars']} chars in {c['seconds']}s{flag}")
            lines.append(f"      {c.get('preview', '')[:220]!r}")
        else:
            lines.append(f"  ✗ perform() raised {c.get('exception')}: {c.get('message')}")
    save_run("test", {"file": str(target), "loaded": data["loaded"]})
    ok_all = data["loaded"] and all(c.get("ok") for c in data["calls"])
    lines.append("")
    lines.append("Verdict: " + ("works" if ok_all else "broken"))
    emit(args, {"file": str(target), **data, "ok": ok_all}, "\n".join(lines))
    return 0 if ok_all else 1


# ─────────────────────────────────────────────────────────── map / tiers / memory

def cmd_map(args):
    report = {"repos": [{"repo": r, "tier": t, "role": d, "url": u} for r, t, d, u in ECOSYSTEM]}
    lines = ["The RAPP ecosystem", ""]
    for tier in (1, 2, 3, 0):
        group = [e for e in ECOSYSTEM if e[1] == tier]
        if not group:
            continue
        if tier:
            name, desc = TIERS[tier]
            lines.append(f"Tier {tier} — {name}: {desc}")
        else:
            lines.append("Platform, SDK and docs")
        for repo, _, role, url in group:
            lines.append(f"  {repo:<28} {role}")
        lines.append("")
    lines.append("Start here:  rapp install   →   rapp up   →   rapp doctor")
    emit(args, report, "\n".join(lines))
    return 0


def cmd_tiers(args):
    checks = doctor_checks(args.url)
    by = {}
    for c in checks:
        by.setdefault(c.get("tier") or 0, []).append(c)
    status = {}
    for tier in (1, 2, 3):
        group = by.get(tier, [])
        blocking = [c for c in group if c["state"] == BAD]
        status[tier] = "blocked" if blocking else ("ready" if group else "unknown")
    report = {"tiers": {str(k): {"name": TIERS[k][0], "state": v} for k, v in status.items()}}
    lines = ["Where you stand", ""]
    for tier in (1, 2, 3):
        name, desc = TIERS[tier]
        mark = {"ready": "✓", "blocked": "✗", "unknown": "·"}[status[tier]]
        lines.append(f"  {mark} Tier {tier} — {name}: {status[tier]}")
        lines.append(f"      {desc}")
    lines.append("")
    lines.append("Promotion path: prove it on Tier 1, promote the same agent file to Tier 2,")
    lines.append("then publish through Copilot Studio on Tier 3. No rewrite between them.")
    emit(args, report, "\n".join(lines))
    return 0


def cmd_memory(args):
    if args.action == "path":
        print(BRAINSTEM_HOME)
        return 0
    if args.action == "backup":
        dest = Path(args.dest or (HOME / f"brainstem-memory-{time.strftime('%Y%m%d-%H%M%S')}"))
        if not BRAINSTEM_HOME.exists():
            print("Nothing to back up — no ~/.brainstem")
            return 1
        shutil.copytree(BRAINSTEM_HOME, dest, ignore=shutil.ignore_patterns("venv", "__pycache__", "*.pyc"))
        print(f"✓ backed up to {dest}")
        return 0
    # show
    if not BRAINSTEM_HOME.exists():
        print("No ~/.brainstem yet. Run: rapp install")
        return 1
    entries = []
    for p in sorted(BRAINSTEM_HOME.iterdir()):
        try:
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size
        except OSError:
            size = 0
        entries.append({"path": p.name, "dir": p.is_dir(), "bytes": size})
    report = {"home": str(BRAINSTEM_HOME), "entries": entries}
    lines = [f"Memory and state live at {BRAINSTEM_HOME}", "",
             "This is the whole answer to \"where does our AI's memory live?\" —",
             "you can point at it, back it up, and delete it.", ""]
    for e in entries:
        kind = "dir " if e["dir"] else "file"
        lines.append(f"  {kind} {e['path']:<22} {e['bytes'] / 1024:>10.1f} KB")
    lines.append("")
    lines.append("Back it up:  rapp memory backup")
    emit(args, report, "\n".join(lines))
    return 0


# ─────────────────────────────────────────────────────────── cli

def main(argv=None):
    # Global flags live on a parent parser so they work on either side of the
    # subcommand — `rapp --json doctor` and `rapp doctor --json` both parse.
    # SUPPRESS matters: without it the subparser's own default would overwrite a
    # value already parsed by the main parser, so `rapp --json doctor` would emit text.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="structured output")
    common.add_argument("--url", default=argparse.SUPPRESS, help="brainstem URL")

    p = argparse.ArgumentParser(prog="rapp", parents=[common],
                                description="Run the RAPP ecosystem end to end.")
    p.add_argument("--version", action="version", version=f"rapp-skill {VERSION}")
    p.set_defaults(json=False, url=DEFAULT_URL)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    d = add("doctor", help="health check across every tier")
    d.add_argument("--deep", action="store_true", help="also do a live chat round-trip")
    d.add_argument("--postmortem", action="store_true", help="what the last run did")
    d.set_defaults(fn=cmd_doctor)

    i = add("install", help="install or repair the global brainstem")
    i.add_argument("--repair", action="store_true")
    i.add_argument("--force", action="store_true")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--timeout", type=int, default=900)
    i.set_defaults(fn=cmd_install)

    u = add("up", help="start the local brainstem")
    u.add_argument("--wait", type=int, default=30)
    u.set_defaults(fn=cmd_up)

    add("down", help="stop the local brainstem").set_defaults(fn=cmd_down)
    add("status", help="is it running, what is loaded").set_defaults(fn=cmd_status)

    s = add("search", help="search the RAPP Agent Registry")
    s.add_argument("query", nargs="*")
    s.add_argument("--category")
    s.add_argument("--publisher")
    s.add_argument("--limit", type=int, default=12)
    s.set_defaults(fn=cmd_search)

    a = add("agents", help="list / install / export / remove agents")
    a.add_argument("action", choices=["list", "install", "remove", "export"])
    a.add_argument("name", nargs="?")
    a.add_argument("--dest")
    a.add_argument("--to-disk", action="store_true", help="write to the agents dir instead of hot-loading")
    a.set_defaults(fn=cmd_agents)

    st = add("store", help="RAPPstore — rapplications and senses")
    st.add_argument("action", choices=["list", "install"])
    st.add_argument("name", nargs="*")
    st.add_argument("--sense", action="store_true", help="operate on a sense, not a rapplication")
    st.add_argument("--to-disk", action="store_true")
    st.add_argument("--dest")
    st.add_argument("--token", help="PAT for a gated rapplication")
    st.add_argument("--limit", type=int, default=25)
    st.set_defaults(fn=cmd_store)

    c = add("chat", help="send a turn to the brainstem")
    c.add_argument("message", nargs="*")
    c.add_argument("--session")
    c.add_argument("--timeout", type=int, default=300)
    c.add_argument("--show-tools", action="store_true", default=True)
    c.set_defaults(fn=cmd_chat)

    t = add("test", help="load an agent and actually run it")
    t.add_argument("file")
    t.add_argument("--timeout", type=int, default=120)
    t.set_defaults(fn=cmd_test)

    add("map", help="which repo owns which layer").set_defaults(fn=cmd_map)
    add("tiers", help="where a build stands across the three tiers").set_defaults(fn=cmd_tiers)

    m = add("memory", help="inspect and back up what the brainstem remembers")
    m.add_argument("action", nargs="?", default="show", choices=["show", "path", "backup"])
    m.add_argument("--dest")
    m.set_defaults(fn=cmd_memory)

    args = p.parse_args(argv)

    # argparse subparsers reset a parent flag parsed before the subcommand, so a
    # global given as `rapp --json doctor` would be silently dropped. Reconcile
    # from the raw argv — both orders must behave identically.
    raw = list(argv) if argv is not None else sys.argv[1:]
    if "--json" in raw:
        args.json = True
    if "--url" in raw:
        i = raw.index("--url")
        if i + 1 < len(raw):
            args.url = raw[i + 1]

    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
