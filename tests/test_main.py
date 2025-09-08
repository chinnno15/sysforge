"""Test cases for the __main__ module."""

import subprocess
import sys


def test_main_module_runs() -> None:
    """Test that the module can be run as a script."""
    result = subprocess.run(
        [sys.executable, "-m", "sysforge", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "sysforge" in result.stdout.lower()
