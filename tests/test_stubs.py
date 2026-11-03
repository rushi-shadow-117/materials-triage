from typer.testing import CliRunner

from materials_triage.cli import app

COMMANDS = ["query", "rank", "replay", "diff", "eval", "export", "serve"]


def test_cli_lists_every_planned_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in COMMANDS:
        assert cmd in result.output


def test_serve_stub_says_not_implemented() -> None:
    """Track B implemented the other six commands (tests/cli); serve waits for Track C."""
    result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 2 and "not implemented" in result.output
