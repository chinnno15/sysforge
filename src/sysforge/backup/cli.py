"""Command-line interface for backup and restore operations."""

import sys
from pathlib import Path
from typing import List, Optional

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
    rich_markup_mode="rich"
)


def _load_config(
    config_file: Optional[Path] = None,
    profile: Optional[str] = None,
    **overrides
) -> BackupConfig:
    """Load configuration with proper hierarchy."""
    # Remove None values from overrides
    clean_overrides = {k: v for k, v in overrides.items() if v is not None}

    try:
        return ConfigManager.load_effective_config(
            profile=profile,
            config_file=config_file,
            overrides=clean_overrides if clean_overrides else None
        )
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)


def _complete_backup_files(incomplete: str) -> List[str]:
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


def _complete_profiles(incomplete: str) -> List[str]:
    """Tab completion for profile names."""
    try:
        profiles = ConfigManager.list_profiles()
        return [profile for profile in profiles if profile.startswith(incomplete)]
    except Exception:
        return []


@backup_app.command("create")
def create_backup_command(
    target_path: Optional[str] = typer.Argument(
        None,
        help="Target directory to backup (default from config)"
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Custom configuration file"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Use named profile",
        autocompletion=_complete_profiles
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Override output path"
    ),
    format_type: Optional[str] = typer.Option(
        None,
        "--format",
        help="Override compression format (zstd|lz4|gzip)"
    ),
    level: Optional[int] = typer.Option(
        None,
        "--level",
        help="Override compression level"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be backed up"
    ),
    print_config: bool = typer.Option(
        False,
        "--print-config",
        help="Print effective configuration and exit"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output"
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Minimal output"
    ),
    exclude_git: bool = typer.Option(
        False,
        "--exclude-git",
        help="Don't include git repositories"
    ),
    include_pattern: Optional[List[str]] = typer.Option(
        None,
        "--include",
        help="Add include pattern (can be used multiple times)"
    ),
    exclude_pattern: Optional[List[str]] = typer.Option(
        None,
        "--exclude",
        help="Add exclude pattern (can be used multiple times)"
    )
):
    """Create a backup of user directory."""
    try:
        # Build overrides
        overrides = {}

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

        # Load configuration
        config = _load_config(
            config_file=config_file,
            profile=profile,
            **overrides
        )

        # Print config if requested
        if print_config:
            rich_print("[bold blue]Effective Configuration:[/bold blue]")
            config_dict = config.model_dump()
            rich_print(yaml.dump(config_dict, default_flow_style=False, sort_keys=False))
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
        result = create_backup(
            config=config,
            target_path=target_path_obj,
            output_path=output_path_obj,
            dry_run=dry_run,
            verbose=verbose,
            console=backup_console
        )

        if not quiet:
            console.print("\n[bold green]Backup operation completed successfully![/bold green]")

    except KeyboardInterrupt:
        console.print("\n[red]Backup cancelled by user[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Backup failed: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)


@backup_app.command("restore")
def restore_backup_command(
    backup_file: Optional[str] = typer.Argument(
        None,
        help="Backup file to restore",
        autocompletion=_complete_backup_files
    ),
    target: Optional[str] = typer.Option(
        None,
        "--target",
        "-t",
        help="Target directory (default: original location)"
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Custom configuration file"
    ),
    conflict: Optional[str] = typer.Option(
        None,
        "--conflict",
        help="Conflict resolution: prompt|overwrite|skip|backup"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be restored"
    ),
    print_config: bool = typer.Option(
        False,
        "--print-config",
        help="Print effective configuration and exit"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output"
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Minimal output"
    ),
    partial: Optional[str] = typer.Option(
        None,
        "--partial",
        help="Restore only files matching pattern"
    )
):
    """Restore files from backup archive."""
    try:
        # If no backup file specified, list available backups
        if not backup_file:
            available_backups = ConfigManager.list_backups()
            if not available_backups:
                console.print("[red]No backup files found in default backup directory[/red]")
                console.print(f"[yellow]Default backup directory: {ConfigManager.BACKUPS_DIR}[/yellow]")
                raise typer.Exit(1)

            console.print("[bold blue]Available backups:[/bold blue]")
            for i, backup_path in enumerate(available_backups[:10], 1):
                backup_stat = backup_path.stat()
                size = backup_stat.st_size
                modified = backup_stat.st_mtime
                import datetime
                mod_time = datetime.datetime.fromtimestamp(modified)

                size_str = _format_size(size)
                console.print(f"  {i:2d}. {backup_path.name} ({size_str}, {mod_time.strftime('%Y-%m-%d %H:%M')})")

            if len(available_backups) > 10:
                console.print(f"  ... and {len(available_backups) - 10} more backups")

            # Prompt for selection
            choice = typer.prompt(
                "Select backup number (or enter full path)",
                type=str
            )

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
        overrides = {}
        if conflict:
            overrides["restore"] = {"conflict_resolution": conflict}

        # Load configuration
        config = _load_config(
            config_file=config_file,
            **overrides
        )

        # Print config if requested
        if print_config:
            rich_print("[bold blue]Effective Configuration:[/bold blue]")
            config_dict = config.model_dump()
            rich_print(yaml.dump(config_dict, default_flow_style=False, sort_keys=False))
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
        result = restore_backup(
            archive_path=backup_path,
            config=config,
            target_dir=target_path_obj,
            dry_run=dry_run,
            pattern_filter=partial,
            console=restore_console
        )

        if not quiet:
            console.print("\n[bold green]Restore operation completed successfully![/bold green]")

    except KeyboardInterrupt:
        console.print("\n[red]Restore cancelled by user[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Restore failed: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)


@backup_app.command("config")
def config_command(
    action: str = typer.Argument(
        "show",
        help="Action: show|init|edit|validate|reset"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name (for profile-specific actions)"
    )
):
    """Manage backup configuration."""
    try:
        if action == "show":
            # Show effective configuration
            config = ConfigManager.load_effective_config(profile=profile)
            rich_print("[bold blue]Effective Configuration:[/bold blue]")
            config_dict = config.model_dump()
            rich_print(yaml.dump(config_dict, default_flow_style=False, sort_keys=False))

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
                            "output_path": "~/Backups/work-{timestamp}.tar.zst"
                        },
                        "compression": {
                            "level": 6
                        }
                    }

                with open(config_file, 'w') as f:
                    yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

            # Open in editor
            import os
            editor = os.environ.get('EDITOR', 'nano')
            os.system(f"{editor} {config_file}")

        elif action == "validate":
            # Validate configuration
            try:
                config = ConfigManager.load_effective_config(profile=profile)
                console.print("[green]Configuration is valid[/green]")
            except Exception as e:
                console.print(f"[red]Configuration validation failed: {e}[/red]")
                raise typer.Exit(1)

        elif action == "reset":
            # Reset to default configuration
            if profile:
                config_file = ConfigManager.PROFILES_DIR / f"{profile}.yaml"
                if config_file.exists():
                    config_file.unlink()
                    console.print(f"[green]Profile '{profile}' reset[/green]")
                else:
                    console.print(f"[yellow]Profile '{profile}' does not exist[/yellow]")
            else:
                if ConfigManager.USER_CONFIG_FILE.exists():
                    ConfigManager.USER_CONFIG_FILE.unlink()
                    console.print("[green]User configuration reset to defaults[/green]")
                else:
                    console.print("[yellow]User configuration file does not exist[/yellow]")

        else:
            console.print(f"[red]Unknown action: {action}[/red]")
            console.print("Available actions: show, init, edit, validate, reset")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Configuration command failed: {e}[/red]")
        raise typer.Exit(1)


@backup_app.command("list")
def list_command(
    backups: bool = typer.Option(
        True,
        "--backups/--profiles",
        help="List backups (default) or profiles"
    )
):
    """List available backups or profiles."""
    try:
        if backups:
            # List backup files
            backup_files = ConfigManager.list_backups()
            if not backup_files:
                console.print("[yellow]No backup files found[/yellow]")
                console.print(f"Default backup directory: {ConfigManager.BACKUPS_DIR}")
                return

            console.print(f"[bold blue]Available backups ({len(backup_files)}):[/bold blue]")
            for backup_path in backup_files:
                backup_stat = backup_path.stat()
                size = backup_stat.st_size
                modified = backup_stat.st_mtime
                import datetime
                mod_time = datetime.datetime.fromtimestamp(modified)

                size_str = _format_size(size)
                console.print(f"  {backup_path.name} ({size_str}, {mod_time.strftime('%Y-%m-%d %H:%M')})")

        else:
            # List profiles
            profiles = ConfigManager.list_profiles()
            if not profiles:
                console.print("[yellow]No profiles found[/yellow]")
                console.print(f"Profile directory: {ConfigManager.PROFILES_DIR}")
                return

            console.print(f"[bold blue]Available profiles ({len(profiles)}):[/bold blue]")
            for profile in profiles:
                console.print(f"  {profile}")

    except Exception as e:
        console.print(f"[red]List command failed: {e}[/red]")
        raise typer.Exit(1)


def _format_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
