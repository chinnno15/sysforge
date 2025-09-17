"""Command-line interface for backup and restore operations."""

import os
import sys
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from rich import print as rich_print
from rich.console import Console

from .config import BackupConfig, ConfigManager
from .core import create_backup
from .restore import restore_backup

console = Console()

# Create backup app
backup_app = typer.Typer(
    name="user-backup",
    help="Create and manage user directory backups with git-aware functionality",
    rich_markup_mode="rich",
)


def _load_config(
    config_file: Optional[Path] = None, profile: Optional[str] = None, **overrides: Any
) -> BackupConfig:
    """Load configuration with proper hierarchy."""
    # Remove None values from overrides
    clean_overrides = {k: v for k, v in overrides.items() if v is not None}

    try:
        return ConfigManager.load_effective_config(
            profile=profile,
            config_file=config_file,
            overrides=clean_overrides if clean_overrides else None,
        )
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1) from e


def _complete_backup_files(incomplete: str) -> list[str]:
    """Tab completion for backup files."""
    try:
        backup_files = ConfigManager.list_backups()
        return [
            str(backup_file.name)
            for backup_file in backup_files
            if str(backup_file.name).startswith(incomplete)
        ]
    except Exception:
        return []


def _complete_profiles(incomplete: str) -> list[str]:
    """Tab completion for profile names."""
    try:
        profiles = ConfigManager.list_profiles()
        return [profile for profile in profiles if profile.startswith(incomplete)]
    except Exception:
        return []


@backup_app.command("create")
def create_backup_command(
    target_path: Optional[str] = typer.Argument(
        None, help="Target directory to backup (default from config)"
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Custom configuration file"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Use named profile",
        autocompletion=_complete_profiles,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Override output path"
    ),
    format_type: Optional[str] = typer.Option(
        None, "--format", help="Override compression format (zstd|lz4|gzip)"
    ),
    level: Optional[int] = typer.Option(
        None, "--level", help="Override compression level"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be backed up"
    ),
    print_config: bool = typer.Option(
        False, "--print-config", help="Print effective configuration and exit"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    exclude_git: bool = typer.Option(
        False, "--exclude-git", help="Don't include git repositories"
    ),
    include_pattern: Optional[list[str]] = typer.Option(
        None, "--include", help="Add include pattern (can be used multiple times)"
    ),
    exclude_pattern: Optional[list[str]] = typer.Option(
        None, "--exclude", help="Add exclude pattern (can be used multiple times)"
    ),
    max_workers: Optional[int] = typer.Option(
        None,
        "--max-workers",
        "-j",
        help="Number of parallel workers (default: half CPU cores)",
    ),
    enable_parallel: bool = typer.Option(
        True, "--parallel/--no-parallel", help="Enable/disable parallel processing"
    ),
) -> None:
    """Create a backup of user directory."""
    try:
        # Build overrides
        overrides: dict[str, Any] = {}

        if target_path:
            overrides["target"] = {"base_path": target_path}

        if output:
            if "target" not in overrides:
                overrides["target"] = {}
            overrides["target"]["output_path"] = output

        if format_type or level:
            overrides["compression"] = {}
            if format_type:
                overrides["compression"]["format"] = format_type
            if level:
                overrides["compression"]["level"] = level

        if exclude_git:
            overrides["git"] = {"include_repos": False}

        if include_pattern:
            overrides["include_patterns"] = list(include_pattern)

        if exclude_pattern:
            overrides["exclude_patterns"] = list(exclude_pattern)

        if max_workers is not None:
            overrides["max_workers"] = max_workers

        if not enable_parallel:
            overrides["enable_parallel_processing"] = False

        # Load configuration
        config = _load_config(config_file=config_file, profile=profile, **overrides)

        # Print config if requested
        if print_config:
            rich_print("[bold blue]Effective Configuration:[/bold blue]")
            config_dict = config.model_dump()
            rich_print(
                yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
            )
            return

        # Set console verbosity
        if quiet:
            backup_console = Console(file=sys.stderr, quiet=True)
        else:
            backup_console = console

        # Convert target path if provided
        target_path_obj = Path(target_path) if target_path else None
        output_path_obj = Path(output) if output else None

        # Create backup
        create_backup(
            config=config,
            target_path=target_path_obj,
            output_path=output_path_obj,
            dry_run=dry_run,
            verbose=verbose,
            console=backup_console,
        )

        if not quiet:
            console.print(
                "\n[bold green]Backup operation completed successfully![/bold green]"
            )

    except KeyboardInterrupt:
        console.print("\n[red]Backup cancelled by user[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"\n[red]Backup failed: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1) from e


@backup_app.command("restore")
def restore_backup_command(
    backup_file: Optional[str] = typer.Argument(
        None, help="Backup file to restore", autocompletion=_complete_backup_files
    ),
    target: Optional[str] = typer.Option(
        None, "--target", "-t", help="Target directory (default: original location)"
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Custom configuration file"
    ),
    conflict: Optional[str] = typer.Option(
        None, "--conflict", help="Conflict resolution: prompt|overwrite|skip|backup"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be restored"
    ),
    print_config: bool = typer.Option(
        False, "--print-config", help="Print effective configuration and exit"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    partial: Optional[str] = typer.Option(
        None, "--partial", help="Restore only files matching pattern"
    ),
) -> None:
    """Restore files from backup archive."""
    try:
        # If no backup file specified, list available backups
        if not backup_file:
            available_backups = ConfigManager.list_backups()
            if not available_backups:
                console.print(
                    "[red]No backup files found in default backup directory[/red]"
                )
                backup_dir = ConfigManager.BACKUPS_DIR
                console.print(
                    f"[yellow]Default backup directory: {backup_dir}[/yellow]"
                )
                raise typer.Exit(1)

            console.print("[bold blue]Available backups:[/bold blue]")
            for i, backup_path in enumerate(available_backups[:10], 1):
                backup_stat = backup_path.stat()
                size = backup_stat.st_size
                modified = backup_stat.st_mtime
                import datetime

                mod_time = datetime.datetime.fromtimestamp(modified)

                size_str = _format_size(size)
                time_str = mod_time.strftime("%Y-%m-%d %H:%M")
                console.print(f"  {i:2d}. {backup_path.name} ({size_str}, {time_str})")

            if len(available_backups) > 10:
                console.print(f"  ... and {len(available_backups) - 10} more backups")

            # Prompt for selection
            choice = typer.prompt("Select backup number (or enter full path)", type=str)

            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(available_backups):
                    backup_file = str(available_backups[choice_num - 1])
                else:
                    console.print("[red]Invalid backup number[/red]")
                    raise typer.Exit(1)
            except ValueError:
                # User entered a path
                backup_file = choice

        # Build overrides
        overrides: dict[str, Any] = {}
        if conflict:
            overrides["restore"] = {"conflict_resolution": conflict}

        # Load configuration
        config = _load_config(config_file=config_file, **overrides)

        # Print config if requested
        if print_config:
            rich_print("[bold blue]Effective Configuration:[/bold blue]")
            config_dict = config.model_dump()
            rich_print(
                yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
            )
            return

        # Set console verbosity
        if quiet:
            restore_console = Console(file=sys.stderr, quiet=True)
        else:
            restore_console = console

        # Resolve backup file path
        backup_path = Path(backup_file)
        if not backup_path.is_absolute():
            # Try relative to default backup directory
            backup_path = ConfigManager.BACKUPS_DIR / backup_file

        if not backup_path.exists():
            console.print(f"[red]Backup file not found: {backup_path}[/red]")
            raise typer.Exit(1)

        # Convert target path if provided
        target_path_obj = Path(target) if target else None

        # Restore backup
        restore_backup(
            archive_path=backup_path,
            config=config,
            target_dir=target_path_obj,
            dry_run=dry_run,
            pattern_filter=partial,
            console=restore_console,
        )

        if not quiet:
            console.print(
                "\n[bold green]Restore operation completed successfully![/bold green]"
            )

    except KeyboardInterrupt:
        console.print("\n[red]Restore cancelled by user[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"\n[red]Restore failed: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1) from e


@backup_app.command("config")
def config_command(
    action: str = typer.Argument("show", help="Action: show|init|edit|validate|reset"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name (for profile-specific actions)"
    ),
) -> None:
    """Manage backup configuration."""
    try:
        if action == "show":
            # Show effective configuration
            config = ConfigManager.load_effective_config(profile=profile)
            rich_print("[bold blue]Effective Configuration:[/bold blue]")
            config_dict = config.model_dump()
            rich_print(
                yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
            )

        elif action == "init":
            # Initialize configuration directories
            ConfigManager.ensure_config_dirs()
            console.print("[green]Configuration directories created:[/green]")
            console.print(f"  Config: {ConfigManager.CONFIG_DIR}")
            console.print(f"  Profiles: {ConfigManager.PROFILES_DIR}")
            console.print(f"  Backups: {ConfigManager.BACKUPS_DIR}")

        elif action == "edit":
            # Open configuration in editor
            if profile:
                config_file = ConfigManager.PROFILES_DIR / f"{profile}.yaml"
            else:
                config_file = ConfigManager.USER_CONFIG_FILE

            # Create default config if it doesn't exist
            if not config_file.exists():
                ConfigManager.ensure_config_dirs()
                if profile:
                    default_config = {}
                else:
                    # Create a sample user config
                    default_config = {
                        "target": {
                            "base_path": "~/Work",
                            "output_path": "~/Backups/work-{timestamp}.tar.zst",
                        },
                        "compression": {"level": 6},
                    }

                with open(config_file, "w") as f:
                    yaml.dump(
                        default_config, f, default_flow_style=False, sort_keys=False
                    )

            # Open in editor
            import os
            import subprocess

            editor = os.environ.get("EDITOR", "nano")
            subprocess.run([editor, str(config_file)], check=False)

        elif action == "validate":
            # Validate configuration
            try:
                config = ConfigManager.load_effective_config(profile=profile)
                console.print("[green]Configuration is valid[/green]")
            except Exception as e:
                console.print(f"[red]Configuration validation failed: {e}[/red]")
                raise typer.Exit(1) from e

        elif action == "reset":
            # Reset to default configuration
            if profile:
                config_file = ConfigManager.PROFILES_DIR / f"{profile}.yaml"
                if config_file.exists():
                    config_file.unlink()
                    console.print(f"[green]Profile '{profile}' reset[/green]")
                else:
                    console.print(
                        f"[yellow]Profile '{profile}' does not exist[/yellow]"
                    )
            else:
                if ConfigManager.USER_CONFIG_FILE.exists():
                    ConfigManager.USER_CONFIG_FILE.unlink()
                    console.print("[green]User configuration reset to defaults[/green]")
                else:
                    console.print(
                        "[yellow]User configuration file does not exist[/yellow]"
                    )

        else:
            console.print(f"[red]Unknown action: {action}[/red]")
            console.print("Available actions: show, init, edit, validate, reset")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Configuration command failed: {e}[/red]")
        raise typer.Exit(1) from e


@backup_app.command("list")
def list_command(
    backups: bool = typer.Option(
        True, "--backups/--profiles", help="List backups (default) or profiles"
    ),
) -> None:
    """List available backups or profiles."""
    try:
        if backups:
            # List backup files
            backup_files = ConfigManager.list_backups()
            if not backup_files:
                console.print("[yellow]No backup files found[/yellow]")
                console.print(f"Default backup directory: {ConfigManager.BACKUPS_DIR}")
                return

            console.print(
                f"[bold blue]Available backups ({len(backup_files)}):[/bold blue]"
            )
            for backup_path in backup_files:
                backup_stat = backup_path.stat()
                size = backup_stat.st_size
                modified = backup_stat.st_mtime
                import datetime

                mod_time = datetime.datetime.fromtimestamp(modified)

                size_str = _format_size(size)
                time_str = mod_time.strftime("%Y-%m-%d %H:%M")
                console.print(f"  {backup_path.name} ({size_str}, {time_str})")

        else:
            # List profiles
            profiles = ConfigManager.list_profiles()
            if not profiles:
                console.print("[yellow]No profiles found[/yellow]")
                console.print(f"Profile directory: {ConfigManager.PROFILES_DIR}")
                return

            console.print(
                f"[bold blue]Available profiles ({len(profiles)}):[/bold blue]"
            )
            for profile in profiles:
                console.print(f"  {profile}")

    except Exception as e:
        console.print(f"[red]List command failed: {e}[/red]")
        raise typer.Exit(1) from e


@backup_app.command("benchmark")
def benchmark_command(
    path: str = typer.Argument(default="~", help="Path to benchmark"),
    workers: str = typer.Option(
        "1,2,4,8", help="Comma-separated worker counts to test"
    ),
    iterations: int = typer.Option(3, help="Number of iterations per test"),
    output_file: Optional[str] = typer.Option(
        None, help="Save benchmark results to file"
    ),
) -> None:
    """Benchmark backup performance with different worker counts."""
    import statistics

    from rich.console import Console
    from rich.table import Table

    from .core import create_backup

    console = Console()

    # Parse worker counts
    try:
        worker_counts = [int(w.strip()) for w in workers.split(",")]
    except ValueError as e:
        console.print("[red]Error: Invalid worker counts format. Use '1,2,4,8'[/red]")
        raise typer.Exit(1) from e

    console.print(f"[bold blue]Benchmarking backup performance on: {path}[/bold blue]")
    console.print(f"[dim]Worker counts: {worker_counts}[/dim]")
    console.print(f"[dim]Iterations per test: {iterations}[/dim]")
    console.print()

    benchmark_results = {}

    for worker_count in worker_counts:
        console.print(f"[yellow]Testing with {worker_count} workers...[/yellow]")

        iteration_times = []
        iteration_files = []

        for i in range(iterations):
            console.print(f"[dim]  Iteration {i + 1}/{iterations}[/dim]")

            # Create config with specific worker count
            config = _load_config()
            config.max_workers = worker_count
            config.enable_parallel_processing = worker_count > 1

            # Run dry run to measure scanning performance
            try:
                result = create_backup(
                    config=config,
                    target_path=Path(path).expanduser(),
                    dry_run=True,
                    verbose=False,
                    console=Console(file=open(os.devnull, "w")),  # Suppress output
                )

                scan_time = result.get("performance_metrics", {}).get(
                    "total_scan_time", 0
                )
                files_found = result.get("performance_metrics", {}).get(
                    "total_files_found", 0
                )

                iteration_times.append(scan_time)
                iteration_files.append(files_found)

            except Exception as e:
                console.print(f"[red]Error in iteration {i + 1}: {e}[/red]")
                continue

        if iteration_times:
            avg_time = statistics.mean(iteration_times)
            min_time = min(iteration_times)
            max_time = max(iteration_times)
            files_found = iteration_files[0] if iteration_files else 0
            files_per_sec = files_found / avg_time if avg_time > 0 else 0

            benchmark_results[worker_count] = {
                "avg_time": avg_time,
                "min_time": min_time,
                "max_time": max_time,
                "files_found": files_found,
                "files_per_sec": files_per_sec,
                "speedup": None,  # Will calculate later
            }

    # Calculate speedup relative to single worker
    if 1 in benchmark_results and benchmark_results[1]["avg_time"] > 0:
        baseline_time = benchmark_results[1]["avg_time"]
        for worker_count in benchmark_results:
            speedup = baseline_time / benchmark_results[worker_count]["avg_time"]
            benchmark_results[worker_count]["speedup"] = speedup

    # Display results table
    table = Table(title="Backup Performance Benchmark Results")
    table.add_column("Workers", justify="right", style="cyan")
    table.add_column("Avg Time (s)", justify="right", style="green")
    table.add_column("Min Time (s)", justify="right", style="green")
    table.add_column("Max Time (s)", justify="right", style="green")
    table.add_column("Files Found", justify="right", style="yellow")
    table.add_column("Files/sec", justify="right", style="magenta")
    table.add_column("Speedup", justify="right", style="bold blue")

    for worker_count in sorted(benchmark_results.keys()):
        result = benchmark_results[worker_count]
        speedup_str = f"{result['speedup']:.2f}x" if result["speedup"] else "N/A"

        table.add_row(
            str(worker_count),
            f"{result['avg_time']:.2f}",
            f"{result['min_time']:.2f}",
            f"{result['max_time']:.2f}",
            f"{result['files_found']:,}",
            f"{result['files_per_sec']:.0f}",
            speedup_str,
        )

    console.print(table)

    # Save to file if requested
    if output_file:
        import json

        with open(output_file, "w") as f:
            json.dump(
                {
                    "benchmark_results": benchmark_results,
                    "test_parameters": {
                        "path": path,
                        "worker_counts": worker_counts,
                        "iterations": iterations,
                    },
                },
                f,
                indent=2,
            )
        console.print(f"[green]Benchmark results saved to: {output_file}[/green]")


def _format_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    size_float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} PB"
