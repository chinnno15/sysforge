"""Command-line interface for Sysforge."""

from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from sysforge import __version__
from sysforge.backup.cli import backup_app

app = typer.Typer(
    name="sysforge",
    help="Modern Python toolkit for Linux system administration and automation",
    add_completion=True,
    rich_markup_mode="rich",
)

console = Console()


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        print(f"[bold blue]Sysforge[/bold blue] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Sysforge - Modern Python toolkit for Linux system administration.

    A collection of powerful tools for system management, monitoring,
    and automation tasks.
    """
    pass


@app.command()
def status() -> None:
    """Show system status overview."""
    import platform
    from datetime import datetime

    import psutil

    console.print("\n[bold cyan]System Status Overview[/bold cyan]\n")

    # System info table
    table = Table(title="System Information", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Hostname", platform.node())
    table.add_row("Platform", platform.platform())
    table.add_row("Python Version", platform.python_version())
    table.add_row("CPU Cores", str(psutil.cpu_count()))
    table.add_row("CPU Usage", f"{psutil.cpu_percent(interval=1)}%")

    # Memory info
    mem = psutil.virtual_memory()
    table.add_row("Memory Total", f"{mem.total / (1024**3):.2f} GB")
    table.add_row("Memory Used", f"{mem.percent}%")

    # Disk info
    disk = psutil.disk_usage("/")
    table.add_row("Disk Total", f"{disk.total / (1024**3):.2f} GB")
    table.add_row("Disk Used", f"{disk.percent}%")

    # Boot time
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    table.add_row("Boot Time", boot_time.strftime("%Y-%m-%d %H:%M:%S"))

    console.print(table)


@app.command()
def processes(
    top: int = typer.Option(10, "--top", "-t", help="Number of top processes to show"),
    sort_by: str = typer.Option(
        "cpu", "--sort", "-s", help="Sort by: cpu, memory, name"
    ),
) -> None:
    """List running processes."""
    import psutil

    console.print(
        f"\n[bold cyan]Top {top} Processes (sorted by {sort_by})[/bold cyan]\n"
    )

    table = Table(show_header=True)
    table.add_column("PID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("CPU %", style="yellow")
    table.add_column("Memory %", style="magenta")
    table.add_column("Status", style="blue")

    processes_list = []
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent", "status"]
    ):
        try:
            pinfo = proc.info
            processes_list.append(pinfo)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Sort processes
    if sort_by == "cpu":
        processes_list.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
    elif sort_by == "memory":
        processes_list.sort(key=lambda x: x.get("memory_percent", 0) or 0, reverse=True)
    elif sort_by == "name":
        processes_list.sort(key=lambda x: x.get("name", "") or "")

    # Display top N processes
    for proc_info in processes_list[:top]:
        table.add_row(
            str(proc_info.get("pid", "N/A")),
            proc_info.get("name", "N/A") or "N/A",
            f"{proc_info.get('cpu_percent', 0) or 0:.1f}",
            f"{proc_info.get('memory_percent', 0) or 0:.1f}",
            proc_info.get("status", "N/A") or "N/A",
        )

    console.print(table)


@app.command()
def network() -> None:
    """Show network interfaces and statistics."""
    import psutil

    console.print("\n[bold cyan]Network Interfaces[/bold cyan]\n")

    table = Table(show_header=True)
    table.add_column("Interface", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Address", style="yellow")
    table.add_column("Netmask", style="magenta")

    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for iface, addr_list in addrs.items():
        is_up = stats[iface].isup if iface in stats else False
        status = "[green]UP[/green]" if is_up else "[red]DOWN[/red]"

        for addr in addr_list:
            if addr.family.name == "AF_INET":  # IPv4
                table.add_row(
                    iface,
                    status,
                    addr.address,
                    addr.netmask or "N/A",
                )

    console.print(table)

    # Network I/O statistics
    net_io = psutil.net_io_counters()
    console.print("\n[bold cyan]Network I/O Statistics[/bold cyan]")
    console.print(f"Bytes Sent: [green]{net_io.bytes_sent / (1024**2):.2f} MB[/green]")
    console.print(
        f"Bytes Received: [green]{net_io.bytes_recv / (1024**2):.2f} MB[/green]"
    )
    console.print(f"Packets Sent: [green]{net_io.packets_sent:,}[/green]")
    console.print(f"Packets Received: [green]{net_io.packets_recv:,}[/green]")


# Add backup subcommand
app.add_typer(backup_app, name="user-backup", help="User directory backup and restore")


def cli() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli()
