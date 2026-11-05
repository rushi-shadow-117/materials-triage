"""The docs name real things: every `uv run` command, script, and doc link in the README and
guides refers to a CLI command, a script, or a file that exists; the README stays short."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from materials_triage.cli import app

ROOT = Path(__file__).resolve().parents[1]
GUIDES = (
    "ARCHITECTURE",
    "SCIENTIST_GUIDE",
    "ADMIN_GUIDE",
    "CONFIGURING",
    "DATA_SOURCES",
    "DISCOVERY_QUESTIONS",
    "EXTENSIONS",
    "COLD_RUN",
    "PERMISSIONS",
)
# the guides describe the system as it is; DECISIONS, FAILURE_MATRIX, EVAL and wire-findings
# are records of what was true when written and are not checked here
DOCS = [ROOT / "README.md", *(ROOT / "docs" / f"{g}.md" for g in GUIDES)]


def _cli_commands() -> set[str]:
    out = CliRunner().invoke(app, ["--help"]).output
    return set(re.findall(r"^\s*│?\s*([a-z-]+)\s{2,}", out, re.M)) | {
        "query",
        "rank",
        "replay",
        "diff",
        "export",
        "serve",
        "eval",
    }


def test_readme_is_short() -> None:
    assert len((ROOT / "README.md").read_text().splitlines()) < 150


def test_commands_and_links_in_docs_exist() -> None:
    commands = _cli_commands()
    problems: list[str] = []
    for doc in DOCS:
        text = doc.read_text()
        for m in re.finditer(r"uv run materials-triage (\w[\w-]*)", text):
            if m.group(1) not in commands:
                problems.append(f"{doc.name}: unknown command {m.group(1)}")
        for m in re.finditer(r"uv run python (scripts/\S+\.py|-m [\w.]+)", text):
            target = m.group(1)
            if target.startswith("scripts/") and not (ROOT / target).exists():
                problems.append(f"{doc.name}: missing {target}")
        for m in re.finditer(r"`((?:docs|scripts|config|deploy|apptainer|infra)/[\w./-]+)`", text):
            if not (ROOT / m.group(1)).exists() and m.group(1) != "docs/DESIGN_NOTE.md":
                problems.append(f"{doc.name}: missing {m.group(1)}")
    assert problems == [], problems


def test_claude_md_has_no_stale_lines_and_determinism_is_scoped() -> None:
    # review F16 and F05
    claude = (ROOT / "CLAUDE.md").read_text()
    for stale in ("Keycloak is cut", "only `serve` is still a stub", "No web job until"):
        assert stale not in claude, stale
    assert "Read it before planning" not in claude  # pointed at a gitignored plan
    arch = (ROOT / "docs" / "ARCHITECTURE.md").read_text()
    assert "live evidence labels on a cold" in arch and "materials-triage diff" in arch
    from scripts.generate_eval_report import DETERMINISM_NOTE

    assert "cold classifier cache" in DETERMINISM_NOTE


def test_evidence_check_false_negatives_are_a_stated_limit() -> None:
    # owner decision on PR #18: the subject check's known misses are documented, not hidden
    ext = (ROOT / "docs" / "EXTENSIONS.md").read_text()
    dec = (ROOT / "docs" / "DECISIONS.md").read_text()
    for text in (ext, dec):
        assert "MgO/Mo(001)" in text
        assert "does not name the material" in text
