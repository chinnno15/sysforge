"""Formatting utilities for CLI output."""

from typing import Optional

from rich.table import Table


def create_table(
    title: Optional[str] = None,
    columns: Optional[list[tuple[str, str]]] = None,
) -> Table:
    """Create a formatted Rich table.

    Args:
        title: Optional table title.
        columns: List of (name, style) tuples for columns.

    Returns:
        Configured Rich Table object.
    """
    table = Table(title=title, show_header=True)

    if columns:
        for name, style in columns:
            table.add_column(name, style=style)

    return table


def format_bytes(bytes_value: float, precision: int = 2) -> str:
    """Format bytes to human-readable string.

    Args:
        bytes_value: Number of bytes.
        precision: Decimal precision.

    Returns:
        Formatted string (e.g., "1.23 GB").
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.{precision}f} {unit}"
        bytes_value /= 1024.0

    return f"{bytes_value:.{precision}f} PB"


def format_percentage(value: float, precision: int = 1) -> str:
    """Format percentage value.

    Args:
        value: Percentage value.
        precision: Decimal precision.

    Returns:
        Formatted percentage string.
    """
    return f"{value:.{precision}f}%"


def format_uptime(seconds: float) -> str:
    """Format uptime from seconds to human-readable string.

    Args:
        seconds: Uptime in seconds.

    Returns:
        Formatted uptime string.
    """
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return ", ".join(parts) if parts else "Less than a minute"
