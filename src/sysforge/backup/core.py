"""Core backup functionality."""

import json
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.progress import Progress

from .compression import CompressedTarFile
from .config import BackupConfig
from .filters import FileFilter


class PerformanceMetrics:
    """Track performance metrics for backup operations."""

    def __init__(self) -> None:
        self.repo_discovery_time = 0.0
        self.repo_processing_time = 0.0
        self.non_repo_processing_time = 0.0
        self.total_scan_time = 0.0
        self.total_repos_processed = 0
        self.parallel_workers_used = 0
        self.total_files_found = 0
        self.total_files_processed = 0
        self.enable_parallel = True


@contextmanager
def measure_time() -> Any:
    """Context manager to measure execution time."""
    start = time.time()
    timer = type("Timer", (), {"elapsed": 0})()
    try:
        yield timer
    finally:
        timer.elapsed = time.time() - start


class BackupOperation:
    """Handles backup operations."""

    def __init__(self, config: BackupConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.file_filter = FileFilter(config)
        self.verbose = False

        # Statistics
        self.total_files = 0
        self.total_size = 0
        self.processed_files = 0
        self.skipped_files = 0
        self.errors: List[tuple[Path, str]] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

        # Performance metrics
        self.performance_metrics = PerformanceMetrics()
        self.performance_metrics.parallel_workers_used = config.max_workers
        self.performance_metrics.enable_parallel = config.enable_parallel_processing

    def create_backup(
        self,
        target_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Create a backup of the target directory.

        Args:
            target_path: Path to backup (default from config)
            output_path: Output archive path (default from config)
            dry_run: If True, only show what would be backed up

        Returns:
            Dictionary with backup statistics and information
        """
        self.start_time = datetime.now()

        # Use config defaults if not provided
        if target_path is None:
            target_path = self.config.target.get_base_path()

        if output_path is None:
            output_path = self.config.target.get_output_path(self.start_time)

        # Ensure target path exists
        if not target_path.exists():
            raise FileNotFoundError(f"Target path does not exist: {target_path}")

        self.console.print(
            f"\n[bold blue]Creating backup of:[/bold blue] {target_path}"
        )
        self.console.print(f"[bold blue]Output:[/bold blue] {output_path}")
        self.console.print(
            f"[bold blue]Compression:[/bold blue] {self.config.compression.format} (level {self.config.compression.level})"
        )

        # Reset statistics
        self._reset_stats()

        # Get list of files to backup with performance monitoring
        if self.verbose:
            self.console.print(f"[yellow]Scanning files in {target_path}...[/yellow]")
            self.console.print("[dim]Configuration:[/dim]")
            self.console.print(
                f"[dim]  - Git repos included: {self.config.git.include_repos}[/dim]"
            )
            self.console.print(
                f"[dim]  - Respect gitignore: {self.config.git.respect_gitignore}[/dim]"
            )
            self.console.print(
                f"[dim]  - Include patterns: {len(self.config.include_patterns)}[/dim]"
            )
            self.console.print(
                f"[dim]  - Exclude patterns: {len(self.config.exclude_patterns)}[/dim]"
            )
            self.console.print(
                f"[dim]  - Always exclude patterns: {len(self.config.always_exclude)}[/dim]"
            )
            self.console.print(
                f"[dim]  - Max file size: {self.config.max_file_size}[/dim]"
            )
            self.console.print(
                f"[dim]  - Parallel processing: {self.config.enable_parallel_processing}[/dim]"
            )
            self.console.print(f"[dim]  - Max workers: {self.config.max_workers}[/dim]")
        else:
            self.console.print("[yellow]Scanning files...[/yellow]")

        # Measure file scanning performance
        with measure_time() as scan_timer:
            files_to_backup = self.file_filter.get_filtered_files(
                target_path, verbose=self.verbose, console=self.console
            )

        # Update performance metrics
        self.performance_metrics.total_scan_time = scan_timer.elapsed
        self.performance_metrics.total_files_found = len(files_to_backup)

        if self.verbose:
            self.console.print(
                f"[dim]File scanning completed in {scan_timer.elapsed:.2f}s[/dim]"
            )

        self.total_files = len(files_to_backup)
        self.total_size = sum(
            self._get_file_size(file_path) for file_path in files_to_backup
        )

        self.console.print(
            f"[green]Found {self.total_files:,} files ({self._format_size(self.total_size)})[/green]"
        )

        if dry_run:
            self._show_dry_run_results(files_to_backup, target_path)
            return self._get_backup_info(target_path, output_path, files_to_backup)

        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup archive
        self._create_archive(files_to_backup, target_path, output_path)

        self.end_time = datetime.now()

        # Show results
        self._show_backup_results(output_path)

        return self._get_backup_info(target_path, output_path, files_to_backup)

    def _reset_stats(self) -> None:
        """Reset backup statistics."""
        self.total_files = 0
        self.total_size = 0
        self.processed_files = 0
        self.skipped_files = 0
        self.errors.clear()

    def _get_file_size(self, file_path: Path) -> int:
        """Get file size safely."""
        try:
            return file_path.stat().st_size if file_path.is_file() else 0
        except (OSError, PermissionError):
            return 0

    def _create_archive(
        self, files_to_backup: List[Path], target_path: Path, output_path: Path
    ) -> None:
        """Create the backup archive."""
        self.console.print(f"[green]Creating archive: {output_path.name}[/green]")

        with Progress(console=self.console) as progress:
            task = progress.add_task(
                "[green]Compressing files...", total=self.total_files
            )

            with CompressedTarFile(
                output_path,
                self.config.compression.format,
                self.config.compression.level,
            ) as archive:
                # Add metadata file
                self._add_metadata(archive, target_path, files_to_backup)

                # Add files to archive
                for file_path in files_to_backup:
                    try:
                        # Calculate relative path for archive
                        if file_path.is_relative_to(target_path):
                            arcname = str(file_path.relative_to(target_path))
                        else:
                            # Handle absolute paths
                            arcname = str(file_path)

                        # Add file to archive
                        archive.add(file_path, arcname=arcname)
                        self.processed_files += 1

                        progress.update(task, advance=1)

                    except (OSError, PermissionError) as e:
                        self.errors.append((file_path, str(e)))
                        self.skipped_files += 1
                        progress.update(task, advance=1)

    def _add_metadata(
        self, archive: CompressedTarFile, target_path: Path, files_to_backup: List[Path]
    ) -> None:
        """Add backup metadata to the archive."""
        metadata = {
            "backup_info": {
                "created_at": self.start_time.isoformat() if self.start_time else "",
                "target_path": str(target_path),
                "total_files": len(files_to_backup),
                "total_size": self.total_size,
                "compression_format": self.config.compression.format,
                "compression_level": self.config.compression.level,
            },
            "config": self.config.model_dump(),
            "git_repositories": self.file_filter.git_detector.get_repository_stats(),
            "filter_stats": self.file_filter.get_filter_stats(),
        }

        metadata_json = json.dumps(metadata, indent=2, default=str)
        archive.add_string(metadata_json, ".backup_metadata.json")

    def _show_dry_run_results(
        self, files_to_backup: List[Path], target_path: Path
    ) -> None:
        """Show dry run results."""
        self.console.print(
            "\n[bold green]Dry run - files that would be backed up:[/bold green]"
        )

        # Group files by git repository status
        git_files = []
        regular_files = []

        for file_path in files_to_backup:
            if self.file_filter.git_detector.is_in_git_repository(file_path):
                git_files.append(file_path)
            else:
                regular_files.append(file_path)

        if git_files:
            self.console.print(f"\n[cyan]Git repository files: {len(git_files)}[/cyan]")
            for file_path in git_files[:10]:  # Show first 10
                rel_path = (
                    file_path.relative_to(target_path)
                    if file_path.is_relative_to(target_path)
                    else file_path
                )
                self.console.print(f"  [git] {rel_path}")
            if len(git_files) > 10:
                self.console.print(f"  ... and {len(git_files) - 10} more git files")

        if regular_files:
            self.console.print(f"\n[blue]Regular files: {len(regular_files)}[/blue]")
            for file_path in regular_files[:10]:  # Show first 10
                rel_path = (
                    file_path.relative_to(target_path)
                    if file_path.is_relative_to(target_path)
                    else file_path
                )
                self.console.print(f"  [reg] {rel_path}")
            if len(regular_files) > 10:
                self.console.print(
                    f"  ... and {len(regular_files) - 10} more regular files"
                )

        # Show filter stats
        filter_stats = self.file_filter.get_filter_stats()
        self.console.print("\n[yellow]Filter statistics:[/yellow]")
        self.console.print(
            f"  Git repositories found: {filter_stats['git_repositories']}"
        )
        self.console.print(
            f"  Max file size: {self._format_size(filter_stats['max_file_size_bytes'])}"
        )

    def _show_backup_results(self, output_path: Path) -> None:
        """Show backup operation results."""
        duration = (
            self.end_time - self.start_time
            if self.end_time and self.start_time
            else None
        )

        self.console.print("\n[bold green]Backup completed![/bold green]")
        self.console.print(f"[green]Archive:[/green] {output_path}")
        self.console.print(f"[green]Files processed:[/green] {self.processed_files:,}")

        if self.skipped_files > 0:
            self.console.print(
                f"[yellow]Files skipped:[/yellow] {self.skipped_files:,}"
            )

        if self.errors:
            self.console.print(f"[red]Errors:[/red] {len(self.errors):,}")
            # Show first few errors
            for file_path, error in self.errors[:3]:
                self.console.print(f"  [red]Error:[/red] {file_path} - {error}")
            if len(self.errors) > 3:
                self.console.print(
                    f"  [red]... and {len(self.errors) - 3} more errors[/red]"
                )

        # Show archive size
        try:
            archive_size = output_path.stat().st_size
            compression_ratio = (
                (1 - archive_size / self.total_size) * 100 if self.total_size > 0 else 0
            )
            self.console.print(
                f"[green]Archive size:[/green] {self._format_size(archive_size)}"
            )
            self.console.print(
                f"[green]Compression ratio:[/green] {compression_ratio:.1f}%"
            )
        except OSError:
            pass

        if duration:
            self.console.print(f"[green]Duration:[/green] {duration}")

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        size_float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_float < 1024.0:
                return f"{size_float:.1f} {unit}"
            size_float = size_float / 1024.0
        return f"{size_float:.1f} PB"

    def _get_backup_info(
        self,
        target_path: Path,
        output_path: Path,
        files_list: Optional[List[Path]] = None,
    ) -> Dict[str, Any]:
        """Get backup information dictionary."""
        duration = (
            self.end_time - self.start_time
            if self.end_time and self.start_time
            else None
        )

        return {
            "success": len(self.errors) == 0,  # No errors means success
            "target_path": str(target_path),
            "output_path": str(output_path),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_files": self.total_files,
            "total_size": self.total_size,
            "processed_files": self.processed_files,
            "skipped_files": self.skipped_files,
            "errors": len(self.errors),
            "files": files_list if files_list is not None else [],
            "compression_format": self.config.compression.format,
            "compression_level": self.config.compression.level,
            "duration_seconds": duration.total_seconds() if duration else None,
            "performance_metrics": {
                "total_scan_time": self.performance_metrics.total_scan_time,
                "repo_discovery_time": self.performance_metrics.repo_discovery_time,
                "repo_processing_time": self.performance_metrics.repo_processing_time,
                "non_repo_processing_time": self.performance_metrics.non_repo_processing_time,
                "total_repos_processed": self.performance_metrics.total_repos_processed,
                "parallel_workers_used": self.performance_metrics.parallel_workers_used,
                "enable_parallel": self.performance_metrics.enable_parallel,
                "total_files_found": self.performance_metrics.total_files_found,
                "files_per_second": self.performance_metrics.total_files_found
                / self.performance_metrics.total_scan_time
                if self.performance_metrics.total_scan_time > 0
                else 0,
            },
        }


def create_backup(
    config: BackupConfig,
    target_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    dry_run: bool = False,
    verbose: bool = False,
    console: Optional[Console] = None,
) -> Dict[str, Any]:
    """Convenience function to create a backup.

    Args:
        config: Backup configuration
        target_path: Path to backup (default from config)
        output_path: Output archive path (default from config)
        dry_run: If True, only show what would be backed up
        verbose: If True, show detailed progress information
        console: Rich console for output

    Returns:
        Dictionary with backup information and statistics
    """
    backup_op = BackupOperation(config, console)
    backup_op.verbose = verbose
    return backup_op.create_backup(
        target_path=target_path, output_path=output_path, dry_run=dry_run
    )
