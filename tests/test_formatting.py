"""Tests for formatting utilities."""

from sysforge.utils.formatting import (
    create_table,
    format_bytes,
    format_percentage,
    format_uptime,
)


def test_format_bytes() -> None:
    """Test byte formatting."""
    assert format_bytes(0) == "0.00 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1024 * 1024) == "1.00 MB"
    assert format_bytes(1024 * 1024 * 1024) == "1.00 GB"
    assert format_bytes(1536) == "1.50 KB"
    assert format_bytes(1234567890) == "1.15 GB"


def test_format_percentage() -> None:
    """Test percentage formatting."""
    assert format_percentage(0) == "0.0%"
    assert format_percentage(50.5) == "50.5%"
    assert format_percentage(100) == "100.0%"
    assert format_percentage(33.333, precision=2) == "33.33%"


def test_format_uptime() -> None:
    """Test uptime formatting."""
    assert format_uptime(30) == "Less than a minute"
    assert format_uptime(60) == "1 minute"
    assert format_uptime(120) == "2 minutes"
    assert format_uptime(3600) == "1 hour"
    assert format_uptime(7200) == "2 hours"
    assert format_uptime(86400) == "1 day"
    assert format_uptime(90000) == "1 day, 1 hour"
    assert format_uptime(93600) == "1 day, 2 hours"
    assert format_uptime(266400) == "3 days, 2 hours"


def test_create_table() -> None:
    """Test table creation."""
    table = create_table(title="Test Table")
    assert table.title == "Test Table"
    assert table.show_header is True

    table_with_columns = create_table(
        title="Test", columns=[("Column1", "cyan"), ("Column2", "green")]
    )
    assert len(table_with_columns.columns) == 2
