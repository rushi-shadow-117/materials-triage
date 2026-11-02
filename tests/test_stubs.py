from typer.testing import CliRunner

from materials_triage.cli import app

COMMANDS = ["query", "rank", "replay", "diff", "eval", "export", "serve"]


def test_cli_lists_every_planned_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in COMMANDS:
        assert cmd in result.output


def test_cli_stubs_say_not_implemented() -> None:
    for args in (
        ["query", "x"],
        ["rank", "--formulas", "HfO2"],
        ["replay", "r"],
        ["diff", "a", "b"],
        ["eval"],
        ["export", "r"],
        ["serve"],
    ):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 2 and "not implemented" in result.output, args
