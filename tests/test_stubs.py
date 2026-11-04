from typer.testing import CliRunner

from materials_triage.cli import app

COMMANDS = ["query", "rank", "replay", "diff", "eval", "export", "serve"]


def test_cli_lists_every_planned_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in COMMANDS:
        assert cmd in result.output


def test_serve_builds_the_app_without_binding(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`serve` builds the real app (Track C) and hands it to uvicorn; here uvicorn is a spy."""
    import uvicorn

    seen: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(app=app, **kw))
    monkeypatch.setenv("AUTH_MODE", "none")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    result = CliRunner().invoke(app, ["serve", "--port", "8123", "--no-web"])
    assert result.exit_code == 0, result.output
    assert seen["port"] == 8123 and getattr(seen["app"], "title", "") == "materials-triage"
