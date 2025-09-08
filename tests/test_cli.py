"""Tests for CLI commands."""

from typer.testing import CliRunner

from sysforge.cli import app

runner = CliRunner()


def test_version() -> None:
    """Test version option."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Sysforge" in result.stdout
    assert "version" in result.stdout.lower()


def test_status_command() -> None:
    """Test status command."""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "System Status Overview" in result.stdout or "System Information" in result.stdout


def test_processes_command() -> None:
    """Test processes command."""
    result = runner.invoke(app, ["processes", "--top", "5"])
    assert result.exit_code == 0
    assert "Processes" in result.stdout or "PID" in result.stdout


def test_processes_with_sort() -> None:
    """Test processes command with sort option."""
    result = runner.invoke(app, ["processes", "--sort", "memory"])
    assert result.exit_code == 0


def test_network_command() -> None:
    """Test network command."""
    result = runner.invoke(app, ["network"])
    assert result.exit_code == 0
    assert "Network" in result.stdout or "Interface" in result.stdout
