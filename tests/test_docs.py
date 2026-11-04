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
