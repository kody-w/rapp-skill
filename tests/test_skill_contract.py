"""
Contract tests for the RAPP skill.

These run offline. Anything that needs the network or a live brainstem is skipped
rather than failed, so CI stays honest on a machine with neither.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "rapp"
ENGINE = SKILL / "scripts" / "rapp.py"
CONVERTER = ROOT / "skills" / "rapp-agent-converter"
CONVERTER_ENGINE = CONVERTER / "scripts" / "toast.py"

sys.path.insert(0, str(SKILL / "scripts"))
import rapp  # noqa: E402


# ── the engine is importable and self-consistent ───────────────────────

def test_engine_exists_and_is_executable_python():
    assert ENGINE.exists()
    subprocess.run([sys.executable, "-c", f"import ast; ast.parse(open({str(ENGINE)!r}).read())"],
                   check=True)


def test_help_exits_zero():
    p = subprocess.run([sys.executable, str(ENGINE), "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0
    assert "doctor" in p.stdout


def test_converter_is_a_complete_sibling_skill():
    for rel in (
        "SKILL.md",
        "scripts/toast.py",
        "references/rapp-agent-contract.md",
        "references/rapp1-protocol.md",
        "assets/hello_rapp_agent.py",
    ):
        assert (CONVERTER / rel).is_file(), rel


def test_converter_selftest_passes():
    p = subprocess.run(
        [sys.executable, str(CONVERTER_ENGINE), "selftest"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "SELFTEST PASS" in p.stdout


def test_converter_sample_roundtrips_byte_identical():
    sample = CONVERTER / "assets" / "hello_rapp_agent.py"
    p = subprocess.run(
        [sys.executable, str(CONVERTER_ENGINE), "roundtrip", str(sample)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "IDENTICAL" in p.stdout


def test_documented_converter_path_works_from_arbitrary_cwd(tmp_path):
    p = subprocess.run(
        [sys.executable, str(CONVERTER_ENGINE), "inspect",
         str(CONVERTER / "assets" / "hello_rapp_agent.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout)["format"] == "agent"


def test_rapp_skill_routes_conversion_to_sibling_engine():
    text = (SKILL / "SKILL.md").read_text()
    assert "rapp-agent-converter/scripts/toast.py" in text
    assert "Do not implement conversion" in text
    assert "inside `rapp.py`" in text
    assert "Do not derive it from shell `$0`" in text
    assert "converter has its own CLI and does not accept this" in text


@pytest.mark.parametrize("cmd", ["doctor", "install", "up", "down", "status", "search",
                                 "agents", "store", "chat", "test", "map", "tiers", "memory"])
def test_every_documented_command_is_registered(cmd):
    """SKILL.md promises these; argparse must actually accept them."""
    p = subprocess.run([sys.executable, str(ENGINE), cmd, "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr


def test_version_matches_skill_frontmatter():
    fm = (SKILL / "SKILL.md").read_text().split("---")[1]
    declared = next(l.split(":", 1)[1].strip().strip('"')
                    for l in fm.splitlines() if l.startswith("version:"))
    assert declared == rapp.VERSION


def test_plugin_manifests_agree_on_version():
    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
                ".grok-plugin/plugin.json", "gemini-extension.json"):
        data = json.loads((ROOT / rel).read_text())
        assert data["version"] == rapp.VERSION, rel


def test_marketplace_files_are_valid_json():
    for rel in (".claude-plugin/marketplace.json", ".grok-plugin/marketplace.json",
                ".agents/plugins/marketplace.json"):
        data = json.loads((ROOT / rel).read_text())
        assert data["plugins"][0]["name"] == "rapp"


# ── it must not reimplement what the ecosystem already owns ────────────

def test_install_uses_the_canonical_one_liner():
    """The skill ties the ecosystem together; it does not fork the installer."""
    src = ENGINE.read_text()
    assert "kody-w.github.io/rapp-installer/install.sh" in src
    assert "rapp-installer/main/install.ps1" in src


def test_catalogs_are_the_public_ones():
    src = ENGINE.read_text()
    assert "kody-w/RAR/main/registry.json" in src
    assert "kody-w/RAPP_Store/main/index.json" in src


def test_no_hardcoded_secrets():
    """A credential-shaped literal in a public skill is a leak."""
    import re
    bad = re.compile(r"(gh[pousr]_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
    for path in SKILL.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".md", ".json", ".sh"}:
            assert not bad.search(path.read_text(errors="replace")), path


def test_no_entitlement_claims():
    """Never claim what a user's Copilot subscription includes."""
    banned = ["unlimited token", "infinite token", "free tokens", "unlimited copilot"]
    for path in list(SKILL.rglob("*.md")) + [ROOT / "README.md"]:
        if not path.exists():
            continue
        text = path.read_text(errors="replace").lower()
        for phrase in banned:
            assert phrase not in text, f"{path}: {phrase!r}"


# ── pure helpers ───────────────────────────────────────────────────────

def test_check_shape():
    c = rapp.check("x", rapp.OK, "fine", tier=1)
    assert set(c) == {"check", "state", "detail", "fix", "tier"}


def test_ecosystem_map_is_well_formed():
    for repo, tier, role, url in rapp.ECOSYSTEM:
        assert repo and role
        assert tier in (0, 1, 2, 3)
        assert url.startswith("https://github.com/")


def test_tiers_are_described():
    assert set(rapp.TIERS) == {1, 2, 3}
    for name, desc in rapp.TIERS.values():
        assert name and desc


def test_api_returns_error_tuple_when_unreachable():
    ok, data = rapp.api("/health", timeout=2, url="http://127.0.0.1:9")
    assert ok is False and "error" in data


def test_doctor_json_runs_offline():
    """doctor must produce a report even with nothing installed and no network."""
    env = dict(os.environ, RAPP_HOME="/nonexistent-rapp-home")
    p = subprocess.run([sys.executable, str(ENGINE), "--json", "doctor",
                        "--url", "http://127.0.0.1:9"],
                       capture_output=True, text=True, timeout=300, env=env)
    assert p.returncode in (0, 1)
    report = json.loads(p.stdout)
    assert report["schema"] == "rapp-doctor/1.0"
    assert any(c["check"] == "brainstem installed" for c in report["checks"])
    assert all(c["state"] in {"ok", "warn", "fail", "info"} for c in report["checks"])


def test_doctor_names_a_fix_for_every_failure():
    env = dict(os.environ, RAPP_HOME="/nonexistent-rapp-home")
    p = subprocess.run([sys.executable, str(ENGINE), "--json", "doctor",
                        "--url", "http://127.0.0.1:9"],
                       capture_output=True, text=True, timeout=300, env=env)
    for c in json.loads(p.stdout)["checks"]:
        if c["state"] == "fail":
            assert c["fix"], f"{c['check']} fails with no fix line"


def test_map_runs_without_network():
    p = subprocess.run([sys.executable, str(ENGINE), "--json", "map"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0
    assert len(json.loads(p.stdout)["repos"]) >= 10


def test_install_dry_run_does_not_execute():
    p = subprocess.run([sys.executable, str(ENGINE), "install", "--dry-run"],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, RAPP_HOME="/nonexistent-rapp-home"))
    assert p.returncode == 0
    assert "install.sh" in p.stdout or "install.ps1" in p.stdout


# ── documentation contract ─────────────────────────────────────────────

def test_skill_md_has_required_frontmatter():
    fm = (SKILL / "SKILL.md").read_text().split("---")[1]
    for key in ("name:", "version:", "description:", "license:"):
        assert key in fm


def test_converter_skill_has_canonical_frontmatter():
    fm = (CONVERTER / "SKILL.md").read_text().split("---")[1]
    assert "name: rapp-agent-converter" in fm
    assert "description:" in fm


def test_referenced_reference_files_exist():
    text = (SKILL / "SKILL.md").read_text()
    for ref in ("tiers.md", "agent-contract.md", "troubleshooting.md"):
        assert ref in text
        assert (SKILL / "references" / ref).exists()
