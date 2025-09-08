"""Restore functionality for backup archives."""

import os
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from .compression import Decompressor
from .config import BackupConfig, ConflictResolution


class ConflictInfo:
    """Information about a file conflict during restore."""

    def __init__(self, archive_member: tarfile.TarInfo, existing_path: Path):
        self.archive_member = archive_member
        self.existing_path = existing_path
        self.archive_size = archive_member.size
        self.archive_mtime = datetime.fromtimestamp(archive_member.mtime)

        # Get existing file info
        try:
            stat_info = existing_path.stat()
            self.existing_size = stat_info.st_size
            self.existing_mtime = datetime.fromtimestamp(stat_info.st_mtime)
        except (OSError, FileNotFoundError):
            self.existing_size = 0
            self.existing_mtime = datetime.min


class RestoreOperation:
    """Handles restore operations with conflict resolution."""

    def __init__(self, config: BackupConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.conflicts: List[ConflictInfo] = []
        self.restored_files: List[Path] = []
        self.skipped_files: List[Path] = []
        self.errors: List[Tuple[Path, str]] = []

    def restore_archive(
        self,
        archive_path: Path,
        target_dir: Optional[Path] = None,
        dry_run: bool = False,
        pattern_filter: Optional[str] = None
    ) -> Dict[str, int]:
        """Restore files from backup archive.
        
        Args:
            archive_path: Path to backup archive
            target_dir: Target directory (default: original location)
            dry_run: If True, only show what would be restored
            pattern_filter: Optional pattern to filter files
        
        Returns:
            Dictionary with restore statistics
        """
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        # Reset statistics
        self.conflicts.clear()
        self.restored_files.clear()
        self.skipped_files.clear()
        self.errors.clear()

        self.console.print(f"\n[bold blue]Restoring from:[/bold blue] {archive_path}")
        if target_dir:
            self.console.print(f"[bold blue]Target directory:[/bold blue] {target_dir}")

        try:
            # List archive contents and check for conflicts
            members = Decompressor.list_archive(archive_path)

            # Filter members if pattern is provided
            if pattern_filter:
                import fnmatch
                members = [
                    member for member in members
                    if fnmatch.fnmatch(member.name, pattern_filter)
                ]

            self.console.print(f"[green]Found {len(members)} files to restore[/green]")

            # Check for conflicts
            conflicts = self._detect_conflicts(members, target_dir)

            if conflicts and not dry_run:
                self._handle_conflicts(conflicts)

            if dry_run:
                self._show_dry_run_results(members, target_dir)
                return self._get_stats()

            # Perform actual restore
            self._extract_files(archive_path, members, target_dir)

        except Exception as e:
            self.console.print(f"[red]Error during restore: {e}[/red]")
            raise

        # Show results
        self._show_restore_results()

        return self._get_stats()

    def _detect_conflicts(
        self,
        members: List[tarfile.TarInfo],
        target_dir: Optional[Path]
    ) -> List[ConflictInfo]:
        """Detect conflicts with existing files."""
        conflicts = []

        for member in members:
            if member.isfile():
                # Calculate target path
                target_path = self._get_target_path(member.name, target_dir)

                if target_path.exists():
                    conflicts.append(ConflictInfo(member, target_path))

        return conflicts

    def _get_target_path(self, archive_path: str, target_dir: Optional[Path]) -> Path:
        """Calculate target path for a file in the archive."""
        if target_dir:
            return target_dir / archive_path
        else:
            # Use original path (assuming it was stored as absolute path)
            return Path(archive_path)

    def _handle_conflicts(self, conflicts: List[ConflictInfo]) -> None:
        """Handle file conflicts based on configuration."""
        resolution = self.config.restore.conflict_resolution

        if resolution == ConflictResolution.PROMPT:
            self._handle_conflicts_interactive(conflicts)
        elif resolution == ConflictResolution.OVERWRITE:
            self._handle_conflicts_overwrite(conflicts)
        elif resolution == ConflictResolution.SKIP:
            self._handle_conflicts_skip(conflicts)
        elif resolution == ConflictResolution.BACKUP:
            self._handle_conflicts_backup(conflicts)

    def _handle_conflicts_interactive(self, conflicts: List[ConflictInfo]) -> None:
        """Handle conflicts with interactive prompts."""
        self.console.print(f"\n[yellow]Found {len(conflicts)} file conflicts[/yellow]")

        global_choice = None

        for conflict in conflicts:
            if global_choice:
                action = global_choice
            else:
                action = self._prompt_conflict_resolution(conflict)

                if action.endswith('_all'):
                    global_choice = action.replace('_all', '')
                    action = global_choice

            self._apply_conflict_resolution(conflict, action)

    def _prompt_conflict_resolution(self, conflict: ConflictInfo) -> str:
        """Prompt user for conflict resolution."""
        self.console.print(f"\n[bold red]Conflict:[/bold red] {conflict.existing_path}")

        # Create comparison table
        table = Table(title="File Comparison")
        table.add_column("Source", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Modified", justify="right")

        table.add_row(
            "Existing",
            f"{conflict.existing_size:,} bytes",
            conflict.existing_mtime.strftime("%Y-%m-%d %H:%M:%S")
        )
        table.add_row(
            "Archive",
            f"{conflict.archive_size:,} bytes",
            conflict.archive_mtime.strftime("%Y-%m-%d %H:%M:%S")
        )

        self.console.print(table)

        choices = [
            ("o", "Overwrite existing file"),
            ("s", "Skip (keep existing file)"),
            ("b", "Backup existing and restore"),
            ("d", "Show differences"),
            ("O", "Overwrite all remaining"),
            ("S", "Skip all remaining"),
            ("B", "Backup all remaining"),
            ("q", "Quit restore operation")
        ]

        choice_str = "/".join([choice[0] for choice in choices])

        while True:
            action = Prompt.ask(
                f"Choose action [{choice_str}]",
                choices=[choice[0] for choice in choices],
                default="s"
            )

            if action == "d":
                self._show_file_diff(conflict)
                continue
            elif action == "q":
                raise KeyboardInterrupt("Restore operation cancelled by user")
            elif action in ["O", "S", "B"]:
                return action.lower() + "_all"
            else:
                return action

    def _show_file_diff(self, conflict: ConflictInfo) -> None:
        """Show differences between existing file and archive file."""
        self.console.print("[yellow]File diff functionality not implemented yet[/yellow]")
        # TODO: Implement file diff display

    def _apply_conflict_resolution(self, conflict: ConflictInfo, action: str) -> None:
        """Apply the chosen conflict resolution."""
        if action == "overwrite" or action == "o":
            # Mark for overwrite (will be handled during extraction)
            pass
        elif action == "skip" or action == "s":
            self.skipped_files.append(conflict.existing_path)
        elif action == "backup" or action == "b":
            self._backup_existing_file(conflict.existing_path)

    def _handle_conflicts_overwrite(self, conflicts: List[ConflictInfo]) -> None:
        """Overwrite all conflicting files."""
        self.console.print(f"[yellow]Will overwrite {len(conflicts)} existing files[/yellow]")

    def _handle_conflicts_skip(self, conflicts: List[ConflictInfo]) -> None:
        """Skip all conflicting files."""
        self.console.print(f"[yellow]Will skip {len(conflicts)} existing files[/yellow]")
        for conflict in conflicts:
            self.skipped_files.append(conflict.existing_path)

    def _handle_conflicts_backup(self, conflicts: List[ConflictInfo]) -> None:
        """Backup all conflicting files."""
        self.console.print(f"[yellow]Will backup {len(conflicts)} existing files[/yellow]")
        for conflict in conflicts:
            self._backup_existing_file(conflict.existing_path)

    def _backup_existing_file(self, file_path: Path) -> None:
        """Create a backup of an existing file."""
        timestamp = datetime.now()
        backup_suffix = self.config.restore.get_backup_suffix(timestamp)
        backup_path = file_path.with_name(file_path.name + backup_suffix)

        try:
            shutil.copy2(file_path, backup_path)
            self.console.print(f"[green]Backed up:[/green] {backup_path}")
        except Exception as e:
            self.errors.append((file_path, f"Failed to backup: {e}"))

    def _extract_files(
        self,
        archive_path: Path,
        members: List[tarfile.TarInfo],
        target_dir: Optional[Path]
    ) -> None:
        """Extract files from archive."""
        # Filter out skipped files
        skipped_names = {str(path) for path in self.skipped_files}
        members_to_extract = [
            member for member in members
            if self._get_target_path(member.name, target_dir) not in self.skipped_files
        ]

        if not members_to_extract:
            self.console.print("[yellow]No files to extract[/yellow]")
            return

        self.console.print(f"[green]Extracting {len(members_to_extract)} files...[/green]")

        # Create target directory if specified
        if target_dir:
            target_dir.mkdir(parents=True, exist_ok=True)
            extract_path = target_dir
        else:
            extract_path = Path("/")  # Extract to root (absolute paths)

        try:
            with Decompressor.open_archive(archive_path) as tar:
                for member in members_to_extract:
                    try:
                        if target_dir:
                            # Extract with custom target directory
                            tar.extract(member, path=extract_path)
                        else:
                            # Extract to original location
                            tar.extract(member, path="/")

                        target_path = self._get_target_path(member.name, target_dir)
                        self.restored_files.append(target_path)

                        # Restore permissions if configured
                        if self.config.restore.preserve_permissions:
                            self._restore_permissions(target_path, member)

                    except Exception as e:
                        error_path = self._get_target_path(member.name, target_dir)
                        self.errors.append((error_path, str(e)))

        except Exception as e:
            raise RuntimeError(f"Failed to extract archive: {e}")

    def _restore_permissions(self, file_path: Path, member: tarfile.TarInfo) -> None:
        """Restore file permissions from archive."""
        try:
            if member.isfile() or member.isdir():
                os.chmod(file_path, member.mode)

            # Restore timestamps
            os.utime(file_path, (member.mtime, member.mtime))

        except (OSError, PermissionError) as e:
            # Log warning but don't fail the restore
            self.console.print(f"[yellow]Warning: Could not restore permissions for {file_path}: {e}[/yellow]")

    def _show_dry_run_results(
        self,
        members: List[tarfile.TarInfo],
        target_dir: Optional[Path]
    ) -> None:
        """Show what would be restored in dry run mode."""
        self.console.print("\n[bold green]Dry run - files that would be restored:[/bold green]")

        for member in members:
            if member.isfile():
                target_path = self._get_target_path(member.name, target_dir)
                status = "OVERWRITE" if target_path.exists() else "NEW"
                self.console.print(f"  [{status}] {target_path}")

    def _show_restore_results(self) -> None:
        """Show restore operation results."""
        self.console.print("\n[bold green]Restore completed![/bold green]")

        if self.restored_files:
            self.console.print(f"[green]Restored {len(self.restored_files)} files[/green]")

        if self.skipped_files:
            self.console.print(f"[yellow]Skipped {len(self.skipped_files)} files[/yellow]")

        if self.errors:
            self.console.print(f"[red]Errors: {len(self.errors)} files failed[/red]")
            for file_path, error in self.errors[:5]:  # Show first 5 errors
                self.console.print(f"  [red]Error:[/red] {file_path} - {error}")

            if len(self.errors) > 5:
                self.console.print(f"  [red]... and {len(self.errors) - 5} more errors[/red]")

    def _get_stats(self) -> Dict[str, int]:
        """Get restore operation statistics."""
        return {
            "restored": len(self.restored_files),
            "skipped": len(self.skipped_files),
            "errors": len(self.errors),
            "conflicts": len(self.conflicts)
        }


def restore_backup(
    archive_path: Path,
    config: BackupConfig,
    target_dir: Optional[Path] = None,
    dry_run: bool = False,
    pattern_filter: Optional[str] = None,
    console: Optional[Console] = None
) -> Dict[str, int]:
    """Convenience function to restore a backup.
    
    Args:
        archive_path: Path to backup archive
        config: Backup configuration
        target_dir: Target directory (default: original location)
        dry_run: If True, only show what would be restored
        pattern_filter: Optional pattern to filter files
        console: Rich console for output
    
    Returns:
        Dictionary with restore statistics
    """
    restore_op = RestoreOperation(config, console)
    return restore_op.restore_archive(
        archive_path=archive_path,
        target_dir=target_dir,
        dry_run=dry_run,
        pattern_filter=pattern_filter
    )
